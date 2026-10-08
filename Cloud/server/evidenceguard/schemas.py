from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ROI(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def within_frame(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("圈选区域不能超出画面")
        return self

class SkillRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taskKind: Literal['unspecified','parcel_removal','marker_region','pet_activity','vehicle_activity','custom'] = 'unspecified'
    durationSeconds: float = Field(default=0,ge=0,le=86400,description='需求中的持续秒数；当前执行器尚不支持大于0，不能用观察次数替代')
    trigger: Literal["leaves_region", "enters_region", "record_activity"] = "leaves_region"
    minConfidence: float = Field(default=.85, ge=.5, le=1)
    sampleIntervalSeconds: int = Field(default=3, ge=3, le=300)
    confirmationSeconds: int = Field(default=6, ge=3, le=600)

    @model_validator(mode='before')
    @classmethod
    def legacy_frames(cls,value):
        if isinstance(value,dict) and 'consecutiveFrames' in value:
            value=dict(value);count=value.pop('consecutiveFrames')
            # Migrate old records without retaining a frame-count execution path.
            value.setdefault('confirmationSeconds',max(3,(int(count)-1)*max(3,int(value.get('sampleIntervalSeconds',3)))))
        return value
    @model_validator(mode='after')
    def timing_bounds(self):
        if self.confirmationSeconds < self.sampleIntervalSeconds:
            raise ValueError('确认跨度不得小于检测间隔')
        return self

    unknownPolicy: Literal["hold_and_recheck"] = "hold_and_recheck"
    completion: Literal["continuous", "once"] = "continuous"
    saveEvidence: bool = True
    description: str = Field(default="按秒抽样确认关注区域状态，无法确认时保留判断", min_length=2, max_length=300)

class Target(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    cameraId: str
    channelId: str = "main"
    box: ROI

class ReplayConfig(BaseModel):
    recordingId: str = Field(min_length=1,max_length=100)

class EditSkill(BaseModel):
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=2, max_length=2000)
    target: Target
    regions: dict[str, ROI]
    devices: list[str] = Field(min_length=1, max_length=2)
    rules: SkillRules

    @model_validator(mode="after")
    def device_regions(self):
        if len(set(self.devices)) != len(self.devices) or set(self.regions) != set(self.devices):
            raise ValueError("每个所选摄像头必须有独立的关注区域")
        if self.target.cameraId not in self.devices:
            raise ValueError("目标摄像头必须在所选设备中")
        return self


    replay: ReplayConfig | None = None
