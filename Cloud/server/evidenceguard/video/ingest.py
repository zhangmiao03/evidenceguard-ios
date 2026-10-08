"""Local import entry point: python -m evidenceguard.video.ingest --help."""
import argparse, asyncio, json, os
from pathlib import Path
from dotenv import load_dotenv
from ..store import Store
from .service import VideoService

async def main():
    p=argparse.ArgumentParser()
    p.add_argument('file',type=Path); p.add_argument('--camera-id',required=True)
    p.add_argument('--recorded-at',type=float,help='真实采集开始时间 Unix 秒；未知时不要填写')
    p.add_argument('--title',default='导入录像'); p.add_argument('--source-type',default='uploaded')
    p.add_argument('--source-reference'); p.add_argument('--inspect-query',help='额外使用 Lite 直接分析完整视频，输出动作与时间点')
    args=p.parse_args()
    if os.getenv('EG_ENV_FILE'): load_dotenv(os.environ['EG_ENV_FILE'])
    db=Path(os.environ['EG_DATABASE']); store=Store(db)
    service=VideoService(store,os.getenv('EG_VIDEO_ROOT',str(db.parent/'recordings')))
    try:
        recording=service.stage(args.file,args.camera_id,args.recorded_at,args.title,args.source_type,args.source_reference)
        result=await service.index(recording['id']); print(json.dumps(result,ensure_ascii=False),flush=True)
        if args.inspect_query and result.get('duration'):
            result=await service.vision.verify(service.file(recording['id']),args.inspect_query,result['duration'])
            print(json.dumps({'inspection':result},ensure_ascii=False),flush=True)
    finally: await service.shutdown(); store.close()

if __name__=='__main__': asyncio.run(main())
