"""Executable contracts are server-owned; model prose never grants a capability."""
from __future__ import annotations
import hashlib,json,math
from .schemas import SkillRules
from .deployment import plan

CONTRACT_VERSION='visual-contract/v2-seconds'
CATALOG=[
    dict(kind='parcel_removal',name='包裹区域状态变化',scope='仅已存录像回放',conditions=['先建立包裹在场基线','按秒抽样检查区域内是否可见','观察跨度满足确认时长'],missing=['正式摄像头实时输入']),
    dict(kind='marker_region',name='测试标记区域进出',scope='仅合成测试摄像头',conditions=['标记编号17','先确认触发前的位置','新鲜且连续的观察'],missing=['通用物体识别']),
    dict(kind='pet_activity',name='宠物行为',scope='暂不支持',conditions=[],missing=['行为定义及对应视觉执行器']),
    dict(kind='vehicle_activity',name='车辆行为',scope='暂不支持',conditions=[],missing=['车辆执行器']),
    dict(kind='custom',name='其他自定义需求',scope='暂不支持',conditions=[],missing=['经过验证的执行器']),
]

def assess(skill, videos=None, manifests=()):
    rules=SkillRules.model_validate(skill.get('rules',{})).model_dump();kind=rules.get('taskKind','unspecified');replay=skill.get('replay')
    result=dict(version=CONTRACT_VERSION,taskKind=kind,status='unsupported',label='暂不支持',canActivate=False,canTrial=False,executor=None,
        blockers=[],warnings=[],contract=None,deployment=plan(skill,manifests))
    def block(reason,status='unsupported',label='暂不支持'):
        result.update(status=status,label=label);result['blockers'].append(reason);return result
    if kind=='unspecified':return block('请明确选择任务类型；已有草案不会自动推断执行能力。','needs_input','需完善条件')
    if kind not in {'parcel_removal','marker_region'}:return block('当前没有这种任务的视觉执行器，请先明确可观察行为并保留为需求。')
    if rules.get('durationSeconds',0)>0:return block('额外行为持续秒数触发尚未实现；不能用采样确认跨度替代该行为要求。')
    if rules.get('unknownPolicy')!='hold_and_recheck':return block('当前仅支持看不清时保留判断。')
    if not rules.get('saveEvidence'):return block('此执行合同要求保留触发证据。')
    period=rules['sampleIntervalSeconds'];span=rules['confirmationSeconds'];effective=math.ceil(span/period)*period
    if kind=='parcel_removal':
        if rules.get('trigger')!='leaves_region':return block('包裹执行器只判断包裹在关注区域的可见状态，不支持其他触发条件。')
        if not replay:return block('请在观察输入中选择已导入录像；正式摄像头守护尚未接通。','needs_input','需选择录像')
        if span<period:return block('确认观察跨度不能小于检测间隔。','needs_input','需调整秒数')
        if rules.get('completion')!='once':return block('有限回放只执行一次，首次提醒或片尾结束。','needs_input','需调整规则')
        if not videos or not videos.vision.ready:return block('视频模型尚未配置。','needs_input','模型未就绪')
        try:
            r=videos.db.recording(replay['recordingId']);videos.file(r['id'])
        except (KeyError,ValueError):return block('所选录像不存在或不可播放。','needs_input','需选择录像')
        if skill.get('devices')!=[r['cameraId']] or skill.get('target',{}).get('cameraId')!=r['cameraId']:return block('回放必须绑定录像所属的单台摄像头。','needs_input','摄像头不匹配')
        if not 2<=(r.get('duration') or 0)<=60:return block('试跑使用 2–60 秒录像。','needs_input','录像时长不支持')
        result.update(status='replay_only',label='仅支持回放验证',canActivate=True,canTrial=True,executor='parcel-samples/v2',
            contract=dict(precondition='先在采样图中清楚看见目标包裹位于关注区域内',trigger='清晰区域内按间隔采样未见原目标，提醒核验；不声称看见拿取动作',temporal=f'Every {period} s：每 {period} s 抽一张图；相邻有效观察跨度至少 {span} s（按此间隔实际需至少 {effective} s）；不证明采样间连续状态',unknown='遮挡、无法确认、请求失败均不认定拿走',evidence='保留截至触发时刻已到达的视频片段和相对时间',completion='首次提醒、片尾或20次观察后结束'),
            warnings=['抽样可能漏掉间隔内的短动作；原片变化时间只能给出观察区间。','回放通过不代表真机可用或模型可靠性验收通过。'])
    else:
        if replay:return block('测试标记执行器不能分析普通录像，请选择包裹拿取类型或合成测试源。')
        if rules.get('trigger') not in {'leaves_region','enters_region'}:return block('测试标记仅支持区域进入或离开。')
        lookup={m.id:m for m in manifests}
        if not skill.get('devices') or any(d not in lookup or not lookup[d].adapter.startswith('fixture-lab') or lookup[d].connection!='online' for d in skill['devices']):
            return block('所选设备不是就绪的合成测试摄像头；正式 SDK 仍待联调。','needs_input','测试源未就绪')
        result.update(status='executable',label='可执行 · 测试标记',canActivate=True,executor='fixture-marker/v1',
            contract=dict(precondition='先观察到标记17处于触发前的位置',trigger='标记进入区域' if rules['trigger']=='enters_region' else '标记离开区域',temporal=f'每 {period} s 检测；同一状态的有效观察跨度至少 {span} s；重复帧与缺口不累计',unknown='遮挡、过期或视角冲突时保留判断',evidence='持久化触发观察图片',completion='按一次性或持续配置执行'),warnings=['仅验证测试标记，不代表能识别所描述的真实对象。'])
    return result

def fingerprint(skill,videos):
    r=videos.db.recording(skill['replay']['recordingId']) if skill.get('replay') else {}
    value={k:skill.get(k) for k in ['name','prompt','target','regions','devices','rules','replay']}
    value.update(contract=CONTRACT_VERSION,recordingDigest=r.get('sha256'),duration=r.get('duration'),model=getattr(videos.vision,'model','test'),base=getattr(videos.vision,'base',''))
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
