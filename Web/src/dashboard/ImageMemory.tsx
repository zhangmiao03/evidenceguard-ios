import {useState} from 'react';
import {MediaPreview} from './MediaPreview';
import {deviceLabel,statusLabel} from './labels';
import {time,type MediaRow} from './MediaPanels';
import {short} from './judge.mjs';
import {ProcessingCase} from './ProcessingCase';
import {guardModelCall} from './guard-link.mjs';

export function MediaEntry({rows,onPage}:{rows:MediaRow[];onPage:(page:number)=>void}){
  const recordings=rows.filter(r=>r.name==='media_recordings'),frames=rows.filter(r=>r.name==='media_video_segments'&&r.data.kind==='frame');
  const pictures=rows.filter(r=>r.name==='media_evidence');
  return <section className="eg-media-entry" aria-label="真实图像与录像入口"><button onClick={()=>onPage(13)}><small>已保存画面</small><strong>{pictures.length} 条图片证据</strong><span>来源图片 → 可见事实 → 当次模型输入 ↗</span></button><button onClick={()=>onPage(14)}><small>可回看的时间记忆</small><strong>{recordings.length} 条录像 · {frames.length} 个关键帧索引</strong><span>原片 → 分段与图像向量 → 检索诊断 ↗</span></button><p>当前快照与筛选范围；图片证据数量不等于全库图片总数，索引数量不等于已核验事件。</p></section>;
}

export function ImageMemory({rows,onSelect,onPage}:{rows:MediaRow[];onSelect:(r:any)=>void;onPage:(page:number)=>void}){
  const [limit,setLimit]=useState(6);
  const evidence=rows.filter(r=>r.name==='media_evidence').sort((a,b)=>(b.data.receivedAt||b.data.capturedAt||0)-(a.data.receivedAt||a.data.capturedAt||0));
  return <div className="eg-media"><ProcessingCase rows={rows} onSelect={onSelect}/>
    <section className="eg-ops-panel"><span className="eg-media-eyebrow">STORED OBSERVATIONS</span><h2>真实画面与已保存的理解</h2><p>下方是业务保存的观察结论。调用明细是否留存单独标明；不涉及真人身份关联。</p><small>全部存图可在“完整图片台账”查询；视频的图像向量在 <button onClick={()=>onPage(14)}>视频向量库 →</button> 查看。</small></section>
    <div className="eg-image-memory-grid">{evidence.slice(0,limit).map(r=>{const d=r.data,wrapper=d.visualReview||{},review=wrapper.review||wrapper;const assets=(d.media||[]).filter(Boolean).map((m:any)=>m.assetId).filter(Boolean);const prompt=rows.find(p=>p.kind==='prompt'&&!p.data.privateContent&&p.data.inputMedia?.some((m:any)=>assets.includes(m.assetId)));const guardCall=guardModelCall(d,rows);const call=guardCall||(prompt&&rows.find(p=>p.kind==='model'&&p.data.promptId===prompt.id));return <article key={r.id} className="eg-ops-panel"><header><strong>{deviceLabel(d.cameraId,rows)}</strong><small>{statusLabel(d.reviewStatus||r.status)}</small></header><MediaPreview items={d.media} title={`${deviceLabel(d.cameraId,rows)} · 已保存图像记忆`}/><p className="eg-reading-fact">{review.visible||review.summary||d.reason?"观察结论已保存":"原始图片 · 等待分析"}</p><p className="eg-memory-fact">{short(review.visible||review.summary||d.reason||'这张图片尚无保存的视觉结论。',180)}</p><p className="eg-ops-note">限制：{short(review.uncertainties||d.limitation||'只对应本次画面；不能代表采样间隔或此刻现场。',140)}</p><small>来源：{d.sourceType==='official_sdk'?'官方设备事件':d.sourceType==='official_live_ios'?'iOS 实时取样':d.sourceType?.startsWith('synthetic')?'合成测试图':'业务保存图片'} · {time(d.sampledAt||d.capturedAt||d.receivedAt)}</small><div className="eg-memory-actions"><button onClick={()=>onSelect(r)}>来源与完整结论</button>{call&&<button onClick={()=>onSelect(call)}>{guardCall?'本次守护模型输入与输出 ↗':'同图模型输入与输出 ↗'}</button>}</div>{!call&&<small>{d.reason||review.visible||review.summary?"历史结论可查看；同图调用明细未留存关联，不能还原当次输入/输出。":"当前只有原图，尚无保存的分析结论。"}</small>}</article>;})}</div>
    {!evidence.length&&<p className="eg-ops-panel">当前范围没有图片证据。可查看完整台账或清除筛选；不会使用示例图片填充。</p>}
    {evidence.length>limit&&<button onClick={()=>setLimit(n=>n+12)}>显示更多图像记忆 · 还有 {evidence.length-limit} 条</button>}
  </div>;
}
