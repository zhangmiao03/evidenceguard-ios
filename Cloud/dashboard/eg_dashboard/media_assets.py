"""Bounded media copies for the explicitly public competition dashboard.

The HTTP worker reads only a content-addressed cache, never app files or URLs.
Model input copies come from the exact request bytes, not guessed nearby frames.
"""
import base64
import hashlib
import os
from pathlib import Path
import re
import time

MAX_IMAGE = 8_000_000
MAX_VIDEO = 32_000_000
MAX_CACHE = 256_000_000
ID = re.compile(r'^[a-f0-9]{64}$')
MIMES = {'image/jpeg': 'jpg', 'image/png': 'png', 'video/mp4': 'mp4'}


def valid_bytes(raw, mime):
    if mime == 'image/jpeg': return raw.startswith(b'\xff\xd8\xff')
    if mime == 'image/png': return raw.startswith(b'\x89PNG\r\n\x1a\n')
    if mime == 'video/mp4': return len(raw) > 12 and raw[4:8] == b'ftyp'
    return False


def put(root, raw, mime, *, protected=()):
    if mime not in MIMES or not 0 < len(raw) <= (MAX_VIDEO if mime == 'video/mp4' else MAX_IMAGE) or not valid_bytes(raw, mime):
        return None
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    target = root / (digest + '.' + MIMES[mime])
    if target.is_symlink(): return None
    if not target.exists():
        # Bounded disk use. Old unreferenced copies may disappear; never retain
        # unbounded inputs on an otherwise healthy camera process.
        files = sorted((p for p in root.iterdir() if p.is_file() and not p.is_symlink()), key=lambda p:p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total + len(raw) <= MAX_CACHE: break
            if p.stem in protected: continue
            total -= p.stat().st_size; p.unlink()
        if total + len(raw) > MAX_CACHE: return None
        tmp = root / (digest + '.tmp')
        tmp.write_bytes(raw); tmp.chmod(0o644); tmp.replace(target)
    return {'assetId': digest, 'mime': mime, 'bytes': len(raw), 'kind': 'video' if mime.startswith('video/') else 'image'}


def capture_inputs(request, recorder):
    """Opt-in; no remote fetch. Up to 8 inputs (guard: 4 RGB + 2 depth + flow)."""
    if os.getenv('EG_DASHBOARD_CAPTURE_MEDIA') != '1' or not getattr(recorder, 'path', None): return []
    root = Path(recorder.path).parent / 'observer-media'
    found = []; visited = 0
    def walk(value, location, depth=0):
        nonlocal visited
        visited += 1
        if depth > 12 or visited > 3000 or len(found) >= 8: return
        if isinstance(value, dict):
            for key, item in value.items():
                if len(found) >= 8: break
                if key in {'image_url', 'video_url'}:
                    url = item.get('url') if isinstance(item, dict) else item
                    match = re.match(r'^data:(image/jpeg|image/png|video/mp4);base64,', url or '') if isinstance(url,str) else None
                    descriptor = {'position': location + '.' + key, 'kind': 'image' if key == 'image_url' else 'video'}
                    limit=MAX_VIDEO if key=='video_url' else MAX_IMAGE
                    if match and len(url) <= (limit * 4 // 3 + 100):
                        try:
                            media = put(root, base64.b64decode(url[match.end():], validate=True), match[1])
                            if media: descriptor.update(media, status='captured', provenance='exact_model_input')
                            else: descriptor['status'] = 'unsupported_or_over_limit'
                        except (OSError, ValueError): descriptor['status'] = 'unavailable'
                    else: descriptor['status'] = 'remote_or_unsupported_not_copied'
                    found.append(descriptor)
                elif isinstance(item, (dict,list)): walk(item, location+'.'+str(key), depth+1)
        elif isinstance(value,list):
            label = None
            for index,item in enumerate(value[:2000]):
                if isinstance(item,dict) and item.get('type')=='text':
                    label = item.get('text')
                before = len(found)
                walk(item, location+f'[{index}]', depth+1)
                if len(found)>before and isinstance(label,str) and len(label)<=120:
                    # The adjacent label belongs to these exact request bytes;
                    # do not guess roles from nearby timestamps or image content.
                    for descriptor in found[before:]: descriptor['label']=label
    walk(request, 'request')
    return found


class PublicMedia:
    def __init__(self, output, environment, private_root):
        self.environment=environment
        self.root=Path(output)/'media'/environment
        self.root.mkdir(parents=True,exist_ok=True)
        self.root.parent.chmod(0o755);self.root.chmod(0o755)
        self.private_root=Path(private_root)
        self.manifest={}
        self.bytes=0

    def add(self, raw, mime, **metadata):
        digest=hashlib.sha256(raw).hexdigest()
        if digest in self.manifest:
            return dict(self.manifest[digest], **metadata, previewUrl=f"/dashboard/api/media/{self.environment}/{digest}")
        if self.bytes+len(raw)>160_000_000: return None
        item=put(self.root,raw,mime,protected=self.manifest)
        if not item:return None
        if item['assetId'] not in self.manifest:self.bytes+=len(raw)
        self.manifest[item['assetId']]=item
        return dict(item, **metadata, previewUrl=f"/dashboard/api/media/{self.environment}/{item['assetId']}")

    def reference(self, item):
        if not isinstance(item,dict) or not ID.fullmatch(str(item.get('assetId',''))) or item.get('mime') not in MIMES:return dict(item or {},status='unavailable')
        source=self.private_root/(item['assetId']+'.'+MIMES[item['mime']])
        if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_VIDEO:return dict(item,status='expired_or_unavailable')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['assetId']:return dict(item,status='invalid')
        result=self.add(raw,item['mime'])
        return dict(item,**result,status='available') if result else dict(item,status='cache_limit')

    def finish(self):
        import json
        self.root.mkdir(parents=True,exist_ok=True)
        target=self.root/'manifest.json';tmp=self.root/'manifest.tmp'
        tmp.write_text(json.dumps({'at':time.time(),'items':self.manifest}),encoding='utf-8');tmp.chmod(0o644);tmp.replace(target)
        # Only assets in the newest allowlist are served; stale cache bytes are
        # removed after a short grace period for in-flight readers.
        for p in self.root.iterdir():
            if ID.fullmatch(p.stem) and p.stem not in self.manifest and time.time()-p.stat().st_mtime>3600 and not p.is_symlink():p.unlink()
