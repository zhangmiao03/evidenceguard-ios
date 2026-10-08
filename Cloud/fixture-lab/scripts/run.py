"""Start isolated local media server and API; stop only the processes we own."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
PORT=int(os.getenv('EG_PORT','8787'))
for port in (18554,PORT):
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1',port))==0:
            raise SystemExit(f'Port {port} is occupied. Close the existing instance or choose EG_PORT for the API.')
binary=ROOT/'.runtime'/'mediamtx'
if not binary.exists() or not (ROOT/'frontend/dist/index.html').exists():
    raise SystemExit('Run scripts/setup.py first.')
logs=ROOT/'.runtime'
children=[]
def stop(signum=None,frame=None):
    raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    with (logs/'mediamtx.log').open('a') as media_log:
        children.append(subprocess.Popen([str(binary),'infra/mediamtx.yml'],stdout=media_log,stderr=subprocess.STDOUT))
        time.sleep(.4)
        if children[0].poll() is not None:
            raise RuntimeError('MediaMTX failed; see .runtime/mediamtx.log')
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(PORT),'--log-level','warning']))
        print(f'EvidenceGuard: http://127.0.0.1:{PORT}',flush=True)
        print('Synthetic sources -> FFmpeg -> MediaMTX -> FFmpeg -> vision -> SQLite -> UI',flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(1)
        raise RuntimeError('A service exited; inspect console and .runtime/mediamtx.log')
except KeyboardInterrupt:
    pass
finally:
    for p in reversed(children):
        if p.poll() is None:
            p.terminate()
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
