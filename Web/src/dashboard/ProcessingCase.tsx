import {MediaPreview} from './MediaPreview';
import {time,sec,type MediaRow} from './MediaPanels';
import './briefing.css';

const skips:Record<string,string>={FRAMES_NOT_ADJACENT:'两帧间隔超过 1 秒',VIEW_OR_SESSION_CHANGED:'摄像头、会话或视角改变',SAME_FRAME:'同一帧不能用于光流',LIVE_SAMPLE_REQUIRED:'没有符合要求的实时取样',TIME_UNKNOWN:'取样时间不可确认',DIMENSIONS_CHANGED:'图像尺寸改变',REPEATED_PIXELS_NOT_PROOF_OF_STILLNESS:'重复像素不能证明静止',FLOW_DISABLED:'光流未开启'};
export function ProcessingCase({rows,onSelect}:{rows:MediaRow[];onSelect:(r:any)=>void}){
  const item=rows.find(r=>r.name==='media_processing_case'),status=rows.find(r=>r.name==='vision_processing_status');
  if(!item)return <section className="eg-ops-panel"><h2>深度与光流处理</h2><p>当前环境没有可公开的处理样本。真实处理记录到达后展示，不用示意图填充。</p></section>;
  const d=item.data,c=status?.data||{},config=c.configuration||{},media=d.media||[],flow=d.flow||{},depth=d.depth||{};
  const first=sec(d.sampleOffsets?.[0]),last=sec(d.sampleOffsets?.[1]);
  const at=(index:number)=>media.filter((m:any)=>m.position===String(index));
  const pct=typeof flow.consistentFraction==='number'?`${(flow.consistentFraction*100).toFixed(1)}%`:'未采集';
  return <section className="eg-ops-panel eg-processing-case" aria-label="深度与光流真实复算">
    <div className="eg-media-cardhead"><div><span className="eg-media-eyebrow">RGB → DEPTH / FLOW → 视觉判断</span><h2>同一幅画面，多看一层依据</h2><p>已部署策略：原图看内容，深度辅助空间关系，光流检查相邻画面的变化。</p></div><span className="eg-ops-badge">真实录像复算</span></div>
    <div className="eg-processing-status"><span>{c.sameProcess&&config.depthReady?'● DepthART448 已就绪':'Depth 状态待重新核验'}</span><span>{c.sameProcess&&config.flowReady?'● DIS 光流已就绪':'光流状态待重新核验'}</span><span>{c.sameProcess?'本次运行进程已核验':'服务进程已变化，需重新核验配置'}</span><span>首尾分析入库 {c.endpoint_analysesCount??'未知'} 次</span></div>
    <p className="eg-case-footer">来源：{d.source?.title} · {d.sampleOffsets?.join(' / ')} 秒 · 间隔 {d.intervalMs} ms · {time(d.createdAt)} · CPU {d.latencyMs} ms</p>
    <div className="eg-processing-media"><article><h3>① 原始画面</h3><MediaPreview items={at(0)} title={`原片 ${first} · 处理输入`}/><p>从已保存原片取出的真实帧。可在下方核对第二帧。</p></article><article><h3>② 相对深度</h3><MediaPreview items={depth.status==='completed'?at(2):[]} title="DepthART448 · 同帧相对逆深度"/><p>{depth.status==='completed'?'近亮远暗；每张图独立归一化。只能辅助关系判断，不能读取米数。':'本次深度没有完成。'}</p></article><article><h3>③ 相邻帧光流</h3><MediaPreview items={at(4)} title="DIS FAST · 相邻帧光流诊断"/><p>{flow.status==='completed'?`前后向一致性 ${pct}，几何内点 ${flow.geometricInliers}。${flow.quality==='diagnostic_checks_passed_not_ground_truth'?'通过诊断检查。':'质量不足，不展示运动结论。'}`:skips[flow.code]||'没有生成有效光流。'}</p></article></div>
    <p className="eg-case-footer">本例为保存录像的预处理复算，未触发实时守护或云台控制；这三张图不表示历史识图都使用了深度/光流。</p>
    <details className="eg-brief-details"><summary>处理策略、跳过条件与运行覆盖</summary><div className="eg-pipeline"><div><small>01 · 输入</small><strong>全图 + 同框局部图</strong><p>守护与首尾分析按各自上下文选择有效帧。</p></div><div><small>02 · Depth</small><strong>DepthART448</strong><p>448 × 448 CPU 推理，权重摘要校验；不能跨帧比较亮度。</p></div><div><small>03 · Flow</small><strong>先检查帧的条件</strong><p>同设备、通道、会话与视角；不同帧、间隔 ≤ 1 秒。重复像素、断流与跨视角需跳过。</p></div><div><small>04 · 判断</small><strong>交给 VLM 辅助核验</strong><p>几何检查不足或画面不清保留未知。光流不直接驱动电机。</p></div></div>
      <p>配置核验时间：{time(c.verifiedAt)}。守护辅助处理的逐次诊断尚未由当前运行版本持久化；这里不把“开启”计为“成功运行”。</p>
      <div className="eg-processing-media"><article><h3>第二帧 · {last}</h3><MediaPreview items={at(1)} title={`原片 ${last} · 第二帧`}/></article><article><h3>第二帧相对深度</h3><MediaPreview items={at(3)} title="DepthART448 · 第二帧"/></article></div>
      {c.endpointDiagnostics?.map((r:any,i:number)=><p key={i}>{time(r.createdAt)} · {r.status} · 深度 {r.depth?.status||'未记录'} · 光流 {skips[r.flow?.code]||r.flow?.status||'未记录'}</p>)}
      <button onClick={()=>onSelect(item)}>处理参数与可核对来源</button>
    </details>
  </section>;
}
