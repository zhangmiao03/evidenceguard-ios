"""Privileged, network-free collector. Only bounded public snapshots leave it.

The web process runs separately and cannot read app databases, env files or run
commands. Sampling never mutates application state and never replays old runs.
"""
from __future__ import annotations
import argparse
from collections import deque
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
from urllib.parse import quote

SCHEMA = 'evidenceguard.ops/v1'
MAX_RECORDS = 3000
MAX_BYTES = 6_000_000
SECRET = re.compile(r'authorization|api.?key|secret|password|credential|tokenhash|imagebase64|token$|^sn$|devicesn|serialnumber|accountid|clientid|importedby',re.I)


def public_value(value, depth=0):
    if depth > 16:return '[depth omitted]'
    if isinstance(value, dict):
        return {str(k)[:100]:'[redacted]' if SECRET.search(str(k)) else public_value(v,depth+1)
                for k,v in list(value.items())[:100]}
    if isinstance(value,list):return [public_value(v,depth+1) for v in value[:100]]
    if isinstance(value,str):
        if 'data:' in value and ';base64,' in value:return '[binary omitted]'
        if 'PRIVATE KEY-----' in value:return '[credential omitted]'
        value=re.sub(r'(?i)Bearer\s+\S+','Bearer [redacted]',value)
        value=re.sub(r'''(?i)(api[_-]?key|password|secret|access[_-]?token)["']?\s*[=:]\s*["']?[^\s,;"'}]+''',r'\1=[redacted]',value)
        value=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b','[credential omitted]',value)
        value=re.sub(r'https?://[^\s"<>]+','[remote URL omitted]',value)
        return value[:16000]
    if isinstance(value,float):return value if math.isfinite(value) else None
    if value is None or isinstance(value,(bool,int)):return value
    return '[unsupported value]'


def content_ref(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True)
    return {'omitted':'dynamic content on public dashboard','characters':len(raw),
            'sha256':hashlib.sha256(raw.encode()).hexdigest()}


def public_record(record):
    result={key:record.get(key) for key in ('id','kind','name','at','traceId','spanId','parentSpanId',
                                          'source','platform','status','durationMs','data')}
    result['data']=public_value(result.get('data') or {})
    if result['kind']=='prompt':
        body=result['data'].get('request',{})
        for index,message in enumerate(body.get('messages',[])):
            if not isinstance(message,dict):continue
            if not (index==0 and message.get('role')=='system'):
                existing=message.get('content')
                message['content']=existing if isinstance(existing,dict) and existing.get('omitted') else content_ref(existing)
            calls=message.get('tool_calls')
            message['tool_calls']=calls if isinstance(calls,dict) and calls.get('omitted') else content_ref(calls)
        if 'input' in body:body['input']=content_ref(body['input'])
        result['data']['contentCapture']=False
        result['data']['publicProjection']=True
        result['data']['hashMeaning']='sanitized server request before public projection; not wire bytes'
    return result


@contextmanager
def readonly(path):
    db=sqlite3.connect('file:'+quote(str(Path(path).resolve()).replace('\\','/'),safe='/:')+'?mode=ro',uri=True,timeout=.15)
    try:
        db.execute('PRAGMA query_only=ON')
        yield db
    finally:
        db.close()


def resource(name, value, at):
    rid=hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()[:24]
    return dict(id='resource:'+name+':'+rid,kind='resource',name=name,at=at,traceId='snapshot:'+name,
                spanId=rid,parentSpanId=None,source='snapshot',platform='backend',
                status=str(value.get('status','snapshot')),durationMs=None,data=public_value(value))


def read_business(path, now):
    fields={'id','name','model','status','state','lifecycle','cameraId','devices','skillId','revision',
            'executionMode','createdAt','updatedAt','capturedAt','sampledAt','receivedAt','observedAt',
            'sourceType','timestampMeaning','duration','segmentCount','expectedOutcome','verdict',
            'platform','registrationSource','ownershipVerified','mediaStatus','taskKind'}
    resources=[];counts={}
    with readonly(path) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('live_devices','skills','runs','evidence','recordings','skill_trials'):
            if table not in tables:continue
            counts[table]=db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for row in db.execute(f'SELECT payload FROM {table} ORDER BY rowid DESC LIMIT 60'):
                value=json.loads(row[0]);resources.append(resource(table,{k:v for k,v in value.items() if k in fields},now))
    return resources,counts


def file_hashes(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*.py')) if '__pycache__' not in p.parts and not p.is_symlink()}


def compare_files(actual, expected):
    return [{'path':name,'actual':actual.get(name),'expected':expected.get(name),
             'status':'extra' if name not in expected else 'missing' if name not in actual else 'changed'}
            for name in sorted(set(actual)|set(expected)) if actual.get(name)!=expected.get(name)]


class Resources:
    def __init__(self, proc=Path('/proc')):
        self.proc=proc;self.previous=None;self.history=deque(maxlen=90)

    def sample(self, services):
        now=time.time();mono=time.monotonic()
        cpu=[int(v) for v in (self.proc/'stat').read_text().splitlines()[0].split()[1:9]]
        total=sum(cpu);idle=cpu[3]+cpu[4]
        mem={line.split(':')[0]:int(line.split()[1])*1024 for line in (self.proc/'meminfo').read_text().splitlines()}
        received=sent=0
        for line in (self.proc/'net/dev').read_text().splitlines()[2:]:
            name,data=line.split(':');parts=data.split()
            if name.strip()!='lo':received+=int(parts[0]);sent+=int(parts[8])
        disk=shutil.disk_usage('/')
        service_rows=[];ticks={}
        for label,name in services.items():
            if not re.fullmatch(r'[a-zA-Z0-9_.@-]+',name):raise ValueError('Invalid service name')
            try:
                status=subprocess.check_output(['systemctl','show',name,'--property=MainPID,ActiveState,SubState,NRestarts','--no-pager'],text=True,timeout=3)
                fields=dict(line.split('=',1) for line in status.splitlines() if '=' in line)
                pid=int(fields.get('MainPID','0'));rss=None;used=None
                if pid:
                    data=(self.proc/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
                    ticks[label]=(pid,int(data[11])+int(data[12]))
                    memory=(self.proc/str(pid)/'status').read_text()
                    match=re.search(r'^VmRSS:\s+(\d+)',memory,re.M)
                    rss=int(match[1])*1024 if match else None
                    old=self.previous['ticks'].get(label) if self.previous else None
                    if old and old[0]==pid:
                        used=max(0,(ticks[label][1]-old[1])/os.sysconf('SC_CLK_TCK')/(mono-self.previous['mono'])*100)
                service_rows.append(dict(environment=label,service=name,pid=pid or None,
                    state=fields.get('ActiveState'),subState=fields.get('SubState'),
                    restarts=int(fields.get('NRestarts','0')),rssBytes=rss,cpuPercent=round(used,2) if used is not None else None))
            except (OSError,ValueError,subprocess.SubprocessError):
                service_rows.append(dict(environment=label,service=name,state='unavailable',pid=None,rssBytes=None,cpuPercent=None))
        prev=self.previous
        delta=mono-prev['mono'] if prev else None
        percent=100*(1-(idle-prev['idle'])/(total-prev['total'])) if prev and total>prev['total'] else None
        result=dict(at=now,cpuPercent=round(max(0,min(100,percent)),2) if percent is not None else None,
                    cpuCount=os.cpu_count(),loadAverage=list(os.getloadavg()),
                    memoryTotalBytes=mem['MemTotal'],memoryUsedBytes=mem['MemTotal']-mem.get('MemAvailable',mem['MemFree']),
                    diskTotalBytes=disk.total,diskUsedBytes=disk.used,diskFreeBytes=disk.free,
                    networkReceiveBytesPerSecond=max(0,(received-prev['received'])/delta) if prev else None,
                    networkSendBytesPerSecond=max(0,(sent-prev['sent'])/delta) if prev else None,
                    uptimeSeconds=float((self.proc/'uptime').read_text().split()[0]),
                    services=service_rows,sampleSeconds=delta,
                    definitions={'cpu':'host total capacity, first interval unavailable',
                        'processCpu':'100% is one logical CPU; may exceed 100%',
                        'memory':'MemTotal minus MemAvailable','network':'all interfaces excluding loopback; interval rate'})
        self.previous=dict(total=total,idle=idle,received=received,sent=sent,mono=mono,ticks=ticks)
        self.history.append({k:result[k] for k in ('at','cpuPercent','memoryUsedBytes','networkReceiveBytesPerSecond','networkSendBytesPerSecond')})
        result['history']=list(self.history)
        return result


class Collector:
    def __init__(self, config):
        self.config=config;self.output=Path(config['output']);self.output.mkdir(parents=True,exist_ok=True)
        self.resources=Resources();self.disk_cache={};self.scan_at=0
        self.reference=json.loads(Path(config['reference']).read_text())

    def write(self, name, value):
        p=self.output/name;tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        tmp.chmod(0o644);tmp.replace(p)

    def bundle(self, label, environment, server):
        now=time.time();records=[];coverage={'readOnly':True,'publicProjection':True,'contentCapture':False,
            'environment':label,'sampledAt':now,'clock':'server receive wall clock; durations use monotonic clocks',
            'limitations':['No historical model backfill','Dynamic messages are metadata-only on the public dashboard',
                'No model private reasoning, credentials, camera images or video URLs','No inference that missing events mean success']}
        try:
            state=json.loads(Path(environment['state']).read_text())
        except (OSError,ValueError):state={}
        if not self.disk_cache or time.monotonic()-self.scan_at>30:
            self.disk_cache={}
            for env in self.config['environments'].values():
                if env['source'] not in self.disk_cache:self.disk_cache[env['source']]=file_hashes(env['source'])
            self.scan_at=time.monotonic()
        disk=self.disk_cache[environment['source']]
        loaded=state.get('files',{})
        service=next((v for v in server.get('services',[]) if v['environment']==label),{})
        same_process=state.get('pid')==service.get('pid') and bool(state.get('pid'))
        coverage['deployment']={'observerRevision':state.get('observerRevision'),'appVersion':state.get('appVersion'),
            'startedAt':state.get('startedAt'),'processMatchesObserver':same_process,
            'referenceRevision':self.reference['revision'],'fileCount':len(disk),
            'diskVsRunning':compare_files(disk,loaded) if loaded else None,
            'diskVsRepository':compare_files(disk,self.reference['files']),
            'sourceFingerprint':hashlib.sha256(json.dumps(disk,sort_keys=True).encode()).hexdigest(),
            'files':[{'path':k,'sha256':v} for k,v in disk.items()],
            'observerVersion':self.config.get('revision'),'nativeOps':state.get('nativeOps')}
        try:
            with readonly(environment['observations']) as db:
                coverage['totalStored']=db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
                for row in db.execute('SELECT payload FROM records ORDER BY at DESC LIMIT ?', (MAX_RECORDS,)):
                    records.append(public_record(json.loads(row[0])))
                records.reverse()
            coverage['observability']='connected' if same_process else 'stale_process'
        except (OSError,ValueError,sqlite3.Error) as exc:
            coverage.update(observability='unavailable',errorType=type(exc).__name__,totalStored=None)
        try:
            resources,counts=read_business(environment['database'],now)
            records.extend(resources)
            coverage.update(resourceCounts=counts,resourceLimitPerTable=60,resourceSnapshotsAt=now,
                            resourcesTruncated=any(n>60 for n in counts.values()))
        except (OSError,ValueError,sqlite3.Error) as exc:coverage['resourceErrorType']=type(exc).__name__
        for name,model in state.get('models',{}).items():
            records.append(resource('model_configuration',{'operation':name,'model':model,
                'status':'configured' if model else 'not_configured'},now))
        if state.get('systemPrompt'):
            records.append(resource('deployed_prompt',{'systemPrompt':state['systemPrompt'],
                'tools':state.get('tools',[]),'status':'loaded_at_startup'},state.get('startedAt',now)))
        size=0;selected=[]
        for row in reversed(records):
            size+=len(json.dumps(row,ensure_ascii=False).encode())
            if size>MAX_BYTES:break
            selected.append(row)
        selected.reverse()
        count=sum(r['kind']!='resource' for r in selected)
        coverage.update(returned=len(selected),truncated=coverage.get('totalStored',0) is not None and coverage.get('totalStored',0)>count,
                        recordLimit=MAX_RECORDS,server=server)
        return dict(schemaVersion=SCHEMA,dataset={'id':'cloud-'+label,'title':environment['title']+' · 云端实时追踪',
                    'source':'local','exportedAt':now},coverage=coverage,records=selected)

    def tick(self):
        try:server=self.resources.sample({k:v['service'] for k,v in self.config['environments'].items()})
        except (OSError,ValueError) as exc:server={'at':time.time(),'errorType':type(exc).__name__,'services':[]}
        self.write('server.json',server)
        for label,environment in self.config['environments'].items():
            try:self.write(label+'.json',self.bundle(label,environment,server))
            except Exception as exc:
                self.write(label+'.json',{'error':'collection_unavailable','errorType':type(exc).__name__,'at':time.time()})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--once',action='store_true')
    args=parser.parse_args();collector=Collector(json.loads(Path(args.config).read_text()))
    while True:
        collector.tick()
        if args.once:break
        time.sleep(5)

if __name__=='__main__':main()

