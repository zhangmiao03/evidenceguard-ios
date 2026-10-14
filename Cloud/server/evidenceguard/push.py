"""Opt-in APNs alerts. One process owns the durable SQLite outbox.

Device bindings use a Keychain secret in addition to the existing household
bearer token. This is not multi-tenant account authentication. Provider acceptance
is recorded separately from a user opening the alert; neither proves delivery.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class DeviceRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=32, max_length=512, pattern=r'^(?:[0-9a-fA-F]{2})+$')
    environment: Literal['development', 'production']
    topic: str = Field(min_length=1, max_length=200)


class Presence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    active: bool


class APNsProvider:
    def __init__(self):
        self.topic = os.getenv('EG_APNS_TOPIC', 'com.zhangmiao.evidenceguard')
        self.team = os.getenv('EG_APNS_TEAM_ID', '')
        self.key_id = os.getenv('EG_APNS_KEY_ID', '')
        self.key_path = os.getenv('EG_APNS_KEY_PATH', '')
        self.enabled = os.getenv('EG_APNS_ENABLED', '0') == '1'
        self.environment = os.getenv('EG_APNS_ENVIRONMENT', 'production')
        self.clients = {}
        self.jwt = None
        self.signed_at = 0
        self.configuration_error = None
        if self.enabled:
            try: self.authorization()
            except Exception: self.configuration_error = '推送服务配置尚未就绪'

    @property
    def ready(self):
        return bool(self.enabled and self.team and self.key_id and self.key_path and
                    self.environment in {'development', 'production', 'both'} and not self.configuration_error)

    def authorization(self):
        import jwt
        now = time.time()
        if not self.jwt or not 0 <= now - self.signed_at < 2400:
            if not self.team or not self.key_id or not self.key_path: raise ValueError('APNs configuration missing')
            self.jwt = jwt.encode({'iss': self.team, 'iat': int(now)}, Path(self.key_path).read_bytes(),
                                  algorithm='ES256', headers={'kid': self.key_id})
            self.signed_at = now
        return 'bearer ' + self.jwt

    async def send(self, device, delivery, scope):
        environment = device['environment']
        host = 'api.push.apple.com' if environment == 'production' else 'api.sandbox.push.apple.com'
        client = self.clients.get(environment)
        if client is None:
            client = self.clients[environment] = httpx.AsyncClient(http2=True, timeout=20, trust_env=False)
        body = {'aps': {'alert': {'title': 'EvidenceGuard', 'body': {
            'test': '手机通知测试，请点开查看结果。',
            'run': '你交给助手的事项有了结果，点开查看。',
            'draft': '助手已准备好草案，等待你确认。',
        }.get(delivery['kind'], '助手有一条新提醒，点开查看。')}, 'sound': 'default',
            'thread-id': 'evidenceguard-' + scope}, 'eg': {'deliveryId': delivery['id'], 'scope': scope}}
        response = await client.post('https://' + host + '/3/device/' + device['token'], json=body,
            headers={'authorization': self.authorization(), 'apns-topic': self.topic,
                     'apns-push-type': 'alert', 'apns-priority': '10',
                     'apns-id': delivery['id'], 'apns-collapse-id': delivery['id'],
                     'apns-expiration': str(int(delivery['expires_at']))})
        try: detail = response.json() if response.content else {}
        except ValueError: detail = {}
        # Never persist a raw response/request: it can contain device credentials.
        reason = detail.get('reason', '')
        if not isinstance(reason, str) or not re.fullmatch(r'[A-Za-z]{0,80}', reason): reason = 'ProviderError'
        return response.status_code, reason

    async def close(self):
        for client in self.clients.values(): await client.aclose()


class PushService:
    def __init__(self, store, personal, provider=None):
        self.store, self.personal = store, personal
        self.provider = provider or APNsProvider()
        # Explicitly configured per service, never supplied by a model or request.
        self.scope = os.getenv('EG_PUSH_SCOPE', '')
        self.last_error = None
        with store.transaction():
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS push_devices (
                    client TEXT PRIMARY KEY, secret_hash TEXT NOT NULL, token TEXT NOT NULL,
                    environment TEXT NOT NULL, topic TEXT NOT NULL, enabled INTEGER NOT NULL,
                    version TEXT NOT NULL, updated_at REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0, seen_at REAL NOT NULL DEFAULT 0,
                    UNIQUE(token,environment));
                CREATE TABLE IF NOT EXISTS push_outbox (
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, source TEXT NOT NULL,
                    kind TEXT NOT NULL, target TEXT NOT NULL, state TEXT NOT NULL,
                    created_at REAL NOT NULL, due REAL NOT NULL, expires_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, reason TEXT,
                    accepted_at REAL, opened_at REAL, UNIQUE(client,source));
                CREATE INDEX IF NOT EXISTS push_due ON push_outbox(state,due);
            ''')
            store.db.execute("UPDATE push_outbox SET state='retry',reason='RestartRecovery' WHERE state='sending'")

    @property
    def ready(self): return bool(re.fullmatch(r'[a-z0-9-]{1,40}', self.scope) and self.provider.ready)

    def device(self, client):
        with self.store.lock:
            cursor = self.store.db.execute('SELECT * FROM push_devices WHERE client=?', (client,))
            row = cursor.fetchone()
            return dict(zip([c[0] for c in cursor.description], row)) if row else None

    def authenticate(self, client, secret, allow_new=False):
        if not secret or not re.fullmatch(r'[a-f0-9]{64}', secret):
            raise HTTPException(403, '本机通知授权无效，请重新开启通知')
        digest = hashlib.sha256(secret.encode()).hexdigest()
        device = self.device(client)
        if device and not hmac.compare_digest(device['secret_hash'], digest):
            raise HTTPException(403, '本机通知授权不匹配')
        if not device and not allow_new: raise HTTPException(404, '当前手机尚未登记通知')
        return digest

    def status(self, client, secret):
        self.authenticate(client, secret, allow_new=True)
        device = self.device(client)
        with self.store.lock:
            row = self.store.db.execute('SELECT state,reason,accepted_at,opened_at FROM push_outbox WHERE client=? ORDER BY created_at DESC LIMIT 1', (client,)).fetchone()
        return dict(serverReady=self.ready, scope=self.scope, registered=bool(device),
                    enabled=bool(device and device['enabled']), lastState=row[0] if row else None,
                    lastReason=row[1] if row else None, acceptedAt=row[2] if row else None,
                    openedAt=row[3] if row else None, workerError=self.last_error)

    def register(self, client, secret, body):
        if body.topic != self.provider.topic: raise HTTPException(409, '此版本的通知标识与服务不匹配')
        if self.provider.environment not in {body.environment, 'both'}:
            raise HTTPException(409, '此版本的通知环境与服务不匹配，请使用对应的测试版本')
        with self.store.transaction():
            digest = self.authenticate(client, secret, allow_new=True)
            token = body.token.lower()
            owner = self.store.db.execute('SELECT client FROM push_devices WHERE token=? AND environment=?', (token, body.environment)).fetchone()
            if owner and owner[0] != client: raise HTTPException(409, '此设备已有通知登记，请使用原安装的授权')
            self.store.db.execute('''INSERT INTO push_devices
                (client,secret_hash,token,environment,topic,enabled,version,updated_at) VALUES (?,?,?,?,?,1,?,?)
                ON CONFLICT(client) DO UPDATE SET token=excluded.token,environment=excluded.environment,
                topic=excluded.topic,enabled=1,version=excluded.version,updated_at=excluded.updated_at''',
                (client,digest,token,body.environment,body.topic,uuid.uuid4().hex,time.time()))
        return self.status(client, secret)

    def disable(self, client, secret):
        with self.store.transaction():
            self.authenticate(client, secret, allow_new=True)
            # Keep the binding proof, discard the actual device token immediately.
            self.store.db.execute("UPDATE push_devices SET enabled=0,token=?,version=? WHERE client=?",
                                  ('disabled:' + client, uuid.uuid4().hex, client))
            self.store.db.execute("UPDATE push_outbox SET state='cancelled',reason='Disabled' WHERE client=? AND state IN ('pending','retry')", (client,))
        return self.status(client, secret)

    def presence(self, client, secret, active):
        with self.store.transaction():
            self.authenticate(client, secret)
            self.store.db.execute('UPDATE push_devices SET active=?,seen_at=? WHERE client=?', (active,time.time(),client))
        return {'status':'updated'}

    def enqueue(self, client, source, kind, target, now=None, delay=0, expires=None):
        now = time.time() if now is None else now
        with self.store.transaction():
            device = self.device(client)
            if not device or not device['enabled']: return None
            key = str(uuid.uuid4())
            self.store.db.execute('''INSERT OR IGNORE INTO push_outbox
                (id,client,source,kind,target,state,created_at,due,expires_at) VALUES (?,?,?,?,?,'pending',?,?,?)''',
                (key,client,source,kind,json.dumps(target),now,now+delay,expires or now+3600))
            return self.store.db.execute('SELECT id FROM push_outbox WHERE client=? AND source=?', (client,source)).fetchone()[0]

    def message(self, client, message, job):
        self.enqueue(client, message['id'], 'message', {'messageId':message['id']},
                     expires=min(job['expiresAt'], time.time()+3600))

    def completed_run(self, run):
        if not run.get('clientId') or run['status'] not in {'completed','failed'}: return
        # Fast foreground chat does not need an extra phone alert.
        if not run.get('draft') and run.get('executionMode') != 'history' and time.time()-run['createdAt'] < 15: return
        self.enqueue(run['clientId'], 'run:' + run['id'], 'draft' if run.get('draft') else 'run', {'runId':run['id']})

    def test(self, client, secret):
        self.authenticate(client, secret)
        if not self.ready: raise HTTPException(409, '推送服务尚未配置完成')
        if not self.device(client)['enabled']: raise HTTPException(409, '请先开启手机通知')
        now = time.time()
        with self.store.transaction():
            last = self.store.db.execute("SELECT MAX(created_at) FROM push_outbox WHERE client=? AND kind='test'", (client,)).fetchone()[0]
            if last and now-last < 60: raise HTTPException(429, '请等待一分钟再测试')
            key = self.enqueue(client, 'test:' + uuid.uuid4().hex, 'test', {}, now, delay=10)
        return {'id':key}

    def target(self, delivery):
        target = json.loads(delivery['target'])
        client = delivery['client']
        if delivery['kind'] == 'test': return dict(kind='test', title='手机通知测试', body='已记录你点开这条测试通知。')
        if 'messageId' in target:
            row = self.store.db.execute('SELECT payload FROM assistant_messages WHERE id=? AND client=?', (target['messageId'],client)).fetchone()
            if not row: raise KeyError('message')
            message = json.loads(row[0])
            # Evidence and task IDs come from stored sources, never the APNs payload.
            evidence = next((s['id'][9:] for s in message.get('sources',[]) if s['id'].startswith('evidence:')), None)
            return dict(kind='message', title=message['title'], body=message['body'], messageId=message['id'],
                        skillId=message.get('skillId'), evidenceId=evidence)
        run = self.store.run(target['runId'])
        if not run or run.get('clientId') != client: raise KeyError('run')
        return dict(kind='run',title='助手处理结果',body=run.get('text') or run.get('error') or '请查看对话中的结果。',
                    conversationId=run['conversationId'],skillId=run.get('skillId'),
                    executionMode=run.get('executionMode','live'),
                    draftId=run.get('draft',{}).get('id') if run.get('draft') else None)

    def open(self, client, secret, key):
        with self.store.transaction():
            self.authenticate(client, secret)
            delivery = self.row(key)
            if not delivery or delivery['client'] != client: raise HTTPException(404, '通知不存在或不属于当前手机')
            target = self.target(delivery)
            self.store.db.execute("UPDATE push_outbox SET opened_at=COALESCE(opened_at,?),state=CASE WHEN state IN ('pending','retry') THEN 'cancelled' ELSE state END WHERE id=?", (time.time(),key))
            if target.get('messageId'): self.personal.read(client,target['messageId'])
        return target

    def row(self, key):
        cursor = self.store.db.execute('SELECT * FROM push_outbox WHERE id=?', (key,))
        row = cursor.fetchone()
        return dict(zip([c[0] for c in cursor.description], row)) if row else None

    def eligible(self, item, device, now):
        if now >= item['expires_at']: return 'expired', 'Expired', None
        if not device or not device['enabled']: return 'cancelled', 'Disabled', None
        if item['opened_at']: return 'cancelled', 'Opened', None
        if item['kind'] == 'test': return None
        p = self.personal.profile(item['client'])['preferences']
        if item['kind'] == 'message':
            row = self.store.db.execute('SELECT payload FROM assistant_messages WHERE id=? AND client=?', (item['source'],item['client'])).fetchone()
            if not row: return 'cancelled', 'Removed', None
            message = json.loads(row[0])
            if not p['enabled'] or message.get('read') or message.get('feedback') in {'read','handled','dismiss','snooze'}:
                return 'cancelled', 'NoLongerNeeded', None
            job_row = self.store.db.execute('SELECT payload FROM proactive_jobs WHERE id=?', (message['jobId'],)).fetchone()
            if job_row:
                # Revalidate source/opt-in/quiet hours without counting the already
                # published message against the publication frequency gate again.
                gate = self.personal.engine.gate(json.loads(job_row[0]), now, publication=False)
                if gate: return ('retry' if gate[0]=='deferred' else gate[0], 'PolicyChanged', gate[1])
        if self.personal.engine.quiet(p, now): return 'retry', 'QuietHours', now+60
        # A short lease is renewed while this app is visible, never background polling.
        if device['active'] and now-device['seen_at'] < 75: return 'retry', 'AppVisible', now+30
        zone = ZoneInfo(p['timezone'])
        day = datetime.fromtimestamp(now, zone).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        count,last = self.store.db.execute("SELECT COUNT(*),MAX(accepted_at) FROM push_outbox WHERE client=? AND kind!='test' AND accepted_at>=?", (item['client'],day)).fetchone()
        if count >= 6: return 'retry', 'DailyLimit', now+3600
        if last and now-last < 300: return 'retry', 'RateLimit', last+300
        return None

    async def step(self, now=None):
        now = time.time() if now is None else now
        with self.store.transaction():
            row = self.store.db.execute("SELECT id FROM push_outbox WHERE state IN ('pending','retry') AND due<=? ORDER BY due,created_at LIMIT 1", (now,)).fetchone()
            if not row: return False
            item = self.row(row[0]); device = self.device(item['client'])
            gate = self.eligible(item,device,now)
            if gate:
                self.store.db.execute('UPDATE push_outbox SET state=?,reason=?,due=? WHERE id=?', (gate[0],gate[1],gate[2] or now,item['id']))
                return True
            if not self.ready:
                self.store.db.execute("UPDATE push_outbox SET due=?,reason='NotConfigured' WHERE id=?", (now+60,item['id']))
                return True
            self.store.db.execute("UPDATE push_outbox SET state='sending',attempts=attempts+1 WHERE id=?", (item['id'],))
        try:
            status,reason = await self.provider.send(device,item,self.scope)
        except asyncio.CancelledError: raise  # durable 'sending' is recovered on restart
        except Exception:
            status,reason = 0,'TransportError'  # URL/token must never reach logs
        with self.store.transaction():
            if status == 200:
                self.store.db.execute("UPDATE push_outbox SET state='accepted',accepted_at=?,reason=NULL WHERE id=?", (now,item['id']))
            elif status in {0,429} or status >= 500:
                attempts = item['attempts']+1
                # Apple recommends at least 15 minutes for 5xx responses.
                delay = max(900 if status>=500 else 30, min(1800,30*2**min(attempts,6)))
                self.store.db.execute('UPDATE push_outbox SET state=?,due=?,reason=? WHERE id=?',
                                      ('retry' if attempts<6 else 'failed',now+delay,reason,item['id']))
            else:
                self.store.db.execute("UPDATE push_outbox SET state='failed',reason=? WHERE id=?", (reason or 'ProviderRejected',item['id']))
                if status == 410 or reason in {'BadDeviceToken','DeviceTokenNotForTopic'}:
                    # A late error for the old token must not invalidate a fresh registration.
                    self.store.db.execute('UPDATE push_devices SET enabled=0 WHERE client=? AND version=?', (item['client'],device['version']))
        return True

    async def run(self):
        while True:
            try:
                for _ in range(8):
                    if not await self.step(): break
                self.last_error = None
            except asyncio.CancelledError: raise
            except Exception: self.last_error = '手机通知正在重试'
            await asyncio.sleep(2)
