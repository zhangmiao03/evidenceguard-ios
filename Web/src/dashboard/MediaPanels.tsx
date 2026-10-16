import { useState } from "react";
import "./media.css";

type RecordRow = { id:string; kind:string; name:string; at:number; status:string; data:Record<string,any> };
const time = (n:any) => typeof n === 'number' && n > 0 ? new Date(n*1000).toLocaleString('zh-CN',{hour12:false}) : '未采集';
const seconds = (n:any) => typeof n === 'number' ? `${n.toFixed(1)} s` : '—';
const text = (v:any) => typeof v === 'string' ? v : v == null ? '' : JSON.stringify(v);
const origin = (s:any) => s === 'official_sdk' ? '官方 SDK 导入' : s === 'synthetic_review' ? '合成测试素材 · 真实入库' : s || '数据库快照';
const compatible = (v:any) => v === true ? '当前签名匹配' : v === false ? '签名不匹配' : '当前签名未采集';

export function ImageAnalysis({rows,coverage,onSelect}:{rows:RecordRow[];coverage?:Record<string,any>;onSelect:(row:any)=>void}) {
  const [group,setGroup] = useState('episodes');
  const names:Record<string,string>={episodes:'media_sdk_episodes',evidence:'media_evidence',cache:'media_visual_cache'};
  const items=rows.filter(r=>r.name===names[group]);
  const calls=rows.filter(r=>r.kind==='model' && ['image_review','frame_presence','video_verify'].includes(r.name));
  return <div className="eg-media">
    <section className="eg-ops-panel eg-media-intro"><span className="eg-media-eyebrow">VISUAL OBSERVATIONS</span><h2>看见了什么，哪些还不能确认</h2><p>查阅离散图片的核验结果、视觉模型调用和证据来源。图片核验不等同于连续视频判断；原始画面不会通过免登录页面公开。</p><small>来源：当前环境 SQLite 业务库与模型追踪库 · 数据快照 {time(coverage?.sampledAt)} · 每张卡可展开脱敏正文</small></section>
    <div className="eg-media-tabs" aria-label="视觉数据类别">{[['episodes','设备事件核验'],['evidence','图片证据结果'],['cache','视觉结果缓存']].map(([id,label])=><button key={id} aria-pressed={id===group} onClick={()=>setGroup(id)}>{label} · {rows.filter(r=>r.name===names[id]).length}</button>)}</div>
    <div className="eg-media-cards">{items.slice(0,120).map(r=>{
      const d=r.data, wrapper=d.review||d.visualReview||{}, review=wrapper.review||wrapper;
      return <article className="eg-ops-panel" key={r.id}><div className="eg-media-cardhead"><span className="eg-media-icon">▧</span><div><h3>{d.deviceName||d.cameraId||'视觉核验记录'}</h3><small>{origin(d.sourceType || (group==='episodes'?'official_sdk':null))}</small></div><span className="eg-ops-badge">{d.reviewStatus||d.status||r.status}</span></div>
        <dl className="eg-media-observation"><dt>可见事实 / 已保存结论</dt><dd>{text(review.visible||review.summary||d.reason||wrapper.reason)||'尚无可用的核验正文'}</dd><dt>未知与限制</dt><dd>{text(review.uncertainties||wrapper.limitation||d.limitation)||'仅适用于本条已采集证据；不能据此保证当前现场状态。'}</dd></dl>
        <small>{d.updatedAt?'业务更新时间':'记录的观察 / 取样时间'}：{time(d.updatedAt||d.capturedAt||d.observedAt||d.sampledAt)} · 读取时间：{time(r.at)}</small>
        <button onClick={()=>onSelect(r)}>查看完整结果与来源</button></article>;
    })}</div>
    {!items.length && <div className="eg-ops-panel eg-media-empty"><h3>当前范围没有这类图片分析记录</h3><p>检查环境与筛选。未采集与未调用不代表识别成功；设备事件导入并完成视觉核验后，这里会自动更新。</p></div>}
    <section className="eg-ops-panel"><h2>视觉模型调用 · 当前筛选 {calls.length} 次</h2><p className="eg-ops-note">以下来自实际模型埋点。历史数据库结果可能早于采集启用，不能还原未记录的提示词。</p><div className="eg-media-calllist">{calls.slice(-40).reverse().map(r=><button key={r.id} onClick={()=>onSelect(r)}><span>{r.name}<small>{r.data.model||'模型未记录'} · {time(r.at)}</small></span><span>{r.status} →</span></button>)}</div>{!calls.length&&<small>当前时间范围未记录视觉模型调用。</small>}</section>
    {coverage?.status!=='connected'&&<p className="eg-ops-notice">媒体索引采集尚未连接；上方可能是离线导入数据。</p>}
  </div>;
}

export function VideoIndex({rows,coverage,onSelect}:{rows:RecordRow[];coverage?:Record<string,any>;onSelect:(row:any)=>void}) {
  const recordings=rows.filter(r=>r.name==='media_recordings'), segments=rows.filter(r=>r.name==='media_video_segments');
  const [chosen,setChosen]=useState('');
  const active=recordings.find(r=>r.data.id===chosen)||recordings[0];
  const clips=segments.filter(r=>r.data.recordingId===active?.data.id).sort((a,b)=>a.data.start-b.data.start);
  const total=coverage?.tables?.video_segments;
  const compatibleCount=segments.filter(r=>r.data.signatureCompatible===true).length;
  return <div className="eg-media">
    <section className="eg-ops-panel eg-media-intro"><span className="eg-media-eyebrow">VIDEO MEMORY INDEX</span><h2>从录像片段，到可核验的记忆</h2><p>查看真实落库的录像与向量。检索相似度用于候选排序，最终结论仍需视觉模型复核。素材类型单独标注，测试录像不会显示为真实摄像头录像。</p><small>数据库采样 {time(coverage?.sampledAt)} · 只读展示，不触发付费嵌入、重建索引或设备操作。</small></section>
    <div className="eg-media-metrics">{[['库内切片总数',total?.total ?? '未知'],['当前筛选切片',segments.length],['当前签名匹配',coverage?.currentSignature?compatibleCount:'未采集'],['采样无效向量',coverage?.invalidVectorsInSample??'未知']].map(([label,value])=><div className="eg-ops-panel" key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
    <div className="eg-media-pipeline"><span>录像入库</span><b>→</b><span>重叠切片</span><b>→</b><span>多模态向量</span><b>→</b><span>相似度召回</span><b>→</b><span>视觉复核 + 时间点</span></div>
    <div className="eg-media-indexgrid"><section className="eg-ops-panel"><h2>录像 · 当前筛选 {recordings.length} 条</h2><div className="eg-media-calllist">{recordings.map(r=><button key={r.id} aria-pressed={active?.id===r.id} onClick={()=>setChosen(r.data.id)}><span>{r.data.title||r.data.id}<small>{origin(r.data.sourceType)} · {seconds(r.data.duration)}</small></span><span>{r.data.status} →</span></button>)}</div>{!recordings.length&&<p className="eg-ops-note">没有已采集的录像条目。上传或导入后端录像后刷新；不会用示例数据填充此列表。</p>}</section>
      <section className="eg-ops-panel"><h2>{active?.data.title||'片段索引'}</h2>{active&&<><p className="eg-ops-note">{origin(active.data.sourceType)} · {active.data.cameraId} · {compatible(active.data.signatureCompatible)}</p><dl className="eg-media-observation"><dt>Embedding 模型</dt><dd>{active.data.embeddingModel||'尚未记录'}</dd><dt>索引签名</dt><dd className="eg-media-code">{active.data.embeddingSignature||'尚未生成'}</dd></dl><button onClick={()=>onSelect(active)}>查看录像元数据</button></>}
      <div className="eg-media-timeline" aria-label="录像切片时间轴">{clips.map(r=><button key={r.id} onClick={()=>onSelect(r)} style={{width:`${Math.max(10,Math.min(100,(r.data.end-r.data.start)/Math.max(1,active?.data.duration||1)*100))}%`,marginLeft:`${Math.min(90,r.data.start/Math.max(1,active?.data.duration||1)*100)}%`}}>{seconds(r.data.start)} → {seconds(r.data.end)}</button>)}</div>
      {clips.map(r=><div className="eg-media-vector" key={r.id}><div className="eg-media-cardhead"><strong>{seconds(r.data.start)} — {seconds(r.data.end)}</strong><span>{r.data.dimensions??'未知'} 维</span><span className="eg-ops-badge">{r.data.status}</span></div><small>范数 {r.data.norm??'无效'} · {r.data.normalized?'已归一化':'未归一化 / 无效'} · {compatible(r.data.signatureCompatible)}</small><div className="eg-media-bars" aria-label="向量前 16 维预览">{(r.data.vectorPreview||[]).map((v:number,i:number)=><span key={i} title={`维度 ${i+1}: ${v}`} style={{height:`${Math.max(4,Math.min(50,Math.abs(v)*400))}px`,background:v<0?'#e7ae72':'#69d9d0'}} />)}</div><small>仅展示前 16 维数值，不是概率或语义坐标。</small><button onClick={()=>onSelect(r)}>展开向量、签名与校验摘要</button></div>)}
      {active&&!clips.length&&<p className="eg-ops-note">当前筛选没有此录像的切片；检查索引状态或采集上限。</p>}</section></div>
    <p className="eg-ops-note">每表最多采集最近 {coverage?.limitPerTable||120} 条。{total?.truncated?'库内切片超过采集上限，当前列表不完整。':''} 未获取运行进程的当前签名时，不判断向量是否兼容。原始视频、文件路径和访问凭证不在公开快照中。</p>
  </div>;
}
