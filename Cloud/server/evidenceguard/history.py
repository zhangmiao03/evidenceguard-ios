"""User-selected history scope, kept outside model-controlled tool arguments."""
from __future__ import annotations
import math, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator

class HistoryFilter(BaseModel):
    model_config=ConfigDict(extra='forbid')
    period: Literal['all','today','yesterday','last_24_hours','custom']
    startAt: float | None=None
    endAt: float | None=None
    @model_validator(mode='after')
    def valid_range(self):
        if self.period=='custom':
            if self.startAt is None or self.endAt is None or not all(math.isfinite(x) and x>=0 for x in [self.startAt,self.endAt]) or self.startAt>=self.endAt:
                raise ValueError('自定义时间需要有效的开始和结束时间，且开始早于结束')
        elif self.startAt is not None or self.endAt is not None:
            raise ValueError('仅自定义时间允许传入起止时间')
        return self


def resolve_filter(value, now=None, timezone='Asia/Shanghai'):
    if value is None: return None
    value=HistoryFilter.model_validate(value)
    now=time.time() if now is None else now
    midnight=datetime.fromtimestamp(now,ZoneInfo(timezone)).replace(hour=0,minute=0,second=0,microsecond=0)
    start=end=None
    if value.period=='custom': start,end=value.startAt,value.endAt
    elif value.period=='today': start,end=midnight.timestamp(),now
    elif value.period=='yesterday': start,end=(midnight-timedelta(days=1)).timestamp(),midnight.timestamp()
    elif value.period=='last_24_hours': start,end=now-86400,now
    return dict(period=value.period,startAt=start,endAt=end,timezone=timezone)
