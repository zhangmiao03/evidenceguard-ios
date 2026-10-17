import {useState} from 'react';
import {MediaPreview} from './MediaPreview';
import {deviceLabel,eventLabel,statusLabel} from './labels';
import './media.css';
import './mediaReading.css';
export type MediaRow={id:string;kind:string;name:string;at:number;status:string;data:Record<string,any>;durationMs?:number|null;traceId?:string};
export const time=(n:any)=>typeof n==='number'&&n>0?new Date(n*1000).toLocaleString('zh-CN',{hour12:false}):'未采集';
export const sec=(n:any)=>typeof n==='number'?`${n.toFixed(1)} s`:'—';
const origin=(s:any)=>s==='official_sdk'?'官方 SDK 导入':s==='synthetic_review'?'合成测试素材 · 真实入库':s==='uploaded'?'用户上传':s==='fixture'?'测试场景素材':'数据库记录';
const unitLabel=(r:MediaRow,i:number)=>r.data.indexVersion===2?(r.data.kind==='frame'?`关键帧向量 · ${sec(r.data.frameOffsetSeconds)}`:'视频片段向量'):`片段 ${i+1}`;
const compatible=(v:any)=>v===true?'当前模型可检索':v===false?'需重新建立索引':'模型兼容性未采集';
function output(row:MediaRow){if(row.data.privateContent)return '私有画面分析：此处仅展示模型、状态与耗时，结果正文请在 App 中查看。';let v=row.data.content?.response?.choices?.[0]?.message?.content||row.data.content?.response?.content;try{v=JSON.parse(v);}catch{}return typeof v==='string'?v:v?.visible||v?.summary||row.data.content?.error||'展开查看模型返回正文';}
type Props={rows:MediaRow[];coverage?:Record<string,any>;onSelect:(r:any)=>void};
export function ImageAnalysis({rows,coverage,onSelect}:Props){
  const [group,setGroup]=useState('episodes');
  const names:Record<string,string>={episodes:'media_sdk_episodes',events:'media_sdk_events',evidence:'media_evidence',cache:'media_visual_cache'};
  const items=rows.filter(r=>r.name===names[group]);
  const calls=rows.filter(r=>r.kind==='model'&&(['image_review','frame_presence','video_verify','vision.endpoints'].includes(r.name)||rows.find(p=>p.id===r.data.promptId)?.data.inputMedia?.some((m:any)=>m.kind==='image'||m.kind==='video')));
  return <div className="eg-media">
    <section className="eg-ops-panel eg-media-intro"><span className="eg-media-eyebrow">VISUAL OBSERVATIONS</span><h2>画面、理解，以及判断的依据</h2><p>事件原图与识别结论放在一起看。豆包调用记录单独展示当次上传的图片、提示词与返回结果。</p><small>真实业务库 / 模型追踪库 · 更新于 {time(coverage?.sampledAt)}</small></section>
    <section className="eg-ops-panel"><div className="eg-media-cardhead"><div><h2>豆包视觉调用</h2><p className="eg-ops-note">输入副本按原始字节校验。Codex 记录的是传入执行器的图片，底层 HTTP 报文不可见；历史缺失不会拿相邻图片代替。</p></div><span className="eg-ops-badge">{calls.length} 次</span></div>
      <div className="eg-vision-calls">{calls.slice(-20).reverse().map(r=>{const prompt=rows.find(p=>p.id===r.data.promptId);return <article key={r.id}><header><strong>{eventLabel(r.name)}</strong><span>{statusLabel(r.status)}</span></header><small>{time(r.at)} · {r.data.model||'模型未记录'}{r.durationMs!=null?` · ${sec(r.durationMs/1000)}`:''}</small><MediaPreview items={prompt?.data.inputMedia} title="豆包识图实际输入"/><p>{output(r)}</p><button onClick={()=>onSelect(r)}>查看上传图片、提示词与完整输出 →</button></article>;})}</div>{!calls.length&&<p className="eg-ops-note">当前筛选内没有已采集的视觉模型调用。</p>}
    </section>
    <div className="eg-media-tabs" aria-label="视觉数据类别">{[['episodes','设备事件核验'],['events','原始事件图片'],['evidence','图片证据结果'],['cache','视觉结果缓存']].map(([id,label])=><button key={id} aria-pressed={id===group} onClick={()=>setGroup(id)}>{label} · {rows.filter(r=>r.name===names[id]).length}</button>)}</div>
    <div className="eg-media-cards">{items.slice(0,120).map((r,index)=>{const d=r.data,wrapper=d.review||d.visualReview||{},review=wrapper.review||wrapper;return <article className="eg-ops-panel" key={r.id}><div className="eg-media-cardhead"><div><small>观察记录 {index+1}</small><h3>{d.cameraId?deviceLabel(d.cameraId,rows):'视觉核验结果'}</h3><small>{origin(d.sourceType||(group==='episodes'?'official_sdk':null))}</small></div><span className="eg-ops-badge">{statusLabel(d.reviewStatus||d.status||r.status)}</span></div><MediaPreview items={d.media} title={`${deviceLabel(d.cameraId,rows)} · 来源画面`}/><dl className="eg-media-observation"><dt>可见事实 / 已保存结论</dt><dd>{review.visible||review.summary||d.reason||wrapper.reason||'原始事件图片，尚无关联的核验正文'}</dd><dt>未知与限制</dt><dd>{review.uncertainties||wrapper.limitation||d.limitation||'仅对应此条证据，不代表此刻现场状态。'}</dd></dl><small>{d.updatedAt?'业务更新时间':'观察 / 取样时间'}：{time(d.updatedAt||d.capturedAt||d.observedAt||d.sampledAt||d.receivedAt)}</small><button onClick={()=>onSelect(r)}>查看完整结果与来源</button></article>;})}</div>
    {!items.length&&<section className="eg-ops-panel eg-media-empty"><h3>当前范围没有这类记录</h3><p>检查环境、时间范围与筛选；这里只展示实际已采集的数据。</p></section>}
  </div>;
}
export {VideoIndex} from './VideoLibrary';
