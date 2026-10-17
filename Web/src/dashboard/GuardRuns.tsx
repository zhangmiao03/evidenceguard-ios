import {useState} from 'react';
import {MediaPreview} from './MediaPreview';
import {time,type MediaRow} from './MediaPanels';

export const processingReason:Record<string,string>={
  FRAMES_NOT_ADJACENT:'两帧间隔超过 1 秒',VIEW_OR_SESSION_CHANGED:'设备、会话或视角改变',
  SAME_FRAME:'重复帧',LIVE_SAMPLE_REQUIRED:'不是符合要求的实时取样',TIME_UNKNOWN:'取样时间不可确认',
  FLOW_DISABLED:'光流未开启',GUARD_AUX_DISABLED:'守护辅助处理未开启',VISUAL_BUDGET:'本轮视觉预算不足',
  LOCAL_VISION_NOT_READY:'本地视觉服务未就绪',DEPTH_MODEL_MISSING:'深度模型未就绪',
  LOCAL_VISION_BUSY:'本地视觉队列已满',LOCAL_VISION_FAILED:'辅助计算失败',LOCAL_VISION_CLOSED:'本地视觉服务已关闭',
  DIMENSIONS_CHANGED:'图像尺寸改变',REPEATED_PIXELS_NOT_PROOF_OF_STILLNESS:'重复像素不能证明静止',
  CAPTURE_UNAVAILABLE:'本次没有获得设备画面',FRAME_REJECTED:'画面未通过来源、新鲜度或视角检查',
};
const statuses:Record<string,string>={started:'处理中',completed:'已完成',skipped:'已跳过',unavailable:'不可用',failed:'失败',cancelled:'已取消',http_ok:'已返回',http_error:'请求失败'};
const outcomes:Record<string,string>={confirmed:'已确认',unknown:'无法确认',checking:'继续采样确认',issue:'需要处理',pending:'等待检查',inside:'目标在区域内',outside:'区域内未见目标'};
const text=(v:any,fallback='未记录')=>typeof v==='string'?v:fallback;
const state=(r?:MediaRow)=>r?statuses[r.status]||r.status:'未到达 / 未留存';
const ms=(n:any)=>typeof n==='number'?n<1000?Math.round(n)+' ms':(n/1000).toFixed(2)+' s':'耗时未记录';

export function GuardRuns({rows,onSelect}:{rows:MediaRow[];onSelect:(r:any)=>void}){
  const [chosen,setChosen]=useState<string>();
  const [mode,setMode]=useState<string>();
  const all=rows.filter(r=>r.name==='guard.started'&&!r.data.privateContent&&['live_guard','stored_video_replay'].includes(r.data.mode)).sort((a,b)=>b.at-a.at);
  const live=all.filter(r=>r.data.mode==='live_guard'),replays=all.filter(r=>r.data.mode==='stored_video_replay');
  const currentMode=mode||(live.length?'live_guard':'stored_video_replay');
  const starts=all.filter(r=>r.data.mode===currentMode).slice(0,12);
  const selected=starts.find(r=>r.traceId===chosen)||starts[0];
  const trace=selected?rows.filter(r=>r.traceId===selected.traceId).sort((a,b)=>a.at-b.at):[];
  const last=(name:string)=>trace.filter(r=>r.name===name).sort((a,b)=>(a.data.guardSequence||0)-(b.data.guardSequence||0)).at(-1);
  const capture=last('guard.capture'),pre=last('guard.preprocessing'),judgment=last('guard.judgment'),end=last('guard.finished');
  const models=trace.filter(r=>r.kind==='model'),prompts=trace.filter(r=>r.kind==='prompt');
  const media=prompts.flatMap(r=>r.data.inputMedia||[]);
  const by=(pattern:RegExp)=>media.filter(m=>pattern.test(m.label||''));
  const runtime=rows.find(r=>r.name==='vision_processing_status')?.data||{};
  const d=end?.data||{},aux=pre?.data||{},flow=aux.flow||{},depth=aux.depth||{};
  const replay=selected?.data.mode==='stored_video_replay';
  const result=d.disposition==='discarded'?'结果已丢弃：任务已修改或暂停':end?.status==='cancelled'?'本次检查已取消':end?.status==='failed'?'本次检查失败':outcomes[d.resultState||d.judgment?.state]||'等待最终记录';
  return <section className="eg-ops-panel eg-guard-runs" aria-label="守护逐次处理记录">
    <div className="eg-media-cardhead"><div><span className="eg-media-eyebrow">每次检查都有来路与去向</span><h2>这次守护，如何得出结果</h2><p>从同一条检查链路核对画面、辅助算法、模型调用与最终采用的判断。</p></div><span className="eg-ops-badge">{runtime.guardRunCoverage==='per_run_v1'?'逐次记录已部署':'逐次记录待部署'}</span></div>
    <p className="eg-case-footer">最近留存窗口：实时守护 {live.length} 次 · 保存视频验证 {replays.length} 次。每类展示本快照最新 12 次；旧记录和媒体会按容量淘汰。</p>
    {(live.length>0||replays.length>0)&&<div className="eg-tour-mode" aria-label="检查来源"><button aria-pressed={currentMode==='live_guard'} onClick={()=>{setMode('live_guard');setChosen(undefined);}}>实时守护</button><button aria-pressed={currentMode==='stored_video_replay'} onClick={()=>{setMode('stored_video_replay');setChosen(undefined);}}>保存视频验证</button></div>}
    {!live.length&&<p className="eg-guard-notice">尚无实时守护记录。需要 iOS App 保持真实摄像头直播并开启守护后验证。</p>}
    {!selected?<p>新记录到达后自动显示；没有记录不等于运行成功。</p>:<>
      <label className="eg-guard-picker">查看哪次检查 <select value={selected.traceId} onChange={e=>setChosen(e.target.value)}>{starts.map((r,i)=><option key={r.id} value={r.traceId}>{r.data.mode==='stored_video_replay'?'保存视频验证':'实时守护'} · {time(r.at)} · {text(r.data.title,'检查 '+(i+1))}</option>)}</select></label>
      <p className="eg-guard-result"><strong>{result}</strong><span>{ms(end?.durationMs)} · {time(selected.at)}</span></p>
      {replay&&<p className="eg-guard-notice">真实后端处理已保存视频；没有触发摄像头取流、通知或云台控制，也不计为实时验证。</p>}
      <div className="eg-pipeline eg-guard-stages">
        <div><small>01 · 画面输入</small><strong>{state(capture)}</strong><p>{replay?'来源是已保存视频帧':text(capture?.data.frame?.sourceType,'等待有效设备画面')} · {ms(capture?.durationMs)}</p></div>
        <div><small>02 · Depth / Flow</small><strong>{state(pre)}</strong><p>深度：{statuses[depth.status]||'未记录'} · 光流：{statuses[flow.status]||'未记录'}</p><p>{processingReason[flow.code||aux.code]||(flow.quality==='diagnostic_checks_passed_not_ground_truth'?'光流通过诊断检查':'')} {ms(pre?.durationMs)}</p></div>
        <div><small>03 · 模型核验</small><strong>{models.length?models.map(m=>state(m)).join(' / '):'尚未调用 / 未留存'}</strong><p>{models.map(m=>text(m.data.model)).join('、')}</p><p>{models.map(m=>ms(m.durationMs)).join(' / ')}</p></div>
        <div><small>04 · 最终处理</small><strong>{d.disposition==='replay_only'?'回放验证结果':d.disposition==='committed'?'已写入守护状态':d.disposition==='discarded'?'未采用过期结果':state(end)}</strong><p>{text(d.judgment?.reason||judgment?.data.judgment?.reason,'尚无可用判断')}</p><p>{d.alertPublished===true?'本次已生成提醒证据':d.alertPublished===false?'本次未生成提醒':''}</p></div>
      </div>
      {media.length>0&&<div className="eg-processing-media"><article><h3>实际提交 · 当前画面</h3><MediaPreview items={by(/当前采样画面.*全图/)} title="本次提交的当前画面"/></article><article><h3>实际提交 · 相对深度</h3><MediaPreview items={by(/^b 同帧相对逆深度/)} title="本次提交的相对深度"/></article><article><h3>实际提交 · 光流</h3><MediaPreview items={by(/flow|光流/i)} title="本次提交的光流"/>{flow.status==='skipped'&&<p>{processingReason[flow.code]||'本次光流跳过，不生成运动结论。'}</p>}</article></div>}
      <details className="eg-brief-details"><summary>提示词、模型正文与每步诊断（{trace.length} 条）</summary>
        <p>图像来自同一次请求的确切字节；缺失副本会标明不可用。异常、取消、旧版本与未完成记录不会补成成功。</p>
        <div className="eg-guard-events">{trace.map(r=><button key={r.id} onClick={()=>onSelect(r)}>{r.kind==='prompt'?'查看本次提示词与模型输入':r.kind==='model'?'查看模型返回正文':r.name==='guard.preprocessing'?'查看深度与光流诊断':r.name==='guard.finished'?'查看最终结果与采纳状态':r.name==='guard.judgment'?'查看模型判断与约束检查':'查看画面输入与运行状态'} · {state(r)}</button>)}</div>
        {media.length>0&&<details><summary>全部实际提交图片（{media.length} 张）</summary>{media.map((m,i)=><article key={i}><h3>{text(m.label,'输入图片 '+(i+1))}</h3><MediaPreview items={[m]} title={text(m.label,'本次模型输入')}/></article>)}</details>}
      </details>
    </>}
  </section>;
}
