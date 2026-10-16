"""Persisted, bounded visual reviews of already-ingested images.

The budget is for automatic observation, not a safety guarantee. Exhaustion is
an explicit unknown result. Retrying a failed provider call still consumes quota.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone


class VisualReview:
    DAILY_LIMIT = 100
    EVENT_LIMIT = 2

    def __init__(self, store, provider):
        self.store, self.provider = store, provider
        self.lock = asyncio.Lock()
        with store.transaction():
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS visual_usage (
                    id INTEGER PRIMARY KEY, camera TEXT NOT NULL, episode TEXT NOT NULL,
                    day TEXT NOT NULL, at REAL NOT NULL, images INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS visual_usage_day ON visual_usage(camera,day);
                CREATE TABLE IF NOT EXISTS visual_cache (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

    def reserve(self, camera, episode, images=1, now=None, event_limit=EVENT_LIMIT):
        now = time.time() if now is None else now
        day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        with self.store.transaction():
            daily = self.store.db.execute('SELECT COUNT(*) FROM visual_usage WHERE camera=? AND day=?',(camera,day)).fetchone()[0]
            event = self.store.db.execute('SELECT COUNT(*) FROM visual_usage WHERE camera=? AND episode=?',(camera,episode)).fetchone()[0]
            if daily >= self.DAILY_LIMIT: return '当日自动视觉核验额度已用完，图片已保存但尚未核验'
            if event >= event_limit: return '本次观察已达到核验次数上限，需人工查看证据'
            self.store.db.execute('INSERT INTO visual_usage(camera,episode,day,at,images) VALUES (?,?,?,?,?)',(camera,episode,day,now,images))
        return None

    def usage(self, camera, now=None):
        day = datetime.fromtimestamp(now or time.time(),timezone.utc).date().isoformat()
        with self.store.lock:
            row = self.store.db.execute('SELECT COUNT(*),COALESCE(SUM(images),0) FROM visual_usage WHERE camera=? AND day=?',(camera,day)).fetchone()
        return dict(requests=row[0],images=row[1],limit=self.DAILY_LIMIT,day=day,timezone='UTC')

    async def review(self, camera, episode, sources):
        # A source is (media key, observation time). Cache is also bound to model
        # and timestamps; duplicate ingest or follow-up does not pay to look again.
        sources = sources[:3]
        report = episode.startswith('report-')
        key = hashlib.sha256(json.dumps([camera,episode,sources,getattr(self.provider,'model',''),getattr(self.provider,'base',''),'report-visual-v1' if report else 'visual-review-v2'],sort_keys=True).encode()).hexdigest()
        async with self.lock:
            with self.store.lock:
                row = self.store.db.execute('SELECT payload FROM visual_cache WHERE id=?',(key,)).fetchone()
            if row: return json.loads(row[0]) | {'cached':True}
            if not self.provider.ready: return dict(status='unavailable',reason='视觉模型尚未就绪，图片保留待核验')
            frames=[]
            for media_key, at in sources:
                raw,mime,_ = self.store.media(media_key)
                frames.append((raw,mime,at))
            if not frames: return dict(status='unavailable',reason='本次观察没有可用图片，未调用视觉模型')
            reason = self.reserve(camera,episode,len(frames))
            if reason: return dict(status='budget_exhausted',reason=reason)
            try:
                review = await self.provider.describe_observations(frames, **({'report':True} if report else {}))
            except asyncio.CancelledError: raise
            except Exception:
                return dict(status='unavailable',reason='视觉核验未完成；没有把失败当作正常')
            result = dict(status='completed',review=review,cached=False,
                          limitation='核验仅针对所给离散图片；来源与时间以调用方回执为准，不能证明持续状态或完整现场')
            with self.store.transaction():
                self.store.db.execute('INSERT OR REPLACE INTO visual_cache VALUES (?,?)',(key,json.dumps(result,ensure_ascii=False)))
            return result
