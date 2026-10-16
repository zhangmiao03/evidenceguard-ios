from __future__ import annotations
import copy, hashlib, json, sqlite3, threading, time, uuid
from pathlib import Path
from contextlib import contextmanager
from .schemas import EditSkill, SkillRules

DEFAULT_REGIONS = {'cam-a': {'x': .17, 'y': .27, 'width': .48, 'height': .54}, 'cam-b': {'x': .25, 'y': .24, 'width': .51, 'height': .57}}

class CameraConflict(ValueError):
    def __init__(self, conflicts):
        super().__init__('摄像头正在执行其他守护，请保存草案或确认切换任务')
        self.conflicts = conflicts

class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        with self.db:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY, payload TEXT NOT NULL, bytes BLOB NOT NULL, mime TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS skills (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, captured_at REAL NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, sequence INTEGER NOT NULL, type TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL, UNIQUE(run_id, sequence));
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, created_at REAL NOT NULL, payload TEXT NOT NULL);
            ''')

        # Timing-policy upgrades invalidate prior approvals and partial evidence.
        for item in self.skills():
            if item['status'] not in {'draft','active','paused'} or 'sampleIntervalSeconds' in item.get('rules',{}):continue
            item['rules']=SkillRules.model_validate(item.get('rules',{})).model_dump()
            item['revision']+=1;item.pop('evaluation',None);item.pop('approvedTrialId',None)
            if item['status']!='draft':
                item.update(status='paused',needsTimingReview=True,result='unknown',resultReason='检测已升级为按秒抽样，请创建修改草案并重新验收后启用')
            self.save_skill(item);self.event(item['id'],'timing_review_required',{})

    @contextmanager
    def transaction(self):
        with self.lock:
            outer = not self.db.in_transaction
            if outer: self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                if outer: self.db.commit()
            except BaseException:
                if outer: self.db.rollback()
                raise

    def close(self): self.db.close()

    def skills(self):
        with self.lock:
            rows = self.db.execute("SELECT payload FROM skills ORDER BY json_extract(payload,'$.createdAt') DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def skill(self, skill_id):
        with self.lock:
            row = self.db.execute('SELECT payload FROM skills WHERE id=?', (skill_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_skill(self, skill):
        with self.transaction():
            if skill['status'] == 'active':
                conflicts = self.conflicts(skill)
                if conflicts: raise CameraConflict(conflicts)
            self.db.execute('INSERT INTO skills VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (skill['id'], json.dumps(skill, ensure_ascii=False)))
        return skill

    def conflicts(self, skill):
        return [dict(skillId=s['id'], name=s['name'], devices=s['devices'],
                     executionEpoch=s.get('executionEpoch', 'legacy'))
                for s in self.skills() if s['status']=='active' and s['id']!=skill['id']
                and set(s['devices']) & set(skill['devices'])]

    def owner(self, device_id):
        return next((s for s in self.skills() if s['status']=='active' and device_id in s['devices']), None)

    def capture_context(self, device_id, skill_id=None):
        owner = self.owner(device_id)
        if skill_id:
            if not owner or owner['id'] != skill_id:
                raise ValueError('此任务没有占用该摄像头，请先启用或恢复任务')
            return owner.get('executionEpoch', 'legacy')
        if owner: raise CameraConflict(self.conflicts({'id':'', 'devices':[device_id]}))
        return None

    def recover_ownership(self):
        # Old versions permitted overlapping active tasks. Pause every conflicting owner;
        # never arbitrarily choose one and silently disable another user's guard.
        with self.transaction():
            conflicts = [s for s in self.skills() if s['status']=='active' and self.conflicts(s)]
            for s in conflicts:
                s.update(status='paused', result='unknown', resultReason='升级发现摄像头占用冲突，请选择要恢复的守护')
                self.save_skill(s); self.event(s['id'],'ownership_recovery_paused',{})
            for s in self.skills():
                if s['status']=='active' and not s.get('executionEpoch'):
                    s['executionEpoch']=uuid.uuid4().hex; self.save_skill(s)

    def _switch(self, skill, switch_from=None, replacement=None):
        conflicts=self.conflicts(skill)
        explicit=[c for c in conflicts if c['skillId'] != replacement]
        expected={c['skillId']:c['executionEpoch'] for c in explicit}
        if expected != (switch_from or {}): raise CameraConflict(explicit)
        for c in conflicts:
            old=self.skill(c['skillId'])
            old.update(status='stopped' if old['id']==replacement else 'paused',
                       result='unknown', resultReason='已由用户确认切换到「'+skill['name']+'」，当前不再观察')
            self.save_skill(old)
            self.event(old['id'],'camera_ownership_released',{'nextSkillId':skill['id']})

    def historical_evidence(self, skill_id=None, camera_id=None, start_at=None, end_at=None, limit=100):
        clauses=[]; params=[]
        for column,value,op in [('skill_id',skill_id,'='),("json_extract(payload,'$.cameraId')",camera_id,'='),('captured_at',start_at,'>='),('captured_at',end_at,'<=')]:
            if value is not None: clauses.append(column+op+'?'); params.append(value)
        query='SELECT payload FROM evidence'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY captured_at DESC LIMIT ?'
        with self.lock: rows=self.db.execute(query,(*params,limit+1)).fetchall()
        return [json.loads(r[0]) for r in rows[:limit]], len(rows)>limit

    def create_draft(self, prompt, devices, name='物品区域守护', target_description='待圈选物品', rules=None, replaces_id=None):
        if not devices or len(set(devices)) != len(devices): raise ValueError('请选择有效设备')
        previous = self.skill(replaces_id) if replaces_id else None
        if replaces_id and not previous: raise KeyError(replaces_id)
        rules = SkillRules.model_validate(rules or {}).model_dump()
        skill = dict(id='skill-' + uuid.uuid4().hex[:12], name=name, prompt=prompt, status='draft', revision=1,
            target=dict(description=target_description, cameraId=devices[0], channelId='main', box=dict(x=.36,y=.42,width=.12,height=.19)),
            regions={d: dict(DEFAULT_REGIONS.get(d, dict(x=.2,y=.2,width=.6,height=.6))) for d in devices},
            devices=devices, executionMode='live', mode=rules['completion'], rules=rules, result='initializing', resultReason='草案尚未启用，请检查并确认',
            alert='none', createdAt=time.time(), replacesId=replaces_id)
        if previous:
            skill['replacesRevision'] = previous['revision']
            skill['regions'] = {d: copy.deepcopy(previous['regions'].get(d, skill['regions'][d])) for d in devices}
            if previous['target']['cameraId'] in devices:
                skill['target'] = copy.deepcopy(previous['target'])
                skill['target']['description'] = target_description
        if previous and previous.get('replay'): skill['replay']=copy.deepcopy(previous['replay'])
        self.save_skill(skill)
        self.event(skill['id'], 'skill_drafted', {'revision': 1})
        return skill

    def edit(self, skill_id, edit: EditSkill):
        with self.transaction():
            skill = self.skill(skill_id)
            if not skill: raise KeyError(skill_id)
            if skill['status'] != 'draft': raise ValueError('只能编辑草案；运行中的规则请先创建修改草案')
            if skill['revision'] != edit.revision: raise ValueError('草案已更新，请重新加载')
            skill.update(edit.model_dump())
            skill.update(revision=edit.revision+1, mode=edit.rules.completion, resultReason='规则已保存，等待确认')
            self.save_skill(skill)
            self.event(skill_id, 'skill_revised', {'revision': skill['revision']})
            return skill

    def update_draft(self, skill_id, target, regions):
        s = self.skill(skill_id)
        if not s: raise KeyError(skill_id)
        return self.edit(skill_id, EditSkill(revision=s['revision'],name=s['name'],prompt=s['prompt'],target=target,regions=regions,devices=s['devices'],rules=s.get('rules',{})))

    def confirm(self, skill_id, revision, switch_from=None):
        with self.transaction():
            s = self.skill(skill_id)
            if not s: raise KeyError(skill_id)
            if s['revision'] != revision: raise ValueError('草案已变化，请重新确认最新版本')
            if s['status'] == 'active': return s
            if s['status'] != 'draft': raise ValueError('此任务不能确认启用')
            if s.get('replacesId'):
                old = self.skill(s['replacesId'])
                if not old or old['status'] not in {'active', 'paused', 'draft'} or old['revision'] != s.get('replacesRevision'):
                    raise ValueError('被修改的任务已变化，请重新生成修改草案')
            self._switch(s, switch_from, s.get('replacesId'))
            s.update(status='active',executionEpoch=uuid.uuid4().hex,result='initializing',resultReason='等待首次新鲜观察',notBefore=time.time())
            s.pop('evaluation',None)
            self.save_skill(s)
            if s.get('replacesId'):
                previous=self.skill(s['replacesId'])
                if previous and previous['status'] in {'active','paused','draft'}:
                    previous.update(status='stopped', resultReason='已被用户确认的新版本替代')
                    self.save_skill(previous)
            self.event(skill_id,'skill_confirmed',{'revision':revision})
            return s

    def lifecycle(self, skill_id, action, switch_from=None):
        with self.transaction():
            s=self.skill(skill_id)
            if not s: raise KeyError(skill_id)
            allowed={'pause':{'active'},'resume':{'paused'},'stop':{'active','paused','draft'}}
            if action not in allowed or s['status'] not in allowed[action]: raise ValueError('当前任务状态不支持此操作')
            if action=='resume':
                if s.get('needsTimingReview'):raise ValueError('旧任务需修改为按秒规则并重新验收，不能直接恢复')
                self._switch(s, switch_from)
            s['status']={'pause':'paused','resume':'active','stop':'stopped'}[action]
            if action=='resume':
                s.update(executionEpoch=uuid.uuid4().hex,result='initializing',resultReason='等待恢复后的新鲜观察，重新建立触发基线',notBefore=time.time())
                # A pause is a coverage gap, not a continuous sequence of observations.
                s['evaluation']={'episode':s.get('evaluation',{}).get('episode',0)}
            self.save_skill(s)
            self.event(skill_id,'lifecycle_changed',{'action':action})
            return s

    def recheck(self, skill_id, acknowledged=False):
        with self.transaction():
            s=self.skill(skill_id)
            if not s: raise KeyError(skill_id)
            if s['status']!='active': raise ValueError('请先恢复任务，再重新观察')
            s.update(result='unknown',resultReason='已请求复核，等待新证据',notBefore=time.time())
            cp=s.get('evaluation',{})
            cp.pop('candidate',None)
            cp.pop('lastPrimaryRequest',None)
            cp.pop('lastSupplementRequest',None)
            cp['supplementAttempts']=0
            s['evaluation']=cp
            if acknowledged and s['alert']=='open': s['alert']='acknowledged'
            return self.save_skill(s)

    def sync_observation(self, skill_id, lab):
        with self.transaction():
            s=self.skill(skill_id)
            if not s or s['status']!='active': return s
            task=lab.get('task',{}); previous=s['result']
            s['result']=task.get('result') if task.get('result') in {'confirmed','needs_attention','unknown'} else 'unknown'
            s['resultReason']=task.get('reason') or '没有有效观察'
            s['alert']=task.get('alert',s['alert'])
            observations=task.get('evidence',[])
            if observations: s['lastObservedAt']=max(o['captured_at'] for o in observations)
            if previous!=s['result']:
                self.event(skill_id,'result_changed',{'from':previous,'to':s['result'],'reason':s['resultReason']})
                if s.get('rules',{}).get('saveEvidence',True):
                    for o in observations: self.save_evidence(s,o)
            return self.save_skill(s)

    def save_evidence(self, skill, observation):
        f=observation['frame_id']; d=observation['device_id']
        item=dict(id=f"{skill['id']}:{f}",skillId=skill['id'],cameraId=d,capturedAt=observation['captured_at'],relation=observation.get('relation','unknown'),reason=observation.get('reason','观察证据'),imageUrl=observation.get('imageUrl'),revision=skill['revision'],sourceType=observation.get('source_type','fixture'),mediaStatus=observation.get('mediaStatus','pending'),frameId=f)
        with self.transaction():
            self.db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?)',(item['id'],skill['id'],item['capturedAt'],json.dumps(item,ensure_ascii=False)))

    def save_media(self, frame, raw, mime):
        if not raw or len(raw) > 8_000_000 or mime.split(';')[0] not in {'image/jpeg','image/png'}:
            raise ValueError('画面格式或大小无效')
        key = hashlib.sha256((frame['device_id'] + ':' + frame['frame_id']).encode()).hexdigest()
        payload = dict(id=key, frame=frame, imageUrl='/api/media/' + key)
        with self.transaction():
            self.db.execute('INSERT OR IGNORE INTO media VALUES (?,?,?,?)', (key, json.dumps(payload), raw, mime))
        return payload

    def media(self, key):
        with self.lock:
            row = self.db.execute('SELECT bytes,mime,payload FROM media WHERE id=?', (key,)).fetchone()
        if not row: raise KeyError(key)
        return row[0], row[1], json.loads(row[2])

    def attach_evidence_media(self, evidence_id, media=None):
        with self.transaction():
            row = self.db.execute('SELECT payload FROM evidence WHERE id=?', (evidence_id,)).fetchone()
            if not row: return
            value = json.loads(row[0])
            value.update(imageUrl=media['imageUrl'] if media else None, mediaStatus='saved' if media else 'unavailable')
            self.db.execute('UPDATE evidence SET payload=? WHERE id=?', (json.dumps(value,ensure_ascii=False), evidence_id))

    def evidence(self, limit=100):
        with self.lock: rows=self.db.execute('SELECT payload FROM evidence ORDER BY captured_at DESC LIMIT ?',(limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def event(self, run_id, event_type, payload):
        with self.transaction():
            seq=self.db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?',(run_id,)).fetchone()[0]
            at=time.time()
            self.db.execute('INSERT INTO events(run_id,sequence,type,at,payload) VALUES (?,?,?,?,?)',(run_id,seq,event_type,at,json.dumps(payload,ensure_ascii=False)))
        if getattr(self, 'ops', None):
            from .ops import CTX
            context = CTX.get()
            # run_id is also a skill/capture ID in legacy events. Do not claim
            # that it is always an Agent run or join unrelated runs together.
            allowed = {'step','name','tool','status','cameraId','deviceId','requestId','sourceType',
                       'sampledAt','receivedAt','timestampMeaning','mediaId','inputKind','code','reasonCode'}
            metadata = {k:v for k,v in payload.items() if k in allowed} if isinstance(payload,dict) else {}
            metadata.update(legacySubjectId=run_id, sequence=seq)
            self.ops.emit(event_type, data=metadata,
                status=metadata.get('status') or ('failed' if event_type.endswith('failed') else 'observed'),
                trace=context or {'traceId':'subject:'+str(run_id)})
        return dict(runId=run_id,sequence=seq,type=event_type,at=at,payload=payload)

    def events(self, run_id, after=0):
        with self.lock: rows=self.db.execute('SELECT sequence,type,at,payload FROM events WHERE run_id=? AND sequence>? ORDER BY sequence',(run_id,after)).fetchall()
        return [dict(runId=run_id,sequence=r[0],type=r[1],at=r[2],payload=json.loads(r[3])) for r in rows]

    def save_run(self, run):
        with self.transaction():
            if run.get('status') in {'completed', 'failed', 'cancelled', 'interrupted'} and not run.get('completedAt'):
                run['completedAt'] = time.time()
            self.db.execute('INSERT INTO runs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(run['id'],run['conversationId'],run['createdAt'],json.dumps(run,ensure_ascii=False)))
        return run

    def run(self, run_id):
        with self.lock: row=self.db.execute('SELECT payload FROM runs WHERE id=?',(run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def runs(self, conversation_id=None):
        with self.lock:
            rows=self.db.execute('SELECT payload FROM runs WHERE conversation_id=? ORDER BY created_at',(conversation_id,)).fetchall() if conversation_id else self.db.execute('SELECT payload FROM runs ORDER BY created_at').fetchall()
        return [json.loads(r[0]) for r in rows]

    def seed(self): pass  # User tasks are never fabricated at startup.
