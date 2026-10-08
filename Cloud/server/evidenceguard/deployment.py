"""Site acceptance is distinct from offline rule trials and user preparation."""
import hashlib,json

CAMERA_SITES={
    'cam-a':dict(name='屋檐摄像头',position='eaves',use='候选远景：观察室外通道和来去方向；小包裹是否足够清楚需实测。'),
    'cam-b':dict(name='门铃摄像头',position='doorbell',use='候选近景：观察门前包裹；需确认地面不在画面盲区，且人物不会持续挡住目标。'),
}

def plan(skill,manifests=(),completed=()):
    from .schemas import SkillRules
    rules=SkillRules.model_validate(skill.get('rules',{}));period=rules.sampleIntervalSeconds
    wait=rules.confirmationSeconds+2*period
    lookup={m.id:m for m in manifests};cameras=[]
    for device in skill.get('devices',[]):
        site=CAMERA_SITES.get(device,dict(name=device,position='unknown',use='请提供安装位置和实际视野'))
        m=lookup.get(device)
        cameras.append(dict(id=device,name=site['name'],position=site['position'],candidateUse=site['use'],verdict='待实际画面验证',reason='当前只有合成测试源，无法确认实机视野。' if m and m.adapter.startswith('fixture') else '尚无绑定当前安装视角的真机验收证据。'))
    steps=[
        ('placement','确认所选设备的安装位置、朝向及包裹所在位置；角色只是候选用途，不代表视野已合格。'),
        ('visibility',f'把目标放在关注区域并退开，保持至少 {wait} s；检查所选视角能否清楚看到目标；单视角不清楚时，再考虑加入另一台设备。'),
        ('negative',f'从目标旁经过但不拿走，录制至少 {wait} s；人工确认预期是不提醒。'),
        ('positive',f'目标清晰在场后再移出区域，移出后保持至少 {wait} s；人工确认预期是提醒。'),
        ('occlusion','遮挡目标再退开：遮挡时应无法确认，不能直接认定目标离区。'),
    ]
    unsupported=rules.taskKind not in {'parcel_removal','marker_region'}
    if unsupported:steps=[('define','先明确可观察条件并等待对应执行器；当前无需进行设备发布验收。')]
    return dict(status='unsupported' if unsupported else 'needs_user_action',canPublish=False,
        summary='此任务尚无对应执行器，不能发布。' if unsupported else '需要设备视野与正反例验收；录像试跑不能替代真机验收。',
        cameras=cameras,actions=[dict(id=k,instruction=v,completed=k in completed) for k,v in steps],
        blockers=['T8171 / T8214 正式 SDK 和实际取图周期尚未验证。','当前无真机通用视觉守护执行器。','缺少当前安装角度下的目标可见性、正例、反例和遮挡验收。'],
        sampleIntervalSeconds=period,confirmationSeconds=rules.confirmationSeconds,
        note='勾选仅记录用户已完成准备，不会将设备判为合格，也不会自动发布。')

def preparation_key(skill):
    data={k:skill.get(k) for k in ['revision','devices','target','regions','rules','replay']}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

class SitePreparation:
    def __init__(self,store):
        self.store=store
        with store.transaction():store.db.execute('CREATE TABLE IF NOT EXISTS site_preparation (skill_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, completed TEXT NOT NULL)')
    def read(self,skill,manifests=()):
        with self.store.lock:row=self.store.db.execute('SELECT fingerprint,completed FROM site_preparation WHERE skill_id=?',(skill['id'],)).fetchone()
        completed=json.loads(row[1]) if row and row[0]==preparation_key(skill) else []
        return plan(skill,manifests,completed)
    def update(self,skill,revision,action,completed,manifests=()):
        with self.store.transaction():
            current=self.store.skill(skill['id'])
            if current['revision']!=revision:raise ValueError('草案已变化，请刷新验收准备')
            result=self.read(current,manifests)
            if action not in {a['id'] for a in result['actions']}:raise ValueError('未知准备步骤')
            chosen={a['id'] for a in result['actions'] if a['completed']}
            if completed:chosen.add(action)
            else:chosen.discard(action)
            self.store.db.execute('INSERT INTO site_preparation VALUES (?,?,?) ON CONFLICT(skill_id) DO UPDATE SET fingerprint=excluded.fingerprint,completed=excluded.completed',(current['id'],preparation_key(current),json.dumps(sorted(chosen))))
            return self.read(current,manifests)
