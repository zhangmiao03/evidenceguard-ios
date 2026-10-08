"""Causal, paced file replay. Never returns bytes past the requested cursor."""
from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path
from ...video.service import command

@dataclass(frozen=True)
class VideoWindow:
    device_id: str
    recording_id: str
    start: float
    end: float
    path: Path
    observed_at: float
    source_type: str = 'replay'

class ReplayAdapter:
    def __init__(self, videos): self.videos=videos
    async def window(self, device_id, recording_id, start, end, context, region):
        r=self.videos.db.recording(recording_id)
        if r['cameraId']!=device_id: raise ValueError('回放录像与摄像头身份不符')
        if not 0<=start<end<=r['duration'] or end-start>12.001: raise ValueError('回放窗口越界')
        if time.time()>context.deadline: raise ValueError('回放请求已过期')
        directory=self.videos.root/recording_id/'replay'/context.execution_epoch
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/f'{start:.3f}-{end:.3f}.mp4'
        # Exact duration, no looping, no future frames. Blue rectangle is the user-selected ROI.
        box=f"drawbox=x=iw*{region['x']}:y=ih*{region['y']}:w=iw*{region['width']}:h=ih*{region['height']}:color=blue:t=3"
        if not path.exists():
            temp=path.with_suffix('.building.mp4')
            await command('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-protocol_whitelist','file,pipe',
                '-i',str(self.videos.file(recording_id)),'-t',str(end-start),'-an','-vf',box,'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(temp))
            temp.replace(path)
        return VideoWindow(device_id,recording_id,start,end,path,time.time())

    async def sample(self,device_id,recording_id,at,context,region):
        r=self.videos.db.recording(recording_id)
        if r['cameraId']!=device_id or not 0<=at<r['duration']:raise ValueError('抽样位置或设备无效')
        if time.time()>context.deadline:raise ValueError('抽样请求已过期')
        directory=self.videos.root/recording_id/'replay'/context.execution_epoch
        directory.mkdir(parents=True,exist_ok=True);path=directory/f'sample-{at:.3f}.jpg'
        # Select only frames at or before the requested source time; last retained
        # frame is written. No hidden 2 fps video is sent to the guard model.
        box=f"select=lte(t\\,{at}),drawbox=x=iw*{region['x']}:y=ih*{region['y']}:w=iw*{region['width']}:h=ih*{region['height']}:color=blue:t=3"
        await command('ffmpeg','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe','-i',str(self.videos.file(recording_id)),
            '-t',f'{at+.000001:.6f}','-vf',box,'-fps_mode','passthrough','-update','1','-q:v','3',str(path))
        if not path.is_file():raise ValueError('此位置没有可用画面')
        return VideoWindow(device_id,recording_id,at,at,path,time.time())
