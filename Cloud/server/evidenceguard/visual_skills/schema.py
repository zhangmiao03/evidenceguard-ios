from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from ..schemas import ROI


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ScenePlan(Input):
    title: str = Field(min_length=1, max_length=60)
    target: str = Field(min_length=1, max_length=200)
    selection: Literal['object', 'region']
    trigger: Literal['enters', 'leaves']
    confirmationSeconds: int = Field(default=15, ge=15, le=600)
    completion: Literal['once', 'continuous'] = 'continuous'


class Interpretation(Input):
    plan: ScenePlan | None
    question: str = Field(default='', max_length=300)
    unsupportedReason: str = Field(default='', max_length=300)


class Create(Input):
    requestId: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    cameraId: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=2, max_length=2000)


class Revision(Input):
    revision: int = Field(ge=1)


class Interpret(Revision):
    requestId: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    message: str = Field(min_length=1, max_length=2000)


class Selection(Revision):
    frameId: str
    box: ROI


class Judgment(Input):
    state: Literal['inside', 'outside', 'unknown']
    regionClear: bool
    identityClear: bool
    reason: str = Field(min_length=1, max_length=500)


def summary(plan):
    if not plan:
        return '说说要关注什么，以及什么情况下提醒你。'
    condition = '进入' if plan['trigger'] == 'enters' else '离开'
    return f"关注{plan['target']}，确认{condition}所选区域后提醒你；至少两次采样，观察跨度不少于{plan['confirmationSeconds']}秒。"


LIMITATION = '需要保持 App 在前台并连接画面；锁屏或断流时暂停判断。离散采样可能漏过短暂变化，不能证明采样间隔内的持续状态。'
