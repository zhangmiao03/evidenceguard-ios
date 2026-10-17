"""Native chat uses the same draft service as the camera guard editor.

Compilation is queued, never awaited while the chat owns the Codex gate.
No activation, selection, or pause authority is exposed to the model.
"""
import hashlib
from pydantic import Field
from ..harness.tools import Arguments, ToolRegistry
from .schema import Create, Interpret

GUIDANCE = '''本轮 iOS 使用新版“摄像头守护”，导航为助手/摄像头守护/设备/记忆/我的。用户不需要理解 Skill、执行器或代码。
新增摄像头守护只调用 create_camera_guard，修改待确认草稿用 revise_camera_guard，不使用旧 draft_visual_skill 或旧模板能力结论。create_camera_guard 与摄像头页“添加守护”共用同一个服务；返回仅表示原话已保存并排队整理，不能说已完成理解、框选、检查或开启。
需求可以是可见对象进入/离开区域；保持用户要求，含不支持条件也原样交给草稿整理器，不伪装为包裹规则。保存后提示用户点击卡片，在摄像头守护中继续框选并确认。生成/改草稿后结束当前回复，不循环等待编译；编译会在本轮释放模型后继续。
用户只是查询画面/历史时不创建；非摄像头的普通待办仍可保存个人事项。涉及持续看守、某物进入或离开时提醒等视觉需求，使用新版守护草稿而不是只保存一个设备标签提醒。已有守护先 list_camera_guards/read_camera_guard；只有草稿可修改，已开启规则需新建并重新确认，不能声称自动替换。
前台连接由 App 自动维护；断网、锁屏、摄像头离线时据实说明。没有真实新画面不能保证在线或安全。用户仍可暂停某项守护，暂停规则不等于关闭摄像头。'''
GUIDANCE += '''
用户要求对照某项已框选守护的参考图和最近采样时，可调用 analyze_visual_endpoints。它只读已保存的首尾图，不补取实时图片，不修改守护结论；缺少后帧则说明等待采样。completed只表示分析完成，unknown不能解释为正常。图片方向、not_seen和深度描述不构成云台动作依据。
设备控制只根据用户明确的控制要求，使用单独已授权工具及确认卡；先暂停占用设备的守护，切换视角后重新框选。不得为了补全视觉结论自行连续转动或自动重发命令。'''
GUIDANCE += '''
用户明确要求把已框选的目标调整到画面中央时，可调用 aim_camera_at_guard_target，勿自行从图片方向拼接云台参数。
该工具先检查原生解码凭据与硬件验收，再定位目标并生成一次单步确认卡。blocked/unknown不表示已移动；不得绕过缺少的解码凭据或反复调用。
确认后服务端只做一次动作后观察，可用 read_visual_control 读取结果；SDK接受、图像位置改善、机械停止、人工验收是不同结论。'''
GUIDANCE += '''用户明确要求现在采样并分析深度/短时变化时，用sample_camera_vision请求两次真实画面。
光流可能因取样间隔过大、视角变化、重复像素或质量不足而跳过，必须转述原因；不得说连续追踪已开启。'''


class Draft(Arguments):
    message: str = Field(min_length=2, max_length=2000, description='忠实保留用户需求与相关补充，不丢掉不支持的条件。')
    camera_id: str | None = Field(default=None, max_length=100)


class Guard(Arguments):
    guard_id: str = Field(min_length=1, max_length=100)


class Revise(Guard):
    revision: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=2000)

class AnalyzeGuard(Guard):
    revision: int = Field(ge=1)
    include_depth: bool = Field(default=False, description='需要DepthART辅助时设为true；未部署时明确不可用，不用RGB冒充。')

class AimGuard(Guard):
    revision: int = Field(ge=1)

class ControlResult(Arguments):
    control_id: str = Field(min_length=1,max_length=100)


def for_chat(registry, scenes, run):
    result = ToolRegistry()
    removed = {'draft_visual_skill', 'list_skill_capabilities'}
    result._tools = {k:v for k,v in registry._tools.items() if k not in removed}
    result._specs = {k:v for k,v in registry._specs.items() if k not in removed}
    client = run['clientId']
    request_id = 'chat-' + hashlib.sha256(run['id'].encode()).hexdigest()[:40]

    def receipt(scene):
        value = scenes.public(scene)
        return dict(guardId=value['id'], revision=value['revision'], status=value['status'], stage=value['stage'],
                    prompt=value['prompt'], question=value['question'], summary=value['summary'],
                    unsupportedReason=value['unsupportedReason'], destination='camera_guard',
                    reason='草稿已保存，尚未开启；请在摄像头守护继续框选和确认。')

    async def create(message, camera_id=None):
        camera = camera_id or run.get('cameraId')
        if not camera: raise ValueError('请先选择要添加守护的摄像头')
        scene = await scenes.create(client, Create(requestId=request_id, cameraId=camera, message=message))
        return receipt(scene)

    async def revise(guard_id, revision, message):
        return receipt(scenes.interpret(guard_id, client, Interpret(requestId=request_id, revision=revision, message=message)))

    async def read(guard_id): return scenes.public(scenes.get(guard_id, client))

    async def listing():
        values = scenes.list_all(client)
        return {'guards':[{k:scenes.public(s)[k] for k in ('id','cameraId','revision','status','stage','summary','result')} for s in values[:50]],
                'total':len(values), 'truncated':len(values)>50,
                'limitation':'只读当前用户最近50项守护；具体运行状态与检查结果用 read_camera_guard 读取。'}

    result.register('create_camera_guard', create, Draft, '保存新版摄像头守护草稿，与摄像头页添加守护相同。原话排队整理后，用户框选并确认才开启；返回后结束本轮，不等待编译。')
    result.register('revise_camera_guard', revise, Revise, '根据新补充修改本人待确认守护，保留原条件；需要当前 revision。已开启规则不修改，不自动启用。')
    result.register('read_camera_guard', read, Guard, '读取本人守护草稿/状态/问题及最近检查，不能开启、暂停或控制设备。')
    result.register('list_camera_guards', listing, description='列出本人摄像头守护，包括未确认草稿，供选择和继续设置。')
    if scenes.endpoint_vision and scenes.endpoint_vision.enabled:
        async def analyze(guard_id, revision, include_depth=False):
            return await scenes.analyze_endpoints(guard_id,client,revision,run=run,include_depth=include_depth)
        result.register('analyze_visual_endpoints',analyze,AnalyzeGuard,
                        '只读对照本人守护中已确认ROI的参考图和最近已保存采样。先读取guard_id与revision；不接受任意路径或媒体ID，不取新图，不通知或控制设备。结果controlEligible始终false，图像方向不能变成云台命令。')
        async def sample(guard_id,revision):return await scenes.sample_endpoints(guard_id,client,revision,run=run)
        result.register('sample_camera_vision',sample,AimGuard,
                        '为本人已框选守护请求两次新画面，运行DepthART及满足条件时的DIS，再交图像模型分析；12秒采样上限，不创建或修改守护，不控制设备。')
    controller=getattr(scenes,'visual_control',None)
    if controller and controller.enabled:
        async def aim(guard_id,revision):
            return await controller.aim(guard_id,revision,run)
        async def control_result(control_id):return controller.result(control_id,client)
        result.register('aim_camera_at_guard_target',aim,AimGuard,
                        '仅用于用户明确要求将已框选目标调到画面中央。需要T8171、暂停守护、原生解码证明与本机验收；仅生成一次现有确认卡，后端自动观察动作结果，不自动连续追踪。')
        result.register('read_visual_control',control_result,ControlResult,'读取本人视觉调位的SDK操作及后续图像复核结果；不会重发动作。')
    return result
