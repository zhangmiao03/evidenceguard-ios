"""Camera-first proactive coordinator for a single-process internal demo.

SQLite owns triggers, retry checkpoints and publication. The model can propose a
message, never publish it or operate a camera. Installation IDs are namespaces,
not production authentication; the demo household's camera observations are shared.
"""
from __future__ import annotations
import asyncio
import os
import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field
from .camera.sources import official_mode, registered_device_ids
from . import briefings


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    valueScore: int = Field(ge=0, le=100, strict=True)
    title: str = Field(default='', max_length=80)
    body: str = Field(default='', max_length=600)
    reason: str = Field(min_length=1, max_length=300)
    sourceIds: list[str] = Field(default_factory=list, max_length=12)


class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['read', 'handled', 'snooze', 'dismiss']


class BindConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversationId: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


class ProactiveEngine:
    def __init__(self, personal, runtime):
        self.personal, self.runtime, self.store = personal, runtime, personal.store
        self.ingest = None
        self.demo = None
        self.push = None
        self.watch = None
        personal.engine = self
        with self.store.transaction():
            self.store.db.executescript('''
                CREATE TABLE IF NOT EXISTS proactive_jobs (
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, dedupe TEXT NOT NULL,
                    status TEXT NOT NULL, due REAL NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(client,dedupe));
                CREATE INDEX IF NOT EXISTS proactive_due ON proactive_jobs(status,due);
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, job_id TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS personal_conversations (
                    client TEXT PRIMARY KEY, conversation TEXT NOT NULL UNIQUE);
            ''')
            # One ASGI process owns this SQLite store. Re-run read-only attempts,
            # never replay a device effect; UNIQUE(job_id) protects publication.
            self.store.db.execute("UPDATE proactive_jobs SET status='pending' WHERE status='running'")

    def bind(self, client, conversation):
        with self.store.transaction():
            owner = self.owner(conversation)
            if owner and owner != client: raise ValueError('此对话属于另一客户端')
            self.store.db.execute('INSERT INTO personal_conversations VALUES (?,?) ON CONFLICT(client) DO UPDATE SET conversation=excluded.conversation', (client,conversation))
        return {'status':'bound'}

    def owner(self, conversation):
        with self.store.lock:
            row = self.store.db.execute('SELECT client FROM personal_conversations WHERE conversation=?', (conversation,)).fetchone()
        return row[0] if row else None

    def messages(self, client):
        with self.store.lock:
            rows = self.store.db.execute('SELECT payload FROM assistant_messages WHERE client=? ORDER BY created_at DESC LIMIT 50', (client,)).fetchall()
        return [briefings.present(json.loads(r[0])) for r in reversed(rows)]

    def message(self, client, key):
        # A push or explicit reply can refer to a message outside the bootstrap window.
        with self.store.lock:
            row = self.store.db.execute('SELECT payload FROM assistant_messages WHERE id=? AND client=?', (key, client)).fetchone()
        if not row: raise KeyError(key)
        return briefings.present(json.loads(row[0]))

    def activity(self, client):
        with self.store.lock:
            rows = self.store.db.execute('SELECT id,status,payload FROM proactive_jobs WHERE client=? ORDER BY rowid DESC LIMIT 20',(client,)).fetchall()
        return [dict(id=key,status=status,kind=(j:=json.loads(raw))['kind'],reason=j.get('reason','等待检查摄像头观察记录'),createdAt=j['createdAt']) for key,status,raw in rows]

    def enqueue(self, client, dedupe, kind, title, body, now, skill_id=None, report=None):
        key = 'proactive-'+uuid.uuid4().hex
        job = dict(id=key, client=client, dedupe=dedupe, kind=kind, title=title, body=body,
                   cameraObservationId=dedupe if kind=='camera_observation' else None,
                   skillId=skill_id, createdAt=now, expiresAt=now+86400, attempts=0,
                   cameraEpisodeId=dedupe if kind=='camera_event' else None,reason='等待检查摄像头观察记录',episode=dedupe.split(':')[-1] if kind in {'event','followup'} else None)
        if report:
            job.update(report=report, expiresAt=report['expiresAt'])
        with self.store.transaction():
            self.store.db.execute('INSERT OR IGNORE INTO proactive_jobs VALUES (?,?,?,?,?,?)',
                                  (key,client,dedupe,'pending',now,json.dumps(job,ensure_ascii=False)))
        return key

    def save(self, job, status, due=None, reason=None):
        if reason is not None: job['reason'] = reason
        self.store.db.execute('UPDATE proactive_jobs SET status=?,due=?,payload=? WHERE id=?',
                              (status, due if due is not None else time.time(), json.dumps(job,ensure_ascii=False),job['id']))

    def feedback(self, client, message_id, action):
        with self.store.transaction():
            row = self.store.db.execute('SELECT payload FROM assistant_messages WHERE id=? AND client=?',(message_id,client)).fetchone()
            if not row: raise KeyError(message_id)
            message = json.loads(row[0]); message['read'] = True
            if action != 'read':
                message['feedback'] = action; message['feedbackAt'] = time.time()
            self.store.db.execute('UPDATE assistant_messages SET payload=? WHERE id=?',(json.dumps(message,ensure_ascii=False),message_id))
            # Retain the notice for older App versions.
            self.store.db.execute('UPDATE personal_inbox SET payload=json_set(payload,\'$.read\',json(\'true\')) WHERE id=? AND client=?',(message_id,client))
            if action=='snooze':
                original=self.store.db.execute('SELECT payload FROM proactive_jobs WHERE id=? AND client=?',(message['jobId'],client)).fetchone()
                if original:
                    previous=json.loads(original[0]); now=time.time()
                    job=previous | dict(id='revisit-'+message_id, dedupe='revisit:'+message_id, kind='revisit',
                                        sourceKind=previous.get('sourceKind',previous['kind']), parentMessageId=message_id,
                                        createdAt=now,expiresAt=now+86400,attempts=0,reason='用户要求 1 小时后重新检查')
                    self.store.db.execute('INSERT OR IGNORE INTO proactive_jobs VALUES (?,?,?,?,?,?)',
                                          (job['id'],client,job['dedupe'],'deferred',now+3600,json.dumps(job,ensure_ascii=False)))
        return self.personal.snapshot(client)

    def quiet(self, preferences, now):
        hour = datetime.fromtimestamp(now,ZoneInfo(preferences['timezone'])).hour
        start,end = preferences['quietStart'],preferences['quietEnd']
        return start <= hour < end if start < end else (hour >= start or hour < end) if start != end else False

    def event_tasks(self, job, now):
        episode=self.ingest.episode(job.get('cameraEpisodeId') or job['dedupe']) if self.ingest else None
        if not episode: return []
        events=self.ingest.events(episode['id'])
        latest=max((e['metadata']['startMs']/1000 for e in events),default=0)
        return self.personal.tasks.matching(job['client'],episode,latest,now)

    def gate(self, job, now, publication=True):
        p = self.personal.profile(job['client'])['preferences']
        if not p['enabled']: return 'cancelled',None,'用户已关闭主动提醒'
        if job.get('report') and now >= job['report']['endAt'] + briefings.REPORT_GRACE_SECONDS:
            return 'expired',None,'已超过报告时段，不再补发旧的早晚报告'
        if now >= job['expiresAt']: return 'expired',None,'触发已过期，未发送旧提醒'
        if job['kind']=='schedule' and not p['dailySummary']: return 'cancelled',None,'每日概况已关闭'
        if job['kind']=='schedule' and not job.get('report') and job['dedupe'].startswith('daily:'):
            return 'cancelled',None,'旧版每日概况已由早晚报告计划替代'
        if job.get('report') and job['report']['schedule'] != briefings.schedule_signature(p):
            return 'cancelled',None,'早晚报告设置已更改，旧计划不再发送'
        if job.get('report') and not job.get('parentMessageId'):
            report = job['report']
            with self.store.lock:
                delivered = self.store.db.execute("SELECT 1 FROM assistant_messages WHERE client=? AND job_id!=? AND json_extract(payload,'$.report.localDate')=? AND json_extract(payload,'$.report.slot')=? LIMIT 1",
                                                   (job['client'],job['id'],report['localDate'],report['slot'])).fetchone()
            if delivered: return 'cancelled',None,'今天这份报告已经生成，不重复发送'
        kind=job.get('sourceKind',job['kind'])
        if kind=='camera_observation':
            observation=self.watch.observation(job.get('cameraObservationId') or job['dedupe']) if self.watch else None
            if not observation or observation['status']!='completed': return 'cancelled',None,'定时图片尚未完成核验'
            config=self.watch.get(observation['cameraId'])
            if not config['enabled'] or config['revision']!=observation['revision']: return 'cancelled',None,'定时观察已暂停或配置已变化'
            if now-observation['observedAt']>3600: return 'expired',None,'取样已过期，未发送旧现场提醒'
        if official_mode(getattr(self.runtime,'cameras',None)) and kind=='demo_event':
            return 'cancelled',None,'当前已切换官方事件来源，测试证据保留但不再发送测试提醒'
        if kind=='demo_event':
            scene=self.demo.scene(job['dedupe']) if self.demo else None
            if not scene or scene['client']!=job['client'] or scene['status']!='completed':
                return 'cancelled',None,'测试图片尚未完成核验，未发送结论'
            if now-scene['createdAt']>3600: return 'expired',None,'测试事件已超过即时提醒时效，证据仍保留'
        if kind=='camera_event':
            episode=self.ingest.episode(job.get('cameraEpisodeId') or job['dedupe']) if self.ingest else None
            if not episode or episode['status'] not in {'completed','metadata_only'}: return 'cancelled',None,'事件图片尚未核验，未发现场结论'
            events=self.ingest.events(episode['id'])
            if not events or now-max(e['metadata']['startMs']/1000 for e in events)>3600:
                return 'expired',None,'事件已超过即时提醒时效，证据仍保留'
            if not self.event_tasks(job,now):
                return 'cancelled',None,'事件已保存，没有匹配用户交代的关注事项，不打断聊天'
        skill = self.store.skill(job['skillId']) if job['skillId'] else None
        if skill and official_mode(getattr(self.runtime,'cameras',None)):
            ids=registered_device_ids(self.store)
            if not set(skill['devices'])<=ids or skill.get('replay'):
                return 'cancelled',None,'测试任务已退出当前事件来源，历史记录保留'
        if job['skillId'] and not skill: return 'cancelled',None,'任务已移除'
        if kind in {'event','followup'}:
            if not skill or skill.get('alert') != 'open': return 'cancelled',None,'新观察已解除此提醒'
            with self.store.lock:
                event = self.store.db.execute("SELECT id FROM events WHERE run_id=? AND type='alert_opened' ORDER BY id DESC LIMIT 1",(skill['id'],)).fetchone()
            if not event or str(event[0]) != job.get('episode',job['dedupe'].split(':')[-1]): return 'cancelled',None,'旧事件已被更新'
        if kind=='coverage' and (not skill or skill['status']!='active' or skill['result']!='unknown'):
            return 'cancelled',None,'观察已恢复或任务已停止'
        recent = self.messages(job['client'])
        if job.get('parentMessageId'):
            parent=next((m for m in recent if m['id']==job['parentMessageId']),None)
            if not parent or parent.get('feedback') in {'handled','dismiss'}: return 'cancelled',None,'该后续提醒已处理'
        if job['kind']=='followup':
            event_key='event:'+job['dedupe'].split(':')[-1]
            original=next((m for m in reversed(recent) if m.get('triggerKey')==event_key),None)
            if original is None: return 'deferred',now+60,'先处理同一事件的首次提醒'
            if original.get('feedback') in {'handled','dismiss'}: return 'cancelled',None,'用户已处理或不再需要此事件提醒'
            if original.get('feedback')=='snooze': return 'cancelled',None,'后续提醒已交给用户选择的定时复查'
        if self.quiet(p,now): return 'deferred',now+60,'免打扰期间暂存，之后重新核对状态'
        if job.get('report'): return None  # Explicit subscriptions have their own two-slot dedupe, not the unsolicited quota.
        if not publication: return None
        # Non-urgent assistant messages only: native security alarms are separate.
        day = datetime.fromtimestamp(now,ZoneInfo(p['timezone'])).date()
        if self.merge_target(job,now): return None
        start=datetime.combine(day,datetime.min.time(),ZoneInfo(p['timezone'])).timestamp()
        with self.store.lock:
            count=self.store.db.execute("SELECT COUNT(*) FROM assistant_messages WHERE client=? AND created_at>=? AND json_extract(payload,'$.report') IS NULL",(job['client'],start)).fetchone()[0]
        if count>=6: return 'deferred',now+3600,'今天的助手提醒已达频率上限'
        recent = [m for m in recent if not m.get('report')]
        if recent and now-recent[-1]['createdAt'] < 300: return 'deferred',recent[-1]['createdAt']+300,'两条提醒至少间隔5分钟，稍后重新检查'
        return None

    def merge_target(self, job, now):
        if job['kind'] in {'schedule','revisit'}: return None
        key=self.merge_key(job)
        return next((m for m in reversed(self.messages(job['client']))
                     if m.get('mergeKey')==key and now-m['createdAt']<600
                     and m.get('feedback') not in {'handled','dismiss','snooze'}),None)

    def merge_key(self, job):
        if job.get('sourceKind',job['kind'])=='camera_observation' and self.watch:
            observation=self.watch.observation(job.get('cameraObservationId') or job['dedupe'])
            if observation: return 'observation:'+observation['cameraId']
        if job.get('sourceKind',job['kind'])=='camera_event' and self.ingest:
            ep=self.ingest.episode(job.get('cameraEpisodeId') or job['dedupe'])
            if ep: return 'camera:'+ep['cameraId']+':'+ep['kind']
        return (job.get('skillId') or job['dedupe'])+':'+('event' if job['kind'] in {'event','followup'} else job['kind'])

    def sources(self, job, now):
        if job.get('report'):
            return briefings.facts(self.store, job['report'], now)
        if job.get('sourceKind',job['kind'])=='camera_observation' and self.watch:
            return self.watch.sources(job.get('cameraObservationId') or job['dedupe'])
        if job.get('sourceKind',job['kind'])=='demo_event' and self.demo:
            return self.demo.sources(job['dedupe'])
        if job.get('sourceKind',job['kind'])=='camera_event' and self.ingest:
            return self.ingest.sources(job.get('cameraEpisodeId') or job['dedupe']) + [
                dict(id=t['id'],type='requested_task',title=t['title'],cameraId=t['cameraId'],
                     observedAt=t['createdAt'],reason='用户主动交代的事件关注') for t in self.event_tasks(job,now)]
        skills = [s for s in self.store.skills() if not job['skillId'] or s['id']==job['skillId']][:20]
        if official_mode(getattr(self.runtime,'cameras',None)):
            ids=registered_device_ids(self.store)
            skills=[s for s in skills if set(s['devices'])<=ids and not s.get('replay')]
        result = [dict(id='trigger:'+job['dedupe'],type='camera_observation_trigger',title=job['title'],
                       observedAt=job['createdAt'],description=job['body'])]
        for skill in skills:
            result.append(dict(id='skill:'+skill['id'],type='task_state',skillId=skill['id'],name=skill['name'],
                               status=skill['status'],result=skill['result'],reason=skill['resultReason'],
                               observedAt=skill.get('lastObservedAt'),revision=skill['revision'],
                               limitation='运行器状态；不代表此刻现场或全天覆盖'))
            evidence,_ = self.store.historical_evidence(skill['id'],None,None,None,limit=2)
            for e in evidence:
                # Only already-saved images; no SDK writes or extra camera lease.
                result.append(dict(id='evidence:'+e['id'],type='camera_evidence',evidenceId=e['id'],
                                   skillId=skill['id'],cameraId=e['cameraId'],observedAt=e['capturedAt'],
                                   sourceType=e['sourceType'],reason=e['reason'],relation=e['relation'],
                                   imageUrl=e.get('imageUrl') if e.get('mediaStatus')=='saved' else None,
                                   limitation='离散采样；回放/模拟不是真实家庭现场'))
        if job['kind']=='schedule':
            with self.store.lock:
                rows=self.store.db.execute("SELECT payload FROM proactive_jobs WHERE client=? AND status='digest' ORDER BY rowid DESC LIMIT 12",(job['client'],)).fetchall()
            for (raw,) in rows:
                pending=json.loads(raw)
                if pending['expiresAt']<=now or self.gate(pending,now): continue
                # Carry the original, still-authorized facts and cached visual
                # receipt into the summary. A previous model draft is not an
                # image source or sufficient evidence on its own.
                original=self.sources(pending,now) if pending['kind']!='schedule' else []
                result.append(dict(id='digest:'+pending['id'],type='pending_summary',title=pending.get('assessment',{}).get('title'),
                                   description=pending.get('assessment',{}).get('body'),observedAt=pending['createdAt'],
                                   evidenceSourceIds=[s['id'] for s in original],
                                   limitation='待汇总草稿，不是新事实；核对同批附带的原始来源及已有视觉回执'))
                known={s['id'] for s in result}
                result.extend(s for s in original if s['id'] not in known)
        return result

    @staticmethod
    def state_fingerprint(sources):
        # New frames are expected every N seconds. An immutable old frame remains
        # evidence, but a changed task conclusion invalidates a pending message.
        return [{k:v for k,v in s.items() if k!='observedAt'} for s in sources if s['type']=='task_state']

    async def step(self, now=None):
        live_clock = now is None
        now = time.time() if now is None else now
        with self.store.transaction():
            row = self.store.db.execute("SELECT payload FROM proactive_jobs WHERE status IN ('pending','retry','deferred') AND due<=? ORDER BY due,rowid LIMIT 1",(now,)).fetchone()
            if not row: return False
            job = json.loads(row[0])
            blocked = self.gate(job,now)
            if blocked:
                self.save(job,*blocked[:2],reason=blocked[2]); return True
            job['attempts'] += 1
            profile = self.personal.profile(job['client'])
            sources = self.sources(job,now)
            context = dict(clientId=job['client'],now=now,sources=sources,
                           personal=self.personal.context(job['client']),
                           delivery='in_app',scope='shared internal demo cameras; installation-scoped preferences')
            fingerprint = hashlib.sha256(json.dumps(context['personal'],sort_keys=True).encode()).hexdigest()
            job['contextRevision']=profile['revision']
            self.save(job,'running')
        if job.get('report'):
            return await self.deliver_report(job, sources, context, fingerprint, now, live_clock)
        try:
            source_fingerprint=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
            cached=job.get('assessment')
            if job.get('sourceKind',job['kind'])=='camera_event' and self.event_tasks(job,now):
                from .personal_tasks import EVENT_LABELS
                ep=self.ingest.episode(job.get('cameraEpisodeId') or job['dedupe'])
                events=self.ingest.events(ep['id'])
                observed=max(e['metadata']['startMs']/1000 for e in events)
                stamp=datetime.fromtimestamp(observed,ZoneInfo(profile['preferences']['timezone'])).strftime('%m月%d日 %H:%M')
                label=EVENT_LABELS[ep['kind']]
                body=f'你交代的关注事项有新记录。摄像头在 {stamp} 报告了{label}。'
                body+= '可以打开事件画面核对；设备检测标签不等于已确认现场动作。' if any(e.get('imageUrl') for e in events) else '暂未取得事件图片，现场细节还需要核对。'
                decision=Decision(valueScore=100,title='关注的事件有新记录',body=body,
                                  reason='匹配用户明确交代的摄像头和事件类型',sourceIds=[s['id'] for s in sources[:12]])
            elif cached and job.get('assessmentContext')==fingerprint and job.get('assessmentSources')==source_fingerprint:
                decision=Decision.model_validate(cached)
            else:
                job['runId']=job['id']+f"-attempt-{job['attempts']}"
                decision = await self.runtime.proactive(job['runId'],context)
            job.update(assessment=decision.model_dump(),assessmentContext=fingerprint,assessmentSources=source_fingerprint)
        except asyncio.CancelledError:
            with self.store.transaction(): self.save(job,'retry',now+30,reason='服务暂停，恢复后重新检查')
            raise
        except Exception:
            with self.store.transaction(): self.save(job,'failed' if job['attempts']>=3 else 'retry',now+30*job['attempts'],reason='模型检查未完成；未发送消息，未操作设备')
            return True
        with self.store.transaction():
            current = time.time() if live_clock else now
            blocked = self.gate(job,current)
            if blocked:
                self.save(job,*blocked[:2],reason=blocked[2]); return True
            current_context=self.personal.context(job['client'])
            if fingerprint != hashlib.sha256(json.dumps(current_context,sort_keys=True).encode()).hexdigest() or self.state_fingerprint(self.sources(job,current)) != self.state_fingerprint(sources):
                self.save(job,'failed' if job['attempts']>=3 else 'retry',now+30,reason='来源或记忆已变化，重新检查后再提醒'); return True
            # The model never chooses a channel, send time, or policy exception.
            if decision.valueScore<50:
                self.save(job,'silent',reason='价值评分低于50，保留事件记录：'+decision.reason); return True
            # A user-subscribed daily summary can deliver useful digest items at
            # its scheduled time. Ordinary unsolicited events still require 80.
            if decision.valueScore<80 and job['kind']!='schedule':
                self.save(job,'digest',reason='价值评分50–79，等待用户开启的每日汇总：'+decision.reason); return True
            if not decision.title.strip() or not decision.body.strip():
                self.save(job,'failed',reason='消息不完整，未发布'); return True
            refs=[s for s in sources if s['id'] in decision.sourceIds]
            fixture=any(s.get('sourceType') in {'fixture','replay','synthetic_demo'} for s in sources)
            body=decision.body
            if fixture and '测试' not in body: body='测试场景：'+body
            message=dict(id='message-'+job['id'],jobId=job['id'],runId=job.get('runId'),role='assistant',
                         origin='proactive',kind=job['kind'],title=decision.title,body=body,
                         why=decision.reason,sources=refs,createdAt=current,read=False,feedback=None,
                         skillId=job['skillId'],triggerKey=job['dedupe'],delivery='in_app',valueScore=decision.valueScore,mergeKey=self.merge_key(job))
            previous=self.merge_target(job,current)
            if previous:
                message.update(id=previous['id'],jobId=previous['jobId'],createdAt=previous['createdAt'],updatedAt=current,
                               mergedCount=previous.get('mergedCount',1)+1)
                message['sources']=list({s['id']:s for s in previous['sources']+refs}.values())[-20:]
                self.store.db.execute('UPDATE assistant_messages SET payload=? WHERE id=?',(json.dumps(message,ensure_ascii=False),message['id']))
                self.store.db.execute('UPDATE personal_inbox SET payload=? WHERE id=?',(json.dumps(message,ensure_ascii=False),message['id']))
                self.save(job,'merged',reason='已合并到同类事件卡片；'+decision.reason); return True
            self.store.db.execute('INSERT OR IGNORE INTO assistant_messages VALUES (?,?,?,?,?)',
                                  (message['id'],job['client'],job['id'],current,json.dumps(message,ensure_ascii=False)))
            self.store.db.execute('INSERT OR IGNORE INTO personal_inbox VALUES (?,?,?,?)',
                                  (message['id'],job['client'],job['dedupe'],json.dumps(message,ensure_ascii=False)))
            if self.push: self.push.message(job['client'],message,job)
            self.save(job,'sent',reason='规则通过，价值评分'+str(decision.valueScore)+'：'+decision.reason)
            if job['kind']=='schedule':
                for source in refs:
                    if source['id'].startswith('digest:'):
                        self.store.db.execute("UPDATE proactive_jobs SET status='summarized' WHERE id=? AND client=? AND status='digest'",(source['id'][7:],job['client']))
        return True

    async def deliver_report(self, job, sources, context, fingerprint, now, live_clock):
        """A subscribed report survives model failure; publication remains atomic."""
        selected = []
        generation = 'model_ranked'
        job['runId'] = job['id']+f"-attempt-{job['attempts']}"
        context['report'] = job['report']
        try:
            sources = await briefings.review_pictures(sources, getattr(self.runtime,'visual_review',None), job['report'])
            context['sources'] = sources
            decision = await self.runtime.proactive(job['runId'], context)
            selected = decision.sourceIds
        except asyncio.CancelledError:
            with self.store.transaction(): self.save(job,'retry',now+30,reason='服务暂停，恢复后继续生成报告')
            raise
        except Exception:
            generation = 'facts_fallback'
        with self.store.transaction():
            current = time.time() if live_clock else now
            blocked = self.gate(job, current)
            if blocked:
                self.save(job,*blocked[:2],reason=blocked[2]); return True
            # Read fresh source facts under the publication lock. Ignore model
            # prose and old ranking when preferences/source state has changed.
            fresh = self.sources(job,current)
            reviewed = {s['id']:s for s in sources if s['type']=='report_picture'}
            for source in fresh:
                old = reviewed.get(source['id'])
                if old and all(source.get(k)==old.get(k) for k in ('cameraId','observedAt','imageUrl','sourceType')):
                    source['visualReview'] = old.get('visualReview')
            if fingerprint != hashlib.sha256(json.dumps(self.personal.context(job['client']),sort_keys=True).encode()).hexdigest():
                selected = []
                generation = 'facts_refreshed'
            rendered = briefings.render(job['report'], fresh, selected)
            message = dict(id='message-'+job['id'],jobId=job['id'],runId=job.get('runId'),role='assistant',
                           origin='proactive',kind='schedule',createdAt=current,read=False,feedback=None,
                           skillId=None,triggerKey=job['dedupe'],delivery='in_app',valueScore=None,
                           report=job['report'],generation=generation, **rendered)
            self.store.db.execute('INSERT OR IGNORE INTO assistant_messages VALUES (?,?,?,?,?)',
                                  (message['id'],job['client'],job['id'],current,json.dumps(message,ensure_ascii=False)))
            self.store.db.execute('INSERT OR IGNORE INTO personal_inbox VALUES (?,?,?,?)',
                                  (message['id'],job['client'],job['dedupe'],json.dumps(message,ensure_ascii=False)))
            if self.push: self.push.message(job['client'],message,job)
            self.save(job,'sent',reason='已按订阅生成报告；记录不足时明确说明，不按价值评分跳过')
        return True

    async def run(self):
        while True:
            try:
                self.personal.tick()
                for _ in range(8):
                    if not await self.step(): break
                self.personal.last_error=None
            except asyncio.CancelledError: raise
            except Exception: self.personal.last_error='主动检查暂未更新，正在重试'
            await asyncio.sleep(10)
