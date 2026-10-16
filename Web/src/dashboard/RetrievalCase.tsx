import {useState} from 'react';
import {MediaPreview} from './MediaPreview';
import {time,sec,type MediaRow} from './MediaPanels';
import './briefing.css';

const elapsed=(n:any)=>typeof n==='number'&&Number.isFinite(n)?n<1000?`${n.toFixed(1)} ms`:`${(n/1000).toFixed(1)} s`:'未采集';
const verdicts:Record<string,string>={matched:'模型复核：匹配',not_matched:'模型复核：不匹配',uncertain:'仍无法确认',candidate:'召回候选 · 尚未复核',verification_failed:'视频复核未完成'};
export function RetrievalCase({rows,onSelect}:{rows:MediaRow[];onSelect:(r:any)=>void}){
  const cases=rows.filter(r=>r.name==='media_retrieval_case').sort((a,b)=>a.at-b.at);
  const [selected,setSelected]=useState(''),[candidate,setCandidate]=useState('');
  const item=cases.find(r=>r.id===selected)||cases[0];
  if(!item)return <section className="eg-ops-panel"><h2>检索如何找回录像</h2><p>当前没有明确公开的真实检索案例。下方仍可核对原片、索引和私有查询的运行诊断。</p></section>;
  const d=item.data,result=d.videos?.find((v:any)=>v.id===candidate)||d.videos?.[0],t=d.timings||{};
  return <section className="eg-ops-panel eg-retrieval-case" aria-label="真实检索案例">
    <div className="eg-media-cardhead"><div><span className="eg-media-eyebrow">一次真实查询，如何变成可播放的证据</span><h2>用一句话，找回那几秒</h2></div><span className="eg-ops-badge">真实后端 · 已保存结果</span></div>
    <div className="eg-media-tabs">{cases.map((c,i)=><button key={c.id} aria-pressed={c.id===item.id} onClick={()=>{setSelected(c.id);setCandidate('');}}>{c.data.queryType==='image_text'?'图片 + 文字':'文字检索'} · 案例 {i+1}</button>)}</div>
    <p className="eg-case-query">“{d.text}”</p>
    <div className="eg-pipeline"><div><small>01 · 查询向量化</small><strong>{d.queryType==='image_text'?'图文共同输入':'输入查询文字'}</strong><p>豆包图文向量 · {elapsed(t.embeddingMs)}</p></div><div><small>02 · 双路召回</small><strong>{d.candidateCount} 个候选窗口</strong><p>视频 + 图像排名融合 · {elapsed(t.recallMs)}</p></div><div><small>03 · 视频复核</small><strong>{d.verifiedCount} 个窗口已尝试</strong><p>豆包核对原片，逐段返回结论</p></div><div><small>04 · 回到证据</small><strong>{result?sec(result.seekSeconds):'尚无可播放结果'}</strong><p>总耗时 {elapsed(t.totalMs)} · 播放核对</p></div></div>
    <div className="eg-case-layout"><div><div className="eg-case-results">{d.videos?.map((v:any,i:number)=><button key={v.id} aria-pressed={v.id===result?.id} onClick={()=>setCandidate(v.id)}><small>候选 {i+1} · {sec(v.segmentStart)} — {sec(v.segmentEnd)}</small><b>{verdicts[v.verdict]||v.verdict}</b><span>{v.summary}</span><small>点击定位原片 {sec(v.seekSeconds)} →</small></button>)}</div>{!d.videos?.length&&<p>{d.reason||'本次没有可用结果。'}</p>}
      <details className="eg-brief-details"><summary>检索依据、相似度与原始回执</summary><p>Embedding：{d.embeddingModel||"未采集"}；视频复核：{d.verificationModel||"未采集"}。候选定位为模型估计时间。</p>{d.referenceMedia?.length>0&&<MediaPreview items={d.referenceMedia} title="本次图文查询的实际参考帧"/>}{d.videos?.map((v:any)=><p key={v.id}>{sec(v.segmentStart)}—{sec(v.segmentEnd)}：视频余弦 {v.ranking?.video?.cosine?.toFixed(4)??'未召回'} / 图像余弦 {v.ranking?.frame?.cosine?.toFixed(4)??'未召回'}。{v.limitation}</p>)}<p>相似度用于排名，不是事件概率；检索只覆盖本服务已索引的录像。</p><button onClick={()=>onSelect(item)}>查看本次完整检索结果</button></details></div>
      <div>{result&&<><p className="eg-video-position" role="status">结果定位：{sec(result.seekSeconds)} · 点击播放核对</p><MediaPreview key={item.id+':'+result.id} items={d.source?.media} title="检索命中的原始录像" seek={result.seekSeconds}/><div className="eg-case-verdict"><h3>{verdicts[result.verdict]||'等待结果'}</h3><p>{result.summary}</p><small>{result.limitation||'结论只对应这个候选窗口，不代表整个时段。'}</small></div></>}{d.queryType==='image_text'&&<MediaPreview items={d.referenceMedia} title="本次查询参考图 · 来自已公开原片"/>}</div></div>
    <p className="eg-case-footer">{time(d.createdAt)} · {d.source?.title} · {d.signatureCompatible?'索引版本仍匹配':'索引已变化，展示的是历史查询结果'}。这是明确公开的比赛验证；其他私有查询正文保持私有。</p>
  </section>;
}
