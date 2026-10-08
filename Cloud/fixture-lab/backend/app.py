import asyncio
import copy
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, model_validator

from .domain import evaluate, new_task, reset_pending
from .simulator import RTSPReader, SCENARIOS, Simulator
from .storage import Store
from .vision import analyze, read_stamp

ROOT = Path(__file__).resolve().parent.parent


class Runtime:
    def __init__(self, data_dir: Path):
        self.store = Store(data_dir)
        self.task = self.store.get('task') or new_task(time.time())
        if self.task['lifecycle'] == 'active':
            reset_pending(self.task, time.time(), '服务已恢复，等待新的设备证据')
        self.settings = self.store.get('settings') or {'scenario': 'normal', 'mode': 'continuous'}
        url = os.getenv('EG_RTSP_URL', 'rtsp://127.0.0.1:18554')
        self.sim = Simulator(self.settings, url)
        self.readers = {c: RTSPReader(c, url) for c in ('cam-a','cam-b')}
        self.latest = {}
        self.last_seen = {}
        self.commands = []
        self.last_primary_request = 0
        self.last_secondary_request = 0
        self.supplement_attempts = 0
        self.jobs = []
        self.last_tick = 0.
        self.last_prune = 0.
        self.worker_error = None
        self.store.save(self.task, self.settings)

    def event(self, kind, text, **extra):
        event = dict(type=kind, text=text, at=time.time(), revision=self.task['revision'],
                     evidence=copy.deepcopy(self.task['evidence']))
        event.update(extra)
        self.store.append(event)

    def command(self, camera, reason):
        now = time.time()
        outcome = self.sim.request(camera, now)
        c = dict(id=f'cmd-{time.time_ns()}', device_id=camera, requested_at=now,
                 expires_at=now+5, status=outcome, reason=reason, frame_id=None)
        self.commands.append(c)
        self.commands = self.commands[-40:]
        self.event('snapshot_requested', f'{camera.upper()} 新图请求：{outcome}', command=copy.deepcopy(c))
        return c

    async def run(self):
        while True:
            try:
                await self.tick()
                self.worker_error = None
            except Exception as exc:
                self.worker_error = f'{type(exc).__name__}: {exc}'
                import logging
                logging.exception('watch worker failed')
                reset_pending(self.task, time.time(), '观察处理失败，等待恢复')
            await asyncio.sleep(.65)

    async def tick(self):
        now = time.time()
        self.last_tick = now
        for camera, reader in self.readers.items():
            if reader.latest is None:
                continue
            # Copy the current bounded slot; the pixel timestamp is preserved across RTSP.
            rgb = reader.latest.copy()
            captured_at, generation = read_stamp(rgb)
            if not 1_600_000_000 < captured_at <= now+.5:
                continue
            frame_id = f'{camera}-{generation}-{int(captured_at*1000)}'
            if self.last_seen.get(camera) == frame_id:
                continue
            existing = self.latest.get(camera)
            if existing and captured_at <= existing.captured_at:
                continue
            self.last_seen[camera] = frame_id
            packet = dict(frame_id=frame_id, device_id=camera, captured_at=captured_at,
                          received_at=reader.received_at, revision=self.task['revision'])
            observation = analyze(rgb, packet, self.task)
            self.latest[camera] = observation
            Image.fromarray(rgb).save(self.store.images / f'{frame_id}.jpg', quality=84)
            self.store.frame(frame_id, asdict(observation))
        for cmd in self.commands:
            if cmd['status'] != 'accepted':
                continue
            obs = self.latest.get(cmd['device_id'])
            if obs and cmd['requested_at'] <= obs.captured_at <= cmd['expires_at']:
                cmd.update(status='completed', frame_id=obs.frame_id, frame=asdict(obs))
                self.event('snapshot_completed', '已收到请求后的新画面', command=copy.deepcopy(cmd), evidence=[asdict(obs)])
            elif now > cmd['expires_at']:
                cmd['status'] = 'timed_out'
                self.event('snapshot_timeout', '新图请求超时，未获得有效新证据', command=copy.deepcopy(cmd))
        if self.task['lifecycle'] == 'active':
            primary = self.latest.get('cam-a')
            if self.settings['mode'] == 'on_demand' and now-self.last_primary_request >= 3:
                self.command('cam-a', '按需观察调度')
                self.last_primary_request = now
            ambiguous = (not primary or primary.relation == 'unknown' or
                         now-primary.captured_at > self.task['freshness_seconds'])
            if ambiguous and now-self.last_secondary_request > 6 and self.supplement_attempts < 3:
                self.command('cam-b', '主视角无法确认，请求第二视角')
                self.last_secondary_request = now
                self.supplement_attempts += 1
            elif not ambiguous:
                self.supplement_attempts = 0
        events = evaluate(self.task, self.latest, now)
        self.store.save(self.task, self.settings, events)
        if now-self.last_prune > 60:
            self.store.prune_unreferenced(now-900, {o.frame_id for o in self.latest.values()})
            self.last_prune = now

    def snapshot(self):
        now = time.time()
        cameras = []
        for camera, reader in self.readers.items():
            obs = self.latest.get(camera)
            age = round(now-obs.captured_at, 1) if obs else None
            transport_online = reader.connected and now-reader.received_at < 4
            cameras.append(dict(id=camera, label='主视角' if camera == 'cam-a' else '补证视角',
                                expected_model='T8171' if camera == 'cam-a' else 'T8214',
                                transport_online=transport_online, age=age,
                                fresh=age is not None and age <= self.task['freshness_seconds'],
                                observation=asdict(obs) if obs else None,
                                image_url=f'/api/frames/{obs.frame_id}.jpg' if obs else None,
                                error=reader.error if not transport_online else '',
                                roi=self.task['roi'][camera], source_type='fixture'))
        return dict(now=now, task=self.task, settings=self.settings, cameras=cameras,
                    events=self.store.events(), commands=self.commands[-8:],
                    scenarios=SCENARIOS, worker=dict(last_tick=self.last_tick, error=self.worker_error),
                    limitations=['合成素材，经真实 RTSP 输送', 'ArUco 标记检测，尚非通用箱子识别',
                                 'T8171 / T8214 正式 SDK 待接入', '本地后端运行，尚未部署公网云服务'])


class SimulationInput(BaseModel):
    scenario: str | None = None
    mode: Literal['continuous','on_demand','event_only'] | None = None


class TaskInput(BaseModel):
    revision: int
    title: str = Field(min_length=1, max_length=60)
    roi: dict[str, list[float]]

    @model_validator(mode='after')
    def valid_roi(self):
        if set(self.roi) != {'cam-a','cam-b'}:
            raise ValueError('需要两个视角各自的区域')
        for r in self.roi.values():
            if len(r) != 4 or not all(0 <= n <= 1 for n in r):
                raise ValueError('区域坐标须为四个 0 到 1 之间的数值')
            if r[2]-r[0] < .05 or r[3]-r[1] < .05:
                raise ValueError('区域太小或坐标顺序错误')
        return self


class CaptureInput(BaseModel):
    camera_id: Literal['cam-a', 'cam-b']
    reason: str = Field(default='Agent 请求新画面', max_length=120)


class ActionInput(BaseModel):
    action: Literal['pause','resume','recheck']


def create_app(data_dir: Path | None = None, start_workers=True):
    @asynccontextmanager
    async def lifespan(app):
        runtime = Runtime(data_dir or Path(os.getenv('EG_DATA_DIR', str(ROOT/'data'))))
        app.state.runtime = runtime
        if start_workers:
            runtime.jobs = [asyncio.create_task(runtime.sim.run()),
                            *[asyncio.create_task(r.run()) for r in runtime.readers.values()],
                            asyncio.create_task(runtime.run())]
        try:
            yield
        finally:
            for job in runtime.jobs:
                job.cancel()
            await asyncio.gather(*runtime.jobs, return_exceptions=True)
            runtime.store.close()

    app = FastAPI(title='EvidenceGuard Camera Lab', version='0.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def local_guard(request: Request, call_next):
        # Local prototype: prevent unrelated web origins from driving simulator controls.
        origin = request.headers.get('origin')
        host = request.headers.get('host', '')
        if origin and origin not in (f'http://{host}', f'https://{host}'):
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/api/health')
    async def health(request: Request):
        r = request.app.state.runtime
        return dict(ok=not r.worker_error, version='0.1.0', source='fixture', deployment='local')

    @app.get('/api/state')
    async def state(request: Request):
        return request.app.state.runtime.snapshot()

    @app.get('/api/events')
    async def events(request: Request, after: int = 0):
        return request.app.state.runtime.store.events(after=after)

    @app.post('/api/cameras/snapshot')
    async def capture(body: CaptureInput, request: Request):
        return request.app.state.runtime.command(body.camera_id, body.reason)

    @app.get('/api/cameras/requests/{request_id}')
    async def capture_receipt(request_id: str, request: Request):
        command = next((c for c in request.app.state.runtime.commands if c['id'] == request_id), None)
        if not command: raise HTTPException(404, '画面请求不存在或已过期')
        return command

    @app.post('/api/simulation')
    async def simulation(body: SimulationInput, request: Request):
        r = request.app.state.runtime
        if body.scenario and body.scenario not in SCENARIOS:
            raise HTTPException(422, '未知场景')
        if body.scenario:
            r.settings['scenario'] = body.scenario
        if body.mode:
            r.settings['mode'] = body.mode
        r.sim.change()
        r.supplement_attempts = 0
        r.last_secondary_request = 0
        r.event('scenario_changed', f"模拟设置：{SCENARIOS[r.settings['scenario']]} / {r.settings['mode']}")
        r.store.save(r.task, r.settings)
        return r.snapshot()

    @app.post('/api/task')
    async def task(body: TaskInput, request: Request):
        r = request.app.state.runtime
        if body.revision != r.task['revision']:
            raise HTTPException(409, '任务版本已更新，请刷新后修改')
        if r.task['alert'] in ('open','acknowledged'):
            raise HTTPException(409, '当前有未解决告警，请先恢复并复核后再修改区域')
        r.task.update(title=body.title, roi=body.roi, revision=r.task['revision']+1)
        reset_pending(r.task, time.time(), '区域规则已更新，等待新版本证据')
        r.latest.clear()
        r.event('skill_revised', '已确认新的守护区域', roi=body.roi)
        r.store.save(r.task, r.settings)
        return r.snapshot()

    @app.post('/api/task/action')
    async def action(body: ActionInput, request: Request):
        r = request.app.state.runtime
        if body.action == 'pause':
            r.task['lifecycle'] = 'paused'
            r.event('task_paused', '已暂停守护，保留历史告警')
        else:
            r.task['lifecycle'] = 'active'
            if body.action == 'recheck' and r.task['alert'] == 'open':
                r.task['alert'] = 'acknowledged'
            reset_pending(r.task, time.time(), '等待复核所需的新画面')
            r.command('cam-a', '用户请求重新观察')
            r.command('cam-b', '用户请求重新观察')
            r.event('recheck_requested', '已发起重新观察，尚未确认恢复')
        r.store.save(r.task, r.settings)
        return r.snapshot()

    @app.get('/api/frames/{filename}')
    async def frame(filename: str, request: Request):
        if not re.fullmatch(r'cam-[ab]-\d+-\d+\.jpg', filename):
            raise HTTPException(404)
        path = request.app.state.runtime.store.images / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={'Cache-Control': 'private, max-age=86400'})

    dist = ROOT / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app


app = create_app()
