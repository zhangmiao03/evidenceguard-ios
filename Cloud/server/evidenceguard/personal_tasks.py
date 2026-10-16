"""Persistent delegated requests, scoped to the installation that requested them.

Event watches only match new uploaded SDK events. Saving does not start a camera
or override notification preferences; unsupported requests remain unconfigured.
"""
import json
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

EVENT_LABELS = {'package_put':'包裹出现', 'package_take':'包裹移走', 'ring':'门铃响',
                'human':'人物活动', 'pet':'宠物活动', 'vehicle':'车辆活动', 'motion':'画面活动'}


class PersonalTasks:
    def __init__(self, store):
        self.store = store
        with store.transaction():
            store.db.execute('''CREATE TABLE IF NOT EXISTS personal_tasks (
                id TEXT PRIMARY KEY, client TEXT NOT NULL, run_id TEXT NOT NULL,
                payload TEXT NOT NULL, UNIQUE(client,run_id))''')

    def list(self, client, now=None):
        now = time.time() if now is None else now
        with self.store.lock:
            rows = self.store.db.execute('SELECT payload FROM personal_tasks WHERE client=? ORDER BY rowid DESC LIMIT 100', (client,)).fetchall()
        values = [json.loads(r[0]) for r in rows]
        for item in values:
            if item['status'] != 'cancelled' and item.get('expiresAt') and now >= item['expiresAt']:
                item.update(status='expired', reason='关注时段已结束，历史记录保留')
        return values

    def create(self, client, run, title, event_type, camera_id, period, timezone, now=None):
        now = time.time() if now is None else now
        if not client or run.get('clientId') != client or run.get('executionMode') != 'live':
            raise ValueError('只能在本人的现场对话保存交代事项')
        with self.store.transaction():
            existing = self.store.db.execute('SELECT payload FROM personal_tasks WHERE client=? AND run_id=?', (client,run['id'])).fetchone()
            if existing: return json.loads(existing[0])
            if sum(t['status'] in {'waiting_events','needs_setup'} for t in self.list(client,now)) >= 100:
                raise ValueError('待处理事项已达100条，请先结束不再需要的任务')
            expires = None
            if period == 'today':
                local = datetime.fromtimestamp(now,ZoneInfo(timezone))
                expires = (local.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)).timestamp()
            elif period == 'next_24_hours': expires = now+86400
            ready = event_type in EVENT_LABELS and bool(camera_id)
            item = dict(id='task-'+uuid.uuid4().hex, title=title, instruction=run['message'],
                        conversationId=run['conversationId'], sourceRunId=run['id'],
                        eventType=event_type, cameraId=camera_id, createdAt=now, expiresAt=expires,
                        status='waiting_events' if ready else 'needs_setup',
                        reason=('已保存，等待这台摄像头的新事件。需在摄像头页开启前台事件同步，通知仍遵循提醒设置；锁屏后不保证持续接收。'
                                if ready else '需求已保存，尚未启用。请继续和助手明确摄像头、可检测事件或完成场景配置。'))
            self.store.db.execute('INSERT INTO personal_tasks VALUES (?,?,?,?)', (item['id'],client,run['id'],json.dumps(item,ensure_ascii=False)))
            return item

    def cancel(self, client, key):
        with self.store.transaction():
            row = self.store.db.execute('SELECT payload FROM personal_tasks WHERE id=? AND client=?',(key,client)).fetchone()
            if not row: raise KeyError(key)
            item=json.loads(row[0]); item.update(status='cancelled',reason='已结束关注，历史记录保留')
            self.store.db.execute('UPDATE personal_tasks SET payload=? WHERE id=? AND client=?',(json.dumps(item,ensure_ascii=False),key,client))

    def matching(self, client, episode, observed_at, now):
        return [t for t in self.list(client,now) if t['status']=='waiting_events'
                and t['cameraId']==episode['cameraId'] and t['eventType']==episode['kind']
                and t['createdAt'] <= observed_at <= now
                and (t['expiresAt'] is None or observed_at<t['expiresAt'])]
