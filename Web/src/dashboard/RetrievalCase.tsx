import {useState} from 'react';
import {MediaPreview,publicMediaUrl} from './MediaPreview';
import {time,sec,type MediaRow} from './MediaPanels';
import {candidateFrames,nearestFrame,playbackPosition} from './retrievalPresentation.mjs';
import './briefing.css';
import './retrieval.css';

const elapsed=(n:any)=>typeof n==='number'&&Number.isFinite(n)?n<1000?`${n.toFixed(1)} ms`:`${(n/1000).toFixed(1)} s`:'未采集';
const verdicts:Record<string,string>={matched:'模型复核：匹配',not_matched:'模型复核：不匹配',uncertain:'仍无法确认',candidate:'召回候选 · 尚未复核',verification_failed:'视频复核未完成'};
function thumbnail(frame:any){return frame?.data.media?.find((m:any)=>m.kind==='image'&&publicMediaUrl(m.previewUrl))?.previewUrl;}
export function RetrievalCase({rows,onSelect}:{rows:MediaRow[];onSelect:(r:any)=>void}){
  const cases=rows.filter(r=>r.name==='media_retrieval_case').sort((a,b)=>a.at-b.at);
  const [selected,setSelected]=useState(''),[candidate,setCandidate]=useState(''),[position,setPosition]=useState<number|null>(null);
  const item=cases.find(r=>r.id===selected)||cases[0];
  if(!item)return <section className="eg-ops-panel"><h2>检索如何找回录像</h2><p>当前没有明确公开的真实检索案例。下方仍可核对原片、索引和私有查询的运行诊断。</p></section>;
  const d=item.data,videos=d.videos||[],result=videos.find((v:any)=>v.id===candidate)||videos[0],t=d.timings||{};
  const frames=candidateFrames(rows,d,result),seek=playbackPosition(position??result?.seekSeconds,d.source?.duration),poster=thumbnail(nearestFrame(frames,seek));
  const matched=videos.filter((v:any)=>v.verdict==='matched').length;
  function choose(v:any){setCandidate(v.id);setPosition(null);}
  return <section className="eg-ops-panel eg-retrieval-case" aria-label="真实检索案例">
    <div className="eg-media-cardhead"><div><span className="eg-media-eyebrow">VIDEO MEMORY / 找到画面，再核对原片</span><h2>记得一句话，就能找回那几秒。</h2></div><span className="eg-ops-badge">真实后端 · 已保存结果</span></div>
    <div className="eg-media-tabs">{cases.map((c,i)=><button key={c.id} aria-pressed={c.id===item.id} onClick={()=>{setSelected(c.id);setCandidate('');setPosition(null);}}>{c.data.queryType==='image_text'?'图片 + 文字':'文字检索'} · 案例 {i+1}</button>)}</div>
    <div className="eg-recall-query"><div><small>检索输入</small><p className="eg-case-query">“{d.text}”</p><p>{d.queryType==='image_text'?'参考图帮助描述可见外观；相似外观不等于同一物品。':'用语义检索动作，不必记住录像文件名和发生时间。'}</p></div>{d.queryType==='image_text'&&<div className="eg-query-image"><MediaPreview items={d.referenceMedia} title="本次查询实际输入的参考图"/></div>}<div className="eg-recall-outcome"><b>{matched}</b><span>个返回窗口复核匹配<small>{d.candidateCount??'未知'} 个召回候选 · {d.verifiedCount??'未知'} 个尝试复核<br/>全程 {elapsed(t.totalMs)}</small></span></div></div>
    <div className="eg-pipeline"><div><small>01 · 输入变成向量</small><strong>{d.queryType==='image_text'?'图片 + 文字':'一句自然语言'}</strong><p>{elapsed(t.embeddingMs)}</p></div><div><small>02 · 双路召回</small><strong>{d.candidateCount??'未知'} 个候选窗口</strong><p>视频理解动作，关键帧寻找外观</p></div><div><small>03 · 排名融合与复核</small><strong>按原片核对内容</strong><p>排名融合选候选，模型再看视频</p></div><div><small>04 · 定位原片</small><strong>{result?sec(result.seekSeconds):'暂无结果'}</strong><p>点击下方结果直接核对</p></div></div>
    <div className="eg-recall-cards" aria-label="检索候选画面">{videos.map((v:any,i:number)=>{
      const frame=nearestFrame(candidateFrames(rows,d,v),v.seekSeconds),src=thumbnail(frame);
      return <button key={v.id} aria-pressed={v.id===result?.id} onClick={()=>choose(v)} className="eg-recall-card">
        <div className="eg-recall-thumb">{src?<img src={src} alt={`候选 ${i+1} 的索引帧 ${sec(frame.data.frameOffsetSeconds)}`}/>:<span>此窗口无可用索引帧</span>}<b>结果 {i+1}</b><small>{src?`索引帧 ${sec(frame.data.frameOffsetSeconds)}`:'可在下方播放原片'}</small></div>
        <div className="eg-recall-cardbody"><small>{sec(v.segmentStart)} — {sec(v.segmentEnd)}</small><strong className={'verdict-'+v.verdict}>{verdicts[v.verdict]||'复核状态未采集'}</strong><p>{v.summary}</p><span className="eg-recall-rank">视频排名 {v.ranking?.video?.rank??'—'} · 图像排名 {v.ranking?.frame?.rank??'—'} → 融合排名 {v.rank??'—'}</span><b>查看原片 {sec(v.seekSeconds)} ↗</b></div>
      </button>;
    })}</div>
    {!videos.length&&<p>{d.reason||'本次没有可用结果。'}</p>}
    {result&&<div className="eg-recall-proof"><div><p className="eg-video-position" role="status">结果定位：{sec(seek)} · 点击播放核对</p><p className="eg-case-footer">下方模型描述按候选片段计时；播放器定位按完整原片计时。</p>
      <MediaPreview key={item.id+':'+result.id+':'+seek} items={d.source?.media} title="检索命中的原始录像" seek={seek} poster={poster}/>
      {poster&&<small className="eg-recall-note">封面是本窗口的邻近索引帧，事件时刻以原片播放为准。</small>}
      <div className="eg-recall-strip" aria-label="该窗口的真实索引帧">{frames.map((f:any)=>{const src=thumbnail(f);return src?<button key={f.id} onClick={()=>setPosition(f.data.frameOffsetSeconds)} aria-label={`定位索引帧 ${sec(f.data.frameOffsetSeconds)}`}><img src={src} alt="已入库的索引关键帧"/><span>{sec(f.data.frameOffsetSeconds)}</span></button>:null;})}</div>
      <small className="eg-recall-note">画面来自同一录像、同一窗口及同一模型索引。没有精确关联时留空。</small>
    </div><div className="eg-case-verdict"><small>视频复核的实际输出</small><h3>{verdicts[result.verdict]||'等待结果'}</h3><p>{result.summary}</p><div className="eg-recall-events">{result.events?.map((event:any,i:number)=><button key={i} onClick={()=>setPosition(playbackPosition(event.start,d.source?.duration))}><b>▶ {sec(event.start)}</b><span>{event.description}</span></button>)}</div><small>{result.limitation||'结论只对应这个候选窗口，不代表整个时段。'}</small></div></div>}
    <details className="eg-brief-details"><summary>向量、排序与检索依据</summary><p>Embedding：{d.embeddingModel||'未采集'}；视频复核：{d.verificationModel||'未采集'}。</p><p>视频向量与关键帧向量分别计算余弦排名，再以 RRF 合并（每路 1 / (60 + 排名)）。复核匹配的结果优先显示，未复核候选不会标为命中。</p>{videos.map((v:any)=><p key={v.id}>{sec(v.segmentStart)}—{sec(v.segmentEnd)}：视频余弦 {v.ranking?.video?.cosine?.toFixed(4)??'未召回'} / 图像余弦 {v.ranking?.frame?.cosine?.toFixed(4)??'未召回'}。</p>)}<p>相似度用于排名，不是事件发生概率。时间为模型估计；当前查询只覆盖已索引录像，未找到不等于未发生。</p><button onClick={()=>onSelect(item)}>查看本次完整检索回执</button></details>
    <p className="eg-case-footer">{time(d.createdAt)} · {d.source?.title} · {d.signatureCompatible?'索引版本仍匹配':'索引已变化，展示的是历史查询结果'}。明确公开的比赛验证，其他私有查询正文不公开。</p>
  </section>;
}
