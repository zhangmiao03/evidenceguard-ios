"""Real MP4 preprocessing for v2; no thumbnail-to-video substitution."""
from __future__ import annotations
import asyncio, json, re
from pathlib import Path
import numpy as np
from PIL import Image


def sharpness(path):
    with Image.open(path) as image:
        gray = np.asarray(image.convert('L').resize((160, 90)), dtype=np.float32)
    laplacian = -4*gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    return float(laplacian.var())


async def frames(playback, folder):
    manifest = folder/'frames.json'
    if manifest.is_file():
        items = json.loads(manifest.read_text())
        if items and all((folder/item['file']).is_file() for item in items): return items
    process = await asyncio.create_subprocess_exec('ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
        '-protocol_whitelist', 'file,pipe', '-i', str(playback), '-an',
        '-vf', r"select='isnan(prev_selected_t)+gte(t-prev_selected_t,1)',scale=min(640\,iw):-2,showinfo",
        '-vsync', 'vfr', '-q:v', '3', str(folder/'frame-%05d.jpg'),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try: _, error = await asyncio.wait_for(process.communicate(), 120)
    except BaseException:
        if process.returncode is None: process.kill()
        await process.communicate(); raise
    if process.returncode: raise ValueError('无法从原录像抽取关键帧')
    # showinfo reports the selected frames' actual presentation timestamps;
    # unlike a guessed fps counter these remain correct for variable-frame-rate media.
    timestamps = re.findall(r'\bn:\s*\d+\s+pts:.*?pts_time:([\d.e+\-]+)', error.decode(errors='replace'))
    if not timestamps: raise ValueError('关键帧缺少可验证时间戳')
    items = []
    for i, timestamp in enumerate(timestamps, 1):
        file = f'frame-{i:05d}.jpg'
        items.append(dict(file=file, offset=float(timestamp), sharpness=await asyncio.to_thread(sharpness, folder/file)))
    manifest.write_text(json.dumps(items), encoding='utf-8')
    return items


def representatives(items, start, end):
    selected = []
    for part in range(3):
        low, high = start+(end-start)*part/3, start+(end-start)*(part+1)/3
        candidates = [item for item in items if low <= item['offset'] < high]
        if candidates: selected.append(max(candidates, key=lambda v: (v['sharpness'], -v['offset'])))
    return selected


async def build(service, recording, playback, signature):
    from .service import command, windows
    folder = playback.parent/('index-'+signature[:16]); folder.mkdir(exist_ok=True)
    service.index_db.begin(recording, signature)
    samples = await frames(playback, folder)
    segments = list(windows(recording['duration']))
    for i, (start, end) in enumerate(segments):
        clip = folder/f'clip-{i}.mp4'
        if not clip.is_file():
            temporary = folder/f'building-{i}.mp4'
            await command('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start),
                '-protocol_whitelist', 'file,pipe', '-i', str(playback), '-t', str(end-start), '-an',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temporary))
            temporary.replace(clip)
        embeddings = []
        chosen = representatives(samples, start, end)
        if not chosen: raise ValueError('片段中没有可定位的关键帧，未发布索引')
        clip_record = dict(id=recording['id']+f'-{i}', recordingId=recording['id'], cameraId=recording['cameraId'],
            continuityId=recording['id'], start=start, end=end, path=str(clip.relative_to(service.root)), expectedFrames=len(chosen))
        inputs = [('video', -1, clip, None)] + [
            ('frame', round(item['offset']*1000), folder/item['file'], str(folder/item['file'])) for item in chosen]
        for kind, offset, path, thumbnail in inputs:
            key = service.index_db.unit_id(path, kind, signature)
            if not service.index_db.has_unit(key):
                vector = await service.embedding.embed_v2(corpus=True, **({'video': path} if kind == 'video' else {'image': path}))
                service.index_db.save_unit(key, signature, service.embedding.model, vector)
            embeddings.append((kind, offset, key, str(Path(thumbnail).relative_to(service.root)) if thumbnail else None))
            # Link each completed unit before the next await. It survives retry
            # and cannot be collected while another recording is being deleted.
            service.index_db.save_clip(clip_record, signature, embeddings)
        recording['indexedSegments'] = i+1; service.db.save_recording(recording)
    recording.update(status='ready', error=None, embeddingModel=service.embedding.model, embeddingSignature=signature,
        segmentCount=len(segments), indexVersion=2)
    # The active pointer and public recording metadata change in one transaction.
    with service.store.transaction():
        service.index_db.publish(recording, signature, len(segments))
        service.db.save_recording(recording)
