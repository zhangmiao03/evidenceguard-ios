#!/usr/bin/env python3
"""Create an owned synthetic playback sample in the isolated review database.

Run with the cloud virtualenv as evidenceguard-review. This exercises ingestion
and embedding, not real-camera recognition or Skill acceptance.
"""
import asyncio
import argparse
import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--environment', choices=['review','demo'], default='review')
args = parser.parse_args()
root = Path('/var/lib/evidenceguard-'+args.environment)
env = Path('/etc/evidenceguard-'+args.environment+'/cloud.env')
if not root.is_dir() or not env.is_file():
    raise SystemExit('Run cloud_review_setup.sh on the cloud host first.')
load_dotenv(env, override=True)
if Path(os.environ['EG_DATABASE']).parent != root:
    raise SystemExit('Refuse to modify a database outside the isolated review directory.')
sys.path.insert(0, '/opt/evidenceguard-demo/Cloud/server' if args.environment == 'demo' else '/opt/evidenceguard/Cloud/server')
from evidenceguard.store import Store
from evidenceguard.video.service import VideoService


async def main():
    original = root / 'synthetic-review-fixture.mp4'
    if not original.exists():
        # All pixels are generated here. No third-party or team recordings.
        filters = [
            'drawbox=x=0:y=225:w=640:h=135:color=0x64748b:t=fill',
            'drawbox=x=455:y=65:w=115:h=160:color=0x334155:t=fill',
            "drawbox=x=250:y=185:w=90:h=75:color=0xb77943:t=fill:enable='gte(t,1)*lt(t,6)'",
            "drawbox=x=285:y=185:w=12:h=75:color=0xd8b489:t=fill:enable='gte(t,1)*lt(t,6)'",
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='SYNTHETIC TEST FIXTURE':x=15:y=14:fontsize=20:fontcolor=0x0f172a",
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='Not a camera recording':x=15:y=43:fontsize=16:fontcolor=0x0f172a",
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='%{pts\\:hms}':x=15:y=320:fontsize=19:fontcolor=white",
        ]
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=0xcbd5e1:s=640x360:r=6:d=10',
                        '-vf', ','.join(filters), '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(original)], check=True)
    store = Store(Path(os.environ['EG_DATABASE']))
    videos = VideoService(store, os.environ['EG_VIDEO_ROOT'])
    try:
        reference = 'generated:EvidenceGuard/synthetic-review-fixture-v1'
        recording = next((r for r in videos.db.recordings() if r.get('sourceReference') == reference), None)
        if not recording:
            recording = videos.stage(original, 'cam-b', recorded_at=None,
                                     title='合成测试录像 · 非摄像头实拍',
                                     source_type='synthetic_review', source_reference=reference)
        if recording['status'] != 'ready':
            recording = await videos.index(recording['id'])
        print('Review recording:', recording['id'])
        print('Index status:', recording['status'])
        print('Source: synthetic_review; original capture date: unknown')
    finally:
        await videos.shutdown()
        store.close()


asyncio.run(main())
