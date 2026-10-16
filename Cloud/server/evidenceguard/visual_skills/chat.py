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
        async def analyze(guard_id, revision):
            return await scenes.analyze_endpoints(guard_id,client,revision,run=run)
        result.register('analyze_visual_endpoints',analyze,AnalyzeGuard,
                        '只读对照本人守护中已确认ROI的参考图和最近已保存采样。先读取guard_id与revision；不接受任意路径或媒体ID，不取新图，不通知或控制设备。结果controlEligible始终false，图像方向不能变成云台命令。')
    return result
