import {useState} from 'react';
import {MediaPreview} from './MediaPreview';
import {SearchHistory} from './SearchHistory';
import {deviceLabel,statusLabel} from './labels';
import {clipGroups} from './mediaReading.mjs';
import {time,sec,type MediaRow} from './MediaPanels';

export function VideoIndex({rows,coverage,onSelect}:{rows:MediaRow[];coverage?:Record<string,any>;onSelect:(r:any)=>void}){
  const recordings=rows.filter(r=>r.name==='media_recordings');
  const [chosen,setChosen]=useState(''),[clip,setClip]=useState(''),[seek,setSeek]=useState(0);
  const active=recordings.find(r=>r.data.id===chosen)||recordings.find(r=>!['synthetic_review','fixture','synthetic_demo'].includes(r.data.sourceType))||recordings[0];
  const groups=clipGroups(rows,active?.data.id),current=groups.find((g:any)=>g.id===clip)||groups[0];
  const vectors=groups.flatMap((g:any)=>g.rows),frames=vectors.filter((r:any)=>r.data.kind==='frame');
  const source=(s:string)=>({official_sdk:'官方 SDK 事件导入',uploaded:'客户端上传 · 来源见录像说明',synthetic_review:'合成测试素材 · 真实入库',fixture:'测试场景素材',synthetic_demo:'合成测试素材'}[s]||'来源未记录');
  function choose(id:string){setChosen(id);setClip('');setSeek(0);}
  return <div className="eg-media eg-video-library">
    <section className="eg-media-indexgrid">
      <aside className="eg-ops-panel"><span className="eg-media-eyebrow">RECORDED VIDEO</span><h2>先看原片，再看记忆</h2><p>切换录像，点击时间窗口和关键帧，即可定位对应原片。这里读取真实入库记录。</p>
        <div className="eg-media-calllist">{recordings.map((r,i)=><button key={r.id} aria-pressed={active?.id===r.id} onClick={()=>choose(r.data.id)}><span>{r.data.title||`录像 ${i+1}`}<small>{source(r.data.sourceType)} · {sec(r.data.duration)}</small></span><b>{statusLabel(r.data.status)}</b></button>)}</div>
        {!recordings.length&&<p>当前筛选没有录像记录。</p>}
        <p className="eg-ops-note">快照 {time(coverage?.sampledAt)} · 每表最多 {coverage?.limitPerTable||120} 条。计数仅对应当前筛选；旧索引与合成素材单独标明。</p>
      </aside>
      <section className="eg-ops-panel eg-video-stage"><div className="eg-media-cardhead"><div><small>当前录像 / {active?deviceLabel(active.data.cameraId,rows):'等待记录'}</small><h2>{active?.data.title||'未选择录像'}</h2></div>{active&&<span className="eg-ops-badge">{statusLabel(active.data.status)}</span>}</div>
        {active&&<><p className="eg-video-position" role="status">原片定位：{sec(seek)} · 点击播放器播放核对</p><MediaPreview key={active.id+':'+seek} items={active.data.media} title={active.data.title||'入库录像'} seek={seek}/>
          <div className="eg-video-counts"><span><b>{sec(active.data.duration)}</b>录像时长</span><span><b>{groups.length}</b>时间窗口</span><span><b>{vectors.length-frames.length}</b>视频向量</span><span><b>{frames.length}</b>图像向量</span></div>
          <p>{active.data.signatureCompatible===true?'当前模型签名匹配，可参与检索':active.data.signatureCompatible===false?'旧索引与当前模型不匹配，需要重建':'模型兼容性未采集'} · {active.data.embeddingModel||'模型未记录'}</p>
          <small>拍摄开始时间：{time(active.data.recordedAt)}；下方秒数为原片内相对位置，不是墙上时钟。</small>
          <button onClick={()=>onSelect(active)}>查看来源与录像详情</button></>}
      </section>
    </section>
    <section className="eg-ops-panel"><div className="eg-media-cardhead"><div><span className="eg-media-eyebrow">VISUAL MEMORY / INDEXED FRAMES</span><h2>一段录像，如何被记住</h2><p>视频向量保留片段信息，关键帧向量用于找可见目标；两路召回后再用视频复核。相似度不是发生概率。</p></div></div>
      <div className="eg-clip-tabs" aria-label="录像切片时间轴">{groups.map((g:any,i:number)=><button key={g.id} aria-pressed={g.id===current?.id} onClick={()=>{setClip(g.id);setSeek(g.start);}}><small>窗口 {i+1}</small><b>{sec(g.start)} — {sec(g.end)}</b><span>{g.videos.length} 个视频向量 · {g.frames.length} 个图像向量</span></button>)}</div>
      {current&&<><div className="eg-frame-grid">{current.frames.map((r:MediaRow,i:number)=><article key={r.id}><MediaPreview items={r.data.media} title={`已索引关键帧 · ${sec(r.data.frameOffsetSeconds)}`}/><button onClick={()=>setSeek(r.data.frameOffsetSeconds)}>定位原片 {sec(r.data.frameOffsetSeconds)} →</button><small>关键帧 {i+1} · {r.data.dimensions} 维 · {statusLabel(r.data.status)}</small>{!r.data.media?.length&&<p>该帧已索引，当前采集器没有帧预览；可定位原片核对。</p>}</article>)}</div>
      {!current.frames.length&&<p>这个窗口没有已采集的图像向量。</p>}
      <details className="eg-vector-details"><summary>本窗口向量详情 · {current.rows.length} 条</summary>{current.rows.map((r:MediaRow)=><div className="eg-media-vector" key={r.id}><strong>{r.data.kind==='frame'?`关键帧向量 · ${sec(r.data.frameOffsetSeconds)}`:'视频片段向量'}</strong><span>{r.data.dimensions} 维</span><p>{r.data.indexVersion===2?'v2 视频 / 关键帧双路索引':'v1 视频索引'} · {r.data.signatureCompatible===true?'当前模型可检索':r.data.signatureCompatible===false?'需重建索引':'兼容性未采集'}</p><button onClick={()=>onSelect(r)}>展开向量、签名与校验摘要</button></div>)}</details></>}
      {!groups.length&&<p>当前录像尚无已采集的索引，不能用上传成功代替检索就绪。</p>}
    </section>
    <SearchHistory rows={rows} recordings={recordings} onSelect={onSelect}/>
  </div>;
}
