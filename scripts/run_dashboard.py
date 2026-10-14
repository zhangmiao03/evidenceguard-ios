#!/usr/bin/env python3
"""Run the app + operations console locally; never deploy or load cloud secrets."""
import argparse
import os
from pathlib import Path
import sys
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8790)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'Cloud/data/local-dashboard')
    parser.add_argument('--env-file',type=Path,help='Optional explicitly selected local configuration')
    parser.add_argument('--capture-content',action='store_true',help='Opt in to dynamic prompt text; exports may include private conversations')
    args=parser.parse_args()
    web=ROOT/'Web/dist'
    if not (web/'index.html').is_file(): parser.error('Build Web first: cd Web && npm ci && npm run build')
    if not 1<=args.port<=65535: parser.error('Invalid port')
    if args.env_file:
        if not args.env_file.is_file(): parser.error('Configuration file not found')
        from dotenv import load_dotenv
        load_dotenv(args.env_file,override=False)
    data=args.data_dir.resolve();data.mkdir(parents=True,exist_ok=True)
    # An isolated local sandbox by default. No implicit production env loading.
    os.environ['EG_DATABASE']=str(data/'business.sqlite3')
    os.environ['EG_OPS_DATABASE']=str(data/'observability.sqlite3')
    os.environ['EG_VIDEO_ROOT']=str(data/'recordings')
    os.environ['EG_OPS_ENABLED']='1'
    os.environ['EG_OPS_CAPTURE_CONTENT']='1' if args.capture_content else '0'
    os.environ['EG_WEB_ROOT']=str(web)
    try:
        os.environ.setdefault('EG_BUILD_REVISION',subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip())
    except (OSError,subprocess.CalledProcessError): pass
    sys.path.insert(0,str(ROOT/'Cloud/server'))
    import uvicorn
    print(f'Dashboard: http://127.0.0.1:{args.port}/dashboard',flush=True)
    print(f'Local data: {data}',flush=True)
    uvicorn.run('evidenceguard.app:app',host='127.0.0.1',port=args.port,workers=1)


if __name__=='__main__': main()
