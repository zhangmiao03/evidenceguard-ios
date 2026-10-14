"""Internal-demo personal context and durable, read-only proactive recipes.

Installation IDs namespace preferences; they are not account authentication.
Camera/Skill data remains shared inside the isolated demo household.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .camera.sources import official_mode, registered_device_ids


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    dailySummary: bool = False
    summaryHour: int = Field(default=18, ge=0, le=23)
    quietStart: int = Field(default=22, ge=0, le=23)
    quietEnd: int = Field(default=8, ge=0, le=23)
    timezone: str = 'UTC'
    @field_validator('timezone')
    @classmethod
    def known_zone(cls, value):
        try: ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('请选择有效时区')
        return value


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, max_length=500)
    temporary: bool = False
    @field_validator('content')
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value: raise ValueError('记忆内容不能为空')
        return value


def installation(value: str | None) -> str:
    try: return str(uuid.UUID(value or ''))
    except ValueError: raise ValueError('客户端身份无效，请重新打开 App')


class PersonalAgent:
    def __init__(self, store):
        self.store = store
        self.last_error = None
        self.engine = None
        self.memory = None
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS personal_profiles (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            store.db.execute('CREATE TABLE IF NOT EXISTS personal_memories (id TEXT PRIMARY KEY, client TEXT NOT NULL, payload TEXT NOT NULL)')
            store.db.execute('CREATE TABLE IF NOT EXISTS personal_inbox (id TEXT PRIMARY KEY, client TEXT NOT NULL, dedupe TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(client,dedupe))')

    def profile(self, client):
        with self.store.lock:
            row = self.store.db.execute('SELECT payload FROM personal_profiles WHERE id=?', (client,)).fetchone()
        return json.loads(row[0]) if row else dict(preferences=Preferences().model_dump(), revision=0)

    def preferences(self, client, values: Preferences):
        with self.store.transaction():
            old = self.profile(client)
            profile = dict(preferences=values.model_dump(), revision=old['revision']+1)
            self.store.db.execute('INSERT OR REPLACE INTO personal_profiles VALUES (?,?)', (client, json.dumps(profile)))
        return self.snapshot(client)

    def memories(self, client, now=None):
        now = time.time() if now is None else now
        with self.store.lock:
            rows = self.store.db.execute('SELECT payload FROM personal_memories WHERE client=? ORDER BY rowid DESC', (client,)).fetchall()
        return [m for row in rows if (m := json.loads(row[0])).get('expiresAt') is None or m['expiresAt'] > now]

    def remember(self, client, body: MemoryInput):
        with self.store.transaction():
            if len(self.memories(client)) >= 100: raise ValueError('最多保留 100 条记忆，请先移除不再需要的内容')
            item = dict(id=uuid.uuid4().hex, content=body.content, source='user_confirmed', createdAt=time.time(),
                        expiresAt=time.time()+86400 if body.temporary else None)
            self.store.db.execute('INSERT INTO personal_memories VALUES (?,?,?)', (item['id'], client, json.dumps(item)))
        return self.snapshot(client)

    def forget(self, client, key):
        with self.store.transaction():
            item = next((m for m in self.memories(client) if m['id']==key), None)
            if item and self.memory: self.memory.suppress(client,item)
            self.store.db.execute('DELETE FROM personal_memories WHERE client=? AND id=?', (client,key))
        return self.snapshot(client)

    def inbox(self, client):
        with self.store.lock:
            rows = self.store.db.execute('SELECT payload FROM personal_inbox WHERE client=? ORDER BY rowid DESC LIMIT 50', (client,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read(self, client, key):
        with self.store.transaction():
            row = self.store.db.execute('SELECT payload FROM personal_inbox WHERE client=? AND id=?', (client,key)).fetchone()
            if not row: raise KeyError(key)
            item = json.loads(row[0]); item['read'] = True
            self.store.db.execute('UPDATE personal_inbox SET payload=? WHERE client=? AND id=?', (json.dumps(item),client,key))
            if self.engine:
                self.store.db.execute("UPDATE assistant_messages SET payload=json_set(payload,'$.read',json('true')) WHERE client=? AND id=?",(client,key))
        return self.snapshot(client)

    def snapshot(self, client):
        return self.profile(client) | dict(memories=self.memories(client), inbox=self.inbox(client), delivery='in_app', lastError=self.last_error, messages=self.engine.messages(client) if self.engine else [], activity=self.engine.activity(client) if self.engine else [], automaticMemory=self.memory.status(client) if self.memory else None)

    def context(self, client):
        if not client: return None
        profile = self.profile(client)
        return dict(revision=profile['revision'], preferences=profile['preferences'], memories=self.memories(client),
                    scope='installation preferences; shared demo household observations', grantsPermissions=False)

    def emit(self, client, dedupe, kind, title, body, now, skill_id=None):
        if self.engine:
            return self.engine.enqueue(client,dedupe,kind,title,body,now,skill_id)
        item = dict(id=uuid.uuid4().hex, kind=kind, title=title, body=body, createdAt=now, read=False,
                    skillId=skill_id, delivery='in_app')
        self.store.db.execute('INSERT OR IGNORE INTO personal_inbox VALUES (?,?,?,?)', (item['id'],client,dedupe,json.dumps(item)))

    def tick(self, now=None):
        now = time.time() if now is None else now
        # Recipes only read existing task receipts. They cannot capture, enable or control a device.
        with self.store.transaction():
            profiles = self.store.db.execute('SELECT id,payload FROM personal_profiles').fetchall()
            skills = self.store.skills()
            if official_mode(getattr(getattr(self.engine,'runtime',None),'cameras',None)):
                ingest=getattr(self.engine,'ingest',None)
                ids=registered_device_ids(self.store)
                skills=[s for s in skills if set(s['devices'])<=ids and not s.get('replay')]
            for client, raw in profiles:
                p = json.loads(raw)['preferences']
                if not p['enabled']: continue
                local = datetime.fromtimestamp(now, ZoneInfo(p['timezone']))
                start, end, hour = p['quietStart'], p['quietEnd'], local.hour
                quiet = (start <= hour < end) if start < end else (hour >= start or hour < end) if start != end else False
                if quiet: continue  # Evaluate still-current facts when the quiet period ends.
                for skill in skills:
                    if self.engine and skill['status']=='active' and skill['result']=='unknown':
                        # One concern per transition into unknown, not one per sampled frame.
                        row=self.store.db.execute("SELECT id,at FROM events WHERE run_id=? AND type IN ('result_changed','skill_confirmed','lifecycle_changed') ORDER BY id DESC LIMIT 1",(skill['id'],)).fetchone()
                        if row and now-row[1]>=60:
                            self.emit(client,f'coverage:{skill["id"]}:{row[0]}','coverage','有一处画面需要确认',skill['name']+'：'+skill['resultReason'],now,skill['id'])
                    if skill.get('alert') != 'open': continue
                    # The alert event sequence identifies an episode, so reminders survive restart without duplicates.
                    with self.store.lock:
                        row = self.store.db.execute("SELECT id,at FROM events WHERE run_id=? AND type='alert_opened' ORDER BY id DESC LIMIT 1", (skill['id'],)).fetchone()
                    if not row: continue
                    event_id, at = row
                    self.emit(client,f'event:{event_id}','event','有一项守护需要关注',skill['name']+'：'+skill['resultReason'],now,skill['id'])
                    if now-at >= 300:
                        self.emit(client,f'followup:{event_id}','followup','这件事还需要确认',skill['name']+' 的提醒尚未处理。可以查看证据或请求复核；助手没有替你关闭任务。',now,skill['id'])
                if p['dailySummary'] and hour >= p['summaryHour']:
                    active = [s for s in skills if s['status']=='active']
                    alerts = sum(s.get('alert')=='open' for s in skills)
                    self.emit(client,'daily:'+local.date().isoformat(),'schedule','今天的守护概况',
                              f'当前有 {len(active)} 项运行中的守护、{alerts} 项待处理提醒。此概况来自已记录的任务状态，不代表全天现场均已覆盖。',now)
            self.last_error = None

    async def run(self):
        while True:
            try: self.tick()
            except Exception: self.last_error = '主动提醒暂未更新，正在重试'
            await asyncio.sleep(30)
