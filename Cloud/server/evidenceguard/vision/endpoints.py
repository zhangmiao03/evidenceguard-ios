"""Single B-condition RGB call adapted from SeedLite's offline experiment.

Inputs are immutable Store media bound to a user's selected guard. This service
does not capture, activate, notify, or control. The older scene judgment remains
independent; an experiment receipt must never silently become a motion command.
"""
import asyncio
import base64
import hashlib
import io
import json
import math
import os
import time
from pathlib import Path

from PIL import Image
from ..harness.codex import structured_text
from ..harness.providers import OpenAICompatibleProvider
from ..ops import PRIVATE_CONTENT, traced
from .validation import schema_errors, evidence_violations
from .processing import LocalVision, VERSION as LOCAL_VERSION

VERSION = 'seedlite-endpoints-aux-v2'
PROMPT = (Path(__file__).parent / 'prompts/common.md').read_text(encoding='utf-8')
ADAPTER_PROMPT = '''本次提供首尾RGB图片；如提供同帧DepthART或短间隔DIS辅助图，其可用性、来源、质量由auxiliary字段声明；未提供时不得编造。全图始终保留，裁剪不是新时刻。没有独立上下镜头。
相对深度仅辅助同帧空间关系，不能跨帧比较归一化灰度。光流是额外短间隔取样的诊断，不等于首尾目标运动；cross_frame.motion_basis仅允许rgb或none。
target.selection=region时，人工框仅表示区域，target.description表示目标类别；不要把整个框当作具体物体或声称识别真实身份。
时间字段captured_at仅表示设备拍摄时间，sampled_at表示客户端读取直播时间；null保持未知。
这是已保存证据的只读分析，输出不能触发云台、门铃、告警或任务状态变化。图像方向可能判断错误，不提供电机方向、角度或动作参数。'''
LIMITATION = '仅比较两张已保存图片；不能证明连续过程、拿取或失窃、物理运动、米制距离，也不能直接用于自动告警或云台控制。'
PROMPT_HASH = hashlib.sha256((PROMPT + ADAPTER_PROMPT).encode()).hexdigest()


def unavailable(code, reason):
    return dict(status='unknown', code=code, reason=reason, readOnly=True,
                controlEligible=False, condition='B', promptVersion=VERSION, limitation=LIMITATION)


def image_parts(raw, box, label):
    """Preserve the complete RGB view, plus an identically defined ROI crop."""
    with Image.open(io.BytesIO(raw)) as source:
        if source.width*source.height > 20_000_000:
            raise ValueError('图片过大')
        source = source.convert('RGB')
        w, h = source.size
        left, top = int(box['x']*w), int(box['y']*h)
        right = min(w, max(left+1, math.ceil((box['x']+box['width'])*w)))
        bottom = min(h, max(top+1, math.ceil((box['y']+box['height'])*h)))
        result = []
        for name, picture, maximum in [('完整原图', source.copy(), 1280),
                                       ('同帧ROI裁剪', source.crop((left,top,right,bottom)), 768)]:
            picture.thumbnail((maximum, maximum))
            output=io.BytesIO(); picture.save(output,format='JPEG',quality=90)
            result += [dict(type='text',text=label+' · '+name),
                       dict(type='image_url',image_url={'url':'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode()})]
        return result


class EndpointVisionService:
    MAX_PENDING = 3
    MAX_WAIT = 10
    DEADLINE = 70

    def __init__(self, store, visual):
        self.store, self.visual = store, visual
        self.enabled = os.getenv('EG_ENDPOINT_ENABLED','0') == '1'
        self.port = OpenAICompatibleProvider()
        # No silent fallback to chat/video credentials or a different model.
        self.port.base_url = os.getenv('EG_ENDPOINT_BASE_URL','').rstrip('/')
        self.port.model = os.getenv('EG_ENDPOINT_MODEL_ID','')
        self.port.key = os.getenv('EG_ENDPOINT_API_KEY','')
        self.port.ready = all((self.port.base_url,self.port.model,self.port.key))
        self.profile = os.getenv('EG_ENDPOINT_PROFILE', 'dedicated')
        # Explicit deployment choice reuses the CURRENT configured video trio.
        # Never tries an old official key/endpoint after a provider failure.
        if self.profile == 'video':
            from ..video.providers import LiteVideoProvider
            source = LiteVideoProvider()
            self.port.base_url, self.port.model, self.port.key, self.port.ready = source.base, source.model, source.key, source.ready
        elif self.profile != 'dedicated': self.port.ready = False
        self.local = LocalVision()
        self.lock = asyncio.Lock()
        self.pending = 0
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS endpoint_analyses (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def configuration(self):
        return dict(enabled=self.enabled, ready=bool(self.enabled and self.port.ready),
                    model=self.port.model or None, mode='read_only', condition='B',
                    supportedConditions=['B','C'],
                    depthEnabled=self.local.configuration()['depthReady'], flowEnabled=self.local.configuration()['flowReady'],
                    modelProfile=self.profile, localVision=self.local.configuration(), promptVersion=VERSION, promptSha256=PROMPT_HASH)

    @staticmethod
    def prompt_catalog():
        # Static source text only; never camera bytes, user targets or credentials.
        return dict(operation='vision.endpoints', version=VERSION, sha256=PROMPT_HASH,
                    systemPrompt=PROMPT+'\n'+ADAPTER_PROMPT, status='available_read_only')

    def load_frame(self, receipt, camera):
        if not receipt or receipt.get('status') != 'completed':
            raise ValueError('没有已保存的有效画面')
        raw, _, saved = self.store.media(receipt['mediaId'])
        frame = saved['frame']
        if frame.get('device_id') != camera or frame.get('frame_id') != receipt.get('frameId'):
            raise ValueError('画面不属于当前设备或帧引用')
        if frame.get('source_type') != 'official_live_ios' or not frame.get('channel_id') or not frame.get('view_revision'):
            raise ValueError('缺少可核验的iOS画面来源、通道或视角')
        fields = ('frame_id','device_id','channel_id','captured_at','sampled_at','received_at','source_type',
                  'freshness','view_revision','session_id','request_id','execution_epoch','uncertainty_ms','clock_offset_ms')
        metadata = {k:frame.get(k) for k in fields}
        metadata['camera_id'] = metadata['channel_id']  # optical input, NOT physical device ID
        metadata['timestampMeaning'] = 'device_capture' if metadata['captured_at'] is not None else 'client_live_sample'
        metadata['decoderProgressVerified'] = bool(frame.get('decoder_frame'))
        return raw, metadata

    @traced('vision.endpoints')
    async def analyze(self, scene, current, still_valid, *, include_depth=False, flow_pair=None):
        if not self.enabled or not self.port.ready:
            return unavailable('NOT_CONFIGURED','首尾图分析尚未启用或模型配置不完整')
        if include_depth and not self.local.configuration()['depthReady']:
            return unavailable('DEPTH_NOT_READY','服务端深度处理尚未就绪，没有伪装成已完成深度分析')
        if not scene.get('box') or not scene.get('frame') or not scene.get('plan'):
            return unavailable('NEEDS_SELECTION','请先由用户框选并保存目标或关注区域')
        try:
            first, a = self.load_frame(scene['frame'],scene['cameraId'])
            last, b = self.load_frame(current,scene['cameraId'])
        except (KeyError,ValueError):
            return unavailable('SOURCE_INVALID','首尾画面或来源不完整，请等待该守护的新采样')
        if a['frame_id'] == b['frame_id']:
            return unavailable('NEEDS_SECOND_FRAME','只有一张画面，不能比较首尾变化')
        if a['camera_id'] != b['camera_id'] or a['view_revision'] != b['view_revision']:
            return unavailable('VIEW_CHANGED','通道、会话或视角已变化，旧ROI不可复用，请重新框选')
        clock = 'captured_at' if a['captured_at'] is not None and b['captured_at'] is not None else 'sampled_at'
        a_at, b_at = a[clock], b[clock]
        if any(type(x) not in (float,int) or not math.isfinite(x) or x<=0 for x in (a_at,b_at)) or b_at <= a_at or b_at > time.time()+.5:
            return unavailable('TIME_INVALID','无法核对首尾顺序，不能比较变化')
        if not still_valid():
            return unavailable('STALE_CONTEXT','任务修订、视角或本轮请求已变化')
        box = scene['box']
        target = dict(id=scene['id']+':'+str(scene['revision']), description=scene['plan']['target'],
                      selection=scene['plan']['selection'], bbox_a=[box[k] for k in ('x','y','width','height')])
        gates = dict(endpoint_comparison_allowed=True, roi_b_source='baseline', flow_allowed=False,
                     capturedIntervalKnown=a['captured_at'] is not None and b['captured_at'] is not None)
        meta = dict(frames={'a':a,'b':b},gates=gates)
        condition='C' if include_depth else 'B'
        context = dict(target=target,roi_a=target['bbox_a'],frames=meta['frames'],pair_gates=gates,
                       condition=condition,controlEligible=False)
        auxiliary_key = [LOCAL_VERSION, include_depth, self.local.configuration(),
                         [f.get('frame_id') for f in flow_pair[2:]] if flow_pair else None]
        key = hashlib.sha256(json.dumps([scene['clientId'],scene['id'],scene['revision'],context,auxiliary_key,
                self.port.model,self.port.base_url,PROMPT_HASH,hashlib.sha256(first).hexdigest(),hashlib.sha256(last).hexdigest()],
                sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if self.pending >= self.MAX_PENDING:
            return unavailable('QUEUE_FULL','首尾图分析队列已满，请稍后重试')
        self.pending += 1
        acquired = False
        privacy = PRIVATE_CONTENT.set(True)
        started = time.monotonic()
        try:
            await asyncio.wait_for(self.lock.acquire(),timeout=self.MAX_WAIT)
            acquired = True
            if not still_valid(): return unavailable('STALE_CONTEXT','任务或画面已变化，未调用模型')
            with self.store.lock:
                row=self.store.db.execute('SELECT payload FROM endpoint_analyses WHERE id=?',(key,)).fetchone()
            if row: return json.loads(row[0]) | {'cached':True}
            reason=self.visual.reserve(scene['cameraId'],'endpoint:'+key,images=4+(2 if include_depth else 0)+(1 if flow_pair else 0),event_limit=2)
            if reason: return unavailable('BUDGET_EXHAUSTED',reason)
            async with asyncio.timeout(self.DEADLINE):
                auxiliary = await self.local.analyze(first,last,a,b,depth=include_depth,flow_pair=flow_pair)
                if include_depth and auxiliary.get('depth',{}).get('status') != 'completed':
                    return unavailable('DEPTH_PROCESSING_FAILED','深度处理未完成，请稍后重试；没有使用伪造的深度图')
                context['auxiliary'] = {k:v for k,v in auxiliary.items() if k!='images'}
                content=[dict(type='text',text=json.dumps(context,ensure_ascii=False))]
                for label,raw in [('a',first),('b',last)]:
                    content += await asyncio.to_thread(image_parts,raw,box,label)
                content += self.local.parts(auxiliary)
                options=dict(response_format={'type':'json_object'},max_tokens=2500)
                if self.port.model.startswith('doubao-'): options['thinking']={'type':'disabled'}
                answer=await self.port._request([dict(role='system',content=PROMPT+'\n'+ADAPTER_PROMPT),
                                                dict(role='user',content=content)],options)
                raw_answer=structured_text(answer.get('content') or '')
                if answer.get('tool_calls') or len(raw_answer)>48000: raise ValueError('invalid response size/type')
                analysis=json.loads(raw_answer)
                errors=schema_errors(analysis,{'target':target},meta,condition)+evidence_violations(analysis,{'target':target},meta,condition)
                if errors:
                    return unavailable('INVALID_MODEL_RESULT','模型结果未通过结构或证据约束校验') | {'validationErrors':errors[:12]}
            if not still_valid(): return unavailable('STALE_CONTEXT','分析期间任务或视角已变化，结果已丢弃')
            result=dict(status='completed',id=key,readOnly=True,controlEligible=False,cached=False,
                        condition=condition,model=self.port.model,promptVersion=VERSION,promptSha256=PROMPT_HASH,
                        analysis=analysis,sources=meta['frames'],createdAt=time.time(),latencyMs=round((time.monotonic()-started)*1000),
                        limitation=LIMITATION,semanticValidation='requires_human_review',isLiveConclusion=False,
                        auxiliary=context['auxiliary'])
            with self.store.transaction():
                self.store.db.execute('INSERT OR REPLACE INTO endpoint_analyses VALUES (?,?)',(key,json.dumps(result,ensure_ascii=False)))
            return result
        except asyncio.CancelledError: raise
        except TimeoutError: return unavailable('TIMEOUT','分析排队或模型调用超时，未形成结论')
        except Exception: return unavailable('MODEL_UNAVAILABLE','首尾图分析失败，未把失败解释为正常或未发生')
        finally:
            if acquired: self.lock.release()
            self.pending -= 1
            PRIVATE_CONTENT.reset(privacy)
