"""Fixture camera behavior and pixels. Never imports the task state engine."""
import asyncio
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .vision import DICTIONARY, WIDTH, HEIGHT, stamp

SCENARIOS = {
    'normal': '箱子在区内', 'moved': '箱子移出区域', 'occluded_a': 'A 遮挡，B 补证',
    'hidden_both': '两个视角遮挡', 'lookalike': '相似箱子干扰', 'conflict': '两个视角冲突',
    'old_b': 'A 遮挡，B 返回旧图', 'offline_a': 'A 断流', 'offline_both': '两个设备断流',
}


async def stop_process(process):
    """FFmpeg may be blocked on a pipe; drain it and bound shutdown before reconnecting."""
    if process.stdin:
        process.stdin.close()
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.communicate(), 1.5)
    except asyncio.TimeoutError:
        if process.returncode is None:
            process.kill()
        await process.communicate()


def render(camera: str, scenario: str, at: float, generation: int) -> np.ndarray:
    im = Image.new('RGB', (WIDTH, HEIGHT), '#d9e2df')
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 640, 88), fill='#aebebb')
    for x in range(0, 700, 80):
        d.line((x, 88, x-120, 400), fill='#cad5d1', width=2)
    for y in [112, 165, 227, 300, 380]:
        d.line((0, y, 640, y), fill='#cad5d1', width=2)
    d.rounded_rectangle((25, 15, 112, 77), radius=8, fill='#6c817a')
    d.rectangle((36, 25, 100, 67), fill='#91a991')
    d.rounded_rectangle((489, 14, 613, 96), radius=4, fill='#8c9c96')
    d.rectangle((508, 15, 595, 84), fill='#596e66')
    d.ellipse((515, 103, 617, 129), fill='#bdc9c0')
    d.ellipse((535, 64, 597, 116), fill='#6a8c73')
    moved = scenario == 'moved' or (scenario == 'conflict' and camera == 'cam-a')
    x, y = (500 if moved else 267), 206
    if camera == 'cam-b':
        x = 640-x
        if moved:
            x = 82
        y = 202
    d.rounded_rectangle((x-65, y-50, x+76, y+63), radius=8, fill='#b4beb4')
    d.rectangle((x-65, y-57, x+65, y+52), fill='#b9793c')
    d.polygon([(x-65,y-57),(x-48,y-74),(x+79,y-74),(x+65,y-57)], fill='#e2af75')
    d.polygon([(x+65,y-57),(x+79,y-74),(x+79,y+34),(x+65,y+52)], fill='#9a602e')
    marker_id = 23 if scenario == 'lookalike' else 17
    marker = cv2.aruco.generateImageMarker(DICTIONARY, marker_id, 64)
    d.rectangle((x-39,y-38,x+39,y+40), fill='white')
    im.paste(Image.fromarray(marker).convert('RGB'), (x-32,y-31))
    hidden = scenario == 'hidden_both' or (scenario in ('occluded_a','old_b') and camera == 'cam-a')
    if hidden:
        d.rounded_rectangle((x-76,y-100,x+82,y+89), radius=37, fill='#4a5960')
        d.ellipse((x-35,y-140,x+39,y-67), fill='#83928c')
        d.line((x-20,y+70,x-34,y+137), fill='#37484d', width=34)
        d.line((x+35,y+70,x+46,y+137), fill='#37484d', width=34)
    d.rounded_rectangle((18, 12, 236, 37), radius=6, fill='#263f36')
    d.text((29, 20), f'{camera.upper()}  /  SYNTHETIC FIXTURE', fill='#edf6ed')
    d.text((428, 385), time.strftime('%H:%M:%S', time.localtime(at)), fill='#375247')
    rgb = np.array(im)
    stamp(rgb, at, generation)
    return rgb


class Simulator:
    def __init__(self, settings: dict, base_url: str):
        self.settings = settings
        self.base_url = base_url
        self.generation = int(time.time()) % 60000
        self.event_until = time.time()+3
        self.demand_until = {'cam-a': 0., 'cam-b': 0.}
        self.cached = {}
        self.publishers = {}
        self.closed = False
        self.last_error = ''

    def change(self):
        self.generation = (self.generation+1) % 65536
        self.event_until = time.time()+3
        # Retain stale B with its original capture timestamp, never stamp it as fresh.

    def request(self, camera: str, now: float):
        if self.settings['mode'] == 'event_only':
            return 'unsupported'
        if self.offline(camera):
            return 'failed'
        self.demand_until[camera] = now+2.5
        return 'accepted'

    def offline(self, camera):
        return self.settings['scenario'] == 'offline_both' or (self.settings['scenario'] == 'offline_a' and camera == 'cam-a')

    async def publisher(self, camera):
        return await asyncio.create_subprocess_exec(
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
            '-pix_fmt', 'rgb24', '-s', f'{WIDTH}x{HEIGHT}', '-r', '4', '-i', 'pipe:0',
            '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p', '-g', '4', '-f', 'rtsp', '-rtsp_transport', 'tcp',
            f'{self.base_url}/{camera}', stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)

    async def run(self):
        try:
            while not self.closed:
                start = time.time()
                for camera in ('cam-a','cam-b'):
                    p = self.publishers.get(camera)
                    if self.offline(camera):
                        if p and p.returncode is None:
                            await stop_process(p)
                        self.publishers.pop(camera, None)
                        continue
                    if p is None or p.returncode is not None:
                        p = self.publishers[camera] = await self.publisher(camera)
                    fresh = (self.settings['mode'] == 'continuous' or
                             start < self.demand_until[camera] or start < self.event_until)
                    if self.settings['scenario'] == 'old_b' and camera == 'cam-b':
                        fresh = False
                    if fresh:
                        self.cached[camera] = render(camera, self.settings['scenario'], start, self.generation)
                    if camera not in self.cached:
                        # Explicitly old initial image cannot satisfy a watch created now.
                        self.cached[camera] = render(camera, 'normal', start-30, self.generation)
                    try:
                        p.stdin.write(self.cached[camera].tobytes())
                        await asyncio.wait_for(p.stdin.drain(), 1)
                    except (BrokenPipeError, ConnectionResetError, asyncio.TimeoutError):
                        self.last_error = 'MediaMTX 推流连接不可用，正在重试'
                        await stop_process(p)
                        self.publishers.pop(camera, None)
                await asyncio.sleep(max(.01, .25-(time.time()-start)))
        finally:
            for p in self.publishers.values():
                await stop_process(p)


class RTSPReader:
    """One bounded latest-frame slot per camera; no unbounded backlog."""
    def __init__(self, camera: str, base_url: str):
        self.camera, self.base_url = camera, base_url
        self.latest = None
        self.received_at = 0.
        self.connected = False
        self.error = '等待连接'

    async def run(self):
        while True:
            p = None
            try:
                p = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-rtsp_transport', 'tcp',
                    '-timeout', '5000000', '-analyzeduration', '100000', '-probesize', '65536',
                    '-flags', 'low_delay', '-i', f'{self.base_url}/{self.camera}',
                    '-an', '-vf', f'scale={WIDTH}:{HEIGHT}', '-pix_fmt', 'rgb24',
                    '-f', 'rawvideo', 'pipe:1', stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, limit=WIDTH*HEIGHT*6)
                while True:
                    raw = await asyncio.wait_for(p.stdout.readexactly(WIDTH*HEIGHT*3), 6)
                    self.latest = np.frombuffer(raw, np.uint8).reshape(HEIGHT, WIDTH, 3).copy()
                    self.received_at = time.time()
                    self.connected, self.error = True, ''
            except (asyncio.IncompleteReadError, asyncio.TimeoutError, OSError):
                self.connected, self.error = False, '取流中断，正在重连'
            finally:
                if p:
                    await stop_process(p)
            await asyncio.sleep(1)
