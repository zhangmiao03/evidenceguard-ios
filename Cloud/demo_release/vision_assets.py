"""Install one pinned DepthART model for demo; no credentials or arbitrary URLs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

SHA256='825114de5341612386de409f82f5dfb0496bb9afa559565ac633466bf172fb71'
SIZE=24155097
MODEL=Path('/opt/evidenceguard-demo/models/depthart448-'+SHA256[:16]+'.onnx')
URL='https://huggingface.co/Fengxue93/DepthART/resolve/9e154201cd8fb3453c9def581997aaf1b4da3c22/onnx/relative_mnv4m_slim_spf_448_default.onnx'


def valid(path):
    return path.is_file() and path.stat().st_size==SIZE and hashlib.sha256(path.read_bytes()).hexdigest()==SHA256


def install(check=False):
    if not valid(MODEL):
        if check: raise RuntimeError('Pinned depth model missing or corrupt')
        MODEL.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.depthart-',dir=MODEL.parent)
        try:
            with os.fdopen(fd,'wb') as target, urllib.request.urlopen(URL,timeout=60) as source:
                size=0
                while chunk:=source.read(1024*1024):
                    size+=len(chunk)
                    if size>SIZE: raise RuntimeError('Unexpected weight size')
                    target.write(chunk)
            if not valid(Path(name)): raise RuntimeError('Pinned weight integrity failed')
            Path(name).chmod(0o644);os.replace(name,MODEL)
        finally: Path(name).unlink(missing_ok=True)
    print(json.dumps(dict(model='DepthART448',path=str(MODEL),sha256=SHA256,bytes=SIZE,verified=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    install(parser.parse_args().check)
