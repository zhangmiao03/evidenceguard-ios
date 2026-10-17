"""Install the additive competition observer with checked, reversible changes.

Run as root on the project EC2 only. Existing business source, environment files,
databases, credentials and App authentication are never replaced. Each existing
service is restarted separately after compatibility tests. A failure restores
the captured service/proxy configuration before returning a nonzero exit code.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time
import urllib.request
import urllib.error
from eg_dashboard.service_config import parse_command
from eg_dashboard.nginx_routes import plan as dashboard_tls_routes

BASE=Path('/opt/evidenceguard-dashboard')
SERVICES={
    'team':('evidenceguard',8790,'/opt/evidenceguard/Cloud/server','/opt/evidenceguard/venv'),
    'demo':('evidenceguard-demo',8792,'/opt/evidenceguard-demo/Cloud/server','/opt/evidenceguard-demo/venv-build10'),
    'review':('evidenceguard-review',8791,'/opt/evidenceguard/Cloud/server','/opt/evidenceguard/venv'),
}
COLLECTOR='evidenceguard-dashboard-collector'
WEB='evidenceguard-dashboard'
CONFIG=Path('/etc/evidenceguard-dashboard/config.json')
NGINX=Path('/etc/nginx/sites-enabled/evidenceguard-dashboard-ip')
PYTHON='/opt/evidenceguard/venv/bin/python'


def run(*args,**kwargs):
    return subprocess.run(list(args),check=True,text=True,**kwargs)


def status(name,field):
    result=subprocess.run(['systemctl','show',name,'--property='+field,'--value'],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode==0 else ''


def healthy(port):
    for _ in range(30):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as response:
                if response.status==200:
                    try:urllib.request.urlopen(f'http://127.0.0.1:{port}/api/bootstrap',timeout=2)
                    except urllib.error.HTTPError as error:
                        if error.code==401:return
                    raise RuntimeError('Existing App authentication check failed')
        except (urllib.error.URLError,TimeoutError):time.sleep(.5)
    raise RuntimeError('Backend health check failed on '+str(port))


def restore(directory):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(Path('/var/backups/evidenceguard-dashboard')):raise ValueError('Unexpected rollback directory')
    manifest=json.loads((directory/'manifest.json').read_text())
    for item in manifest['files']:
        target=Path(item['path'])
        if item['content'] is None:target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(base64.b64decode(item['content']));target.chmod(item['mode'])
    run('systemctl','daemon-reload')
    for name in [COLLECTOR,WEB]:
        previous=manifest['services'][name]
        subprocess.run(['systemctl','enable' if previous['enabled'] else 'disable',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['systemctl','restart' if previous['active'] else 'stop',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for name in manifest.get('restarted',[]):run('systemctl','restart',name)
    run('nginx','-t');run('systemctl','reload','nginx')
    print('Restored configuration from '+str(directory),flush=True)


def activate(release, capture_content=False):
    release=Path(release).resolve()
    if os.geteuid()!=0:raise RuntimeError('Run through the authorized root SSM maintenance command')
    if not release.is_relative_to(BASE/'releases') or not (release/'reference.json').is_file():raise ValueError('Unexpected release')
    services={};commands={};observed_commands={}
    for label,(service,port,source,venv) in SERVICES.items():
        healthy(port)
        command=status(service,'ExecStart')
        source,venv,commands[label]=parse_command(command,'/opt/evidenceguard-demo' if label=='demo' else '/opt/evidenceguard',port)
        services[label]=(service,port,source,venv)
        observed_commands[service]=command
    # Test each distinct deployed tree without reading production credentials.
    for source,venv in sorted({(v[2],v[3]) for v in services.values()}):
        env=dict(os.environ,PYTHONPATH=str(release)+':'+source)
        run(venv+'/bin/python',str(release/'compatibility.py'),env=env,cwd='/tmp')
        if capture_content:
            run(venv+'/bin/python',str(release/'compatibility.py'),'--capture-content',env=env,cwd='/tmp')
    run(PYTHON,'-m','unittest','discover','-s',str(release/'tests'),'-v',env=dict(os.environ,PYTHONPATH=str(release)))
    for service,command in observed_commands.items():
        if status(service,'ExecStart')!=command:
            raise RuntimeError('Backend changed during preflight; restart deployment after coordination: '+service)

    dropins=[Path('/etc/systemd/system')/(s+'.service.d/40-dashboard-observer.conf') for s,_,_,_ in services.values()]
    tls_routes=dashboard_tls_routes()
    files=dropins+[Path('/etc/systemd/system')/(n+'.service') for n in [COLLECTOR,WEB]]+[CONFIG,NGINX]+list(tls_routes)
    backup=Path('/var/backups/evidenceguard-dashboard')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    manifest={'release':str(release),'restarted':[],'files':[], 'services':{}}
    for target in files:
        manifest['files'].append({'path':str(target),'mode':target.stat().st_mode&0o777 if target.exists() else 0o644,
            'content':base64.b64encode(target.read_bytes()).decode() if target.exists() else None})
    for name in [COLLECTOR,WEB]:
        manifest['services'][name]={'active':status(name,'ActiveState')=='active','enabled':status(name,'UnitFileState')=='enabled'}
    def save(): (backup/'manifest.json').write_text(json.dumps(manifest))
    save()
    print('Rollback configuration: '+str(backup),flush=True)
    try:
        for path,value in tls_routes.items():path.write_text(value)
        try:pwd.getpwnam(WEB)
        except KeyError:run('useradd','--system','--home-dir','/nonexistent','--shell','/usr/sbin/nologin',WEB)
        run('install','-d','-o','root','-g',WEB,'-m','750','/var/lib/evidenceguard-dashboard')
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        titles={'team':'团队联调','demo':'手机演示','review':'Apple 审核'}
        config={'output':'/var/lib/evidenceguard-dashboard','reference':str(release/'reference.json'),'revision':release.name,
            'environments':{label:{'title':titles[label],'service':service,'source':source+'/evidenceguard',
                'state':'/var/lib/'+service+'/observer-state.json','observations':'/var/lib/'+service+'/observability.sqlite3',
                'database':'/var/lib/'+service+'/evidenceguard.sqlite3',
                'secretFiles':['/etc/'+service+'/cloud.env']} for label,(service,port,source,venv) in services.items()}}
        CONFIG.write_text(json.dumps(config,ensure_ascii=False));CONFIG.chmod(0o644)
        for label,(service,port,source,venv) in services.items():
            target=Path('/etc/systemd/system')/(service+'.service.d/40-dashboard-observer.conf')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(f'''[Service]
Environment=PYTHONPATH={release}
Environment=EG_OPS_ENABLED=1
Environment=EG_OPS_CAPTURE_CONTENT=0
Environment=EG_DASHBOARD_CAPTURE_CONTENT={int(capture_content)}
Environment=EG_DASHBOARD_CAPTURE_MEDIA={int(capture_content)}
Environment=EG_OPS_DATABASE=/var/lib/{service}/observability.sqlite3
Environment=EG_DASHBOARD_ENVIRONMENT={label}
Environment=EG_DASHBOARD_REVISION={release.name}
ExecStart=
ExecStart={commands[label]}
''')
        common='''Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
UMask=0027
'''
        Path('/etc/systemd/system/'+COLLECTOR+'.service').write_text(f'''[Unit]
Description=EvidenceGuard read-only telemetry collector
After=network.target
[Service]
User=root
Environment=PYTHONPATH={release}
ExecStart={PYTHON} -m eg_dashboard.collector --config {CONFIG}
ReadWritePaths=/var/lib/evidenceguard-dashboard
RestrictAddressFamilies=AF_UNIX
{common}
[Install]
WantedBy=multi-user.target
''')
        Path('/etc/systemd/system/'+WEB+'.service').write_text(f'''[Unit]
Description=EvidenceGuard public read-only competition Dashboard
After=network.target {COLLECTOR}.service
[Service]
User={WEB}
Group={WEB}
WorkingDirectory={release}
Environment=PYTHONPATH={release}
Environment=EG_DASHBOARD_DATA=/var/lib/evidenceguard-dashboard
Environment=EG_DASHBOARD_WEB={release}/web
ExecStart={PYTHON} -m uvicorn eg_dashboard.server:app --host 127.0.0.1 --port 8795 --no-access-log
InaccessiblePaths=-/etc/evidenceguard -/etc/evidenceguard-demo -/etc/evidenceguard-review -/var/lib/evidenceguard -/var/lib/evidenceguard-demo -/var/lib/evidenceguard-review -/opt/evidenceguard/Cloud -/opt/evidenceguard-demo
{common}
[Install]
WantedBy=multi-user.target
''')
        NGINX.write_text('''# Competition Dashboard only. Existing App routes keep their original redirect/authentication.
server {
    listen 80;
    server_name 47.131.21.137;
    gzip on;
    gzip_types application/json application/javascript text/css;
    gzip_min_length 1024;
    client_max_body_size 32k;
    location = /dashboard {
        proxy_pass http://127.0.0.1:8795;
        proxy_set_header Host $host;
        proxy_read_timeout 15s;
    }
    location ^~ /dashboard/ {
        proxy_pass http://127.0.0.1:8795;
        proxy_set_header Host $host;
        proxy_read_timeout 15s;
    }
    location / { return 301 https://demo.47.131.21.137.sslip.io$request_uri; }
}
''')
        run('nginx','-t');run('systemctl','daemon-reload')
        for label,(service,port,source,venv) in services.items():
            manifest['restarted'].append(service);save()
            run('systemctl','restart',service);healthy(port)
            state=json.loads(Path('/var/lib/'+service+'/observer-state.json').read_text())
            if state['pid']!=int(status(service,'MainPID')):raise RuntimeError('Observer PID mismatch: '+service)
            print(service+' healthy, authentication preserved, observer attached',flush=True)
        run('systemctl','enable','--now',COLLECTOR,WEB)
        run('systemctl','restart',COLLECTOR,WEB)
        for _ in range(20):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8795/dashboard/api/snapshot?environment=demo',timeout=2) as response:
                    bundle=json.load(response)
                if bundle['coverage']['observability']=='connected':break
            except (OSError,KeyError,ValueError):time.sleep(1)
        else:raise RuntimeError('Dashboard did not receive a live snapshot')
        run('systemctl','reload','nginx')
        request=urllib.request.Request('http://127.0.0.1/dashboard',headers={'Host':'47.131.21.137'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        # nginx reload returns before old workers have all stopped accepting.
        # A redirect is not success, and must not be followed into the App API.
        proxy=urllib.request.build_opener(NoRedirect)
        for _ in range(20):
            try:
                with proxy.open(request,timeout=3) as response:
                    if response.status==200 and b'/dashboard/assets/' in response.read():break
            except (OSError,urllib.error.HTTPError):pass
            time.sleep(.5)
        else:raise RuntimeError('Dashboard proxy check failed; restoring original configuration')
        print(json.dumps({'deployed':True,'url':'http://47.131.21.137/dashboard','release':str(release),'rollback':str(backup)}),flush=True)
    except BaseException:
        restore(backup)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--release');group.add_argument('--rollback')
    parser.add_argument('--capture-content',action='store_true',help='Explicitly publish secret-filtered text for future observed runs')
    args=parser.parse_args()
    if args.rollback:restore(args.rollback)
    else:activate(args.release,args.capture_content)
