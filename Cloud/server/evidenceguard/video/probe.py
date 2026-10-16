"""Run real configured models against synthetic media in a temporary database.

PYTHONPATH=Cloud/server python -m evidenceguard.video.probe --output result.json
No deployment, real camera operation, application database mutation or quality
claim. Loads EG_ENV_FILE privately, prints only contract/timing diagnostics.
"""
import argparse, asyncio, io, json, math, os, tempfile, time
from pathlib import Path
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from ..store import Store
from .providers import ArkVideoEmbedding, LiteVideoProvider, VideoProviderError
from .service import VideoService, command
from .search import SearchInput


async def probe(root):
    image=Image.new('RGB',(320,240),'white')
    ImageDraw.Draw(image).rectangle((100,60,220,180),fill='blue')
    frame=root/'reference.jpg'; image.save(frame)
    video=root/'sample.mp4'
    await command('ffmpeg','-hide_banner','-loglevel','error','-loop','1','-i',str(frame),'-t','4',
        '-r','5','-c:v','libx264','-pix_fmt','yuv420p',str(video))
    class ProbeVision(LiteVideoProvider):
        def __init__(self): super().__init__(); self.errors=[]
        async def verify(self,*args,**kwargs):
            try: return await super().verify(*args,**kwargs)
            except VideoProviderError as error:
                self.errors.append(dict(code=error.code,diagnostics=error.diagnostics)); raise
    embed=ArkVideoEmbedding(); vision=ProbeVision()
    if not embed.ready or not vision.ready: raise ValueError('需要配置 Embedding 和视频核验模型')
    report=dict(syntheticOnly=True,qualityAcceptance=False,embeddingModel=embed.model,visionModel=vision.model,
        corpusSignature=embed.corpus_signature,querySignature=embed.query_signature,contracts=[],searches=[])
    vectors={}
    for kind,kw in [('text',dict(text='蓝色矩形')),('image',dict(image=frame)),
                    ('joint',dict(image=frame,text='蓝色矩形')),('joint_changed',dict(image=frame,text='有人拿着它离开')),
                    ('video',dict(video=video,corpus=True))]:
        started=time.monotonic(); value=await embed.embed_v2(**kw); vectors[kind]=value
        report['contracts'].append(dict(kind=kind,dimensions=len(value),normalized=math.isclose(sum(x*x for x in value),1,abs_tol=1e-5),
            elapsedMs=round((time.monotonic()-started)*1000,2)))
    report['jointTextChanged']=sum(a*b for a,b in zip(vectors['joint'],vectors['joint_changed']))<.999999
    store=Store(root/'probe.sqlite'); service=VideoService(store,root/'recordings',embed,vision)
    try:
        recording=service.stage(video,'probe-camera',recorded_at=1700000000,source_type='synthetic_probe')
        started=time.monotonic(); indexed=await service.index(recording['id'])
        report['index']=dict(status=indexed['status'],segments=indexed['segmentCount'],elapsedMs=round((time.monotonic()-started)*1000,2))
        if indexed['status']!='ready': raise ValueError('合成录像索引失败：'+str(indexed.get('error')))
        ref=service.retrieval.upload_image('synthetic-probe',frame.read_bytes())
        for kind,kw in [('text',dict(text='画面中有蓝色矩形')),('image',dict(image_ref=ref['id'])),
                        ('joint',dict(text='这个物体位于画面中央',image_ref=ref['id']))]:
            result=service.retrieval.start(SearchInput(**kw),'synthetic-probe')
            task=service.retrieval.jobs[result['id']]; saw_candidates=False
            while not task.done():
                current=service.retrieval.get(result['id'],'synthetic-probe')
                if current['videos'] and current['status']=='verifying': saw_candidates=True
                await asyncio.sleep(.02)
            await task
            result=service.retrieval.get(result['id'],'synthetic-probe')
            report['searches'].append(dict(kind=kind,status=result['status'],candidateBeforeVerification=saw_candidates,
                candidateCount=result['candidateCount'],timings=result['timings'],
                verdicts=[v['verdict'] for v in result['videos']],referencePassed=all(v['referenceImageUsed'] for v in result['videos']) if kw.get('image_ref') else None))
    finally:
        await service.shutdown(); store.close()
    report['verificationErrors']=vision.errors  # Synthetic content only, never use this probe for personal footage.
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if os.getenv('EG_ENV_FILE'): load_dotenv(os.environ['EG_ENV_FILE'],override=False)
    os.environ['EG_CAMERA_SOURCE']='fixture_lab';os.environ['EG_VIDEO_INDEX_V2']='1'
    with tempfile.TemporaryDirectory(prefix='eg-video-contract-') as directory:
        result=asyncio.run(probe(Path(directory)))
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
