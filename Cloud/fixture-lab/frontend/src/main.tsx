import React, { useEffect, useRef, useState } from 'react';
import {createRoot} from 'react-dom/client';
import { ShieldCheck, LayoutDashboard, Images, Camera, ArrowUpRight, Check, Box, ScanLine,
  CircleHelp, AlertTriangle, RefreshCw, Pause, Play, Clock3, ChevronRight, FlaskConical,
  Wifi, WifiOff, X, SlidersHorizontal, ExternalLink, CheckCheck, Activity } from 'lucide-react';
import './style.css';

type Observation = {frame_id:string;device_id:string;captured_at:number;received_at:number;
  revision:number;relation:string;reason:string;bbox:number[]|null;marker_ids:number[];source_type:string};
type CameraState = {id:string;label:string;expected_model:string;transport_online:boolean;fresh:boolean;
  age:number|null;image_url:string|null;error:string;roi:number[];observation:Observation|null};
type Event = {sequence:number;type:string;text:string;at:number;revision:number;evidence:Observation[]};
type Snapshot = {now:number;task:{id:string;title:string;revision:number;lifecycle:string;result:string;
  reason:string;alert:string;episode:number;last_confirmed_at:number|null;evidence:Observation[];
  roi:Record<string,number[]>;freshness_seconds:number;confirmations:number};
  settings:{scenario:string;mode:string};cameras:CameraState[];events:Event[];scenarios:Record<string,string>;
  commands:{id:string;device_id:string;status:string;reason:string;requested_at:number}[];
  worker:{last_tick:number;error:string|null};limitations:string[]};
const labels:Record<string,string> = {initializing:'等待首次观察',confirmed:'已确认',needs_attention:'需要处理',unknown:'无法确认'};
const eventLabels:Record<string,string> = {state_changed:'观察更新',alert_opened:'异常提醒',alert_resolved:'恢复确认',
  snapshot_requested:'请求新图',snapshot_completed:'新图到达',snapshot_timeout:'取图超时',scenario_changed:'模拟切换',
  task_paused:'暂停守护',recheck_requested:'发起复核',skill_revised:'规则更新'};
const statusLabels:Record<string,string> = {accepted:'等待新图',completed:'已取得新图',failed:'设备不可用',unsupported:'设备不支持',timed_out:'等待超时'};
const fmt = (t:number|null|undefined) => t ? new Date(t*1000).toLocaleTimeString('zh-CN',{hour12:false}) : '—';
const imageUrl = (o:Observation) => `/api/frames/${o.frame_id}.jpg`;

function App(){
 const [data,setData]=useState<Snapshot|null>(null), [error,setError]=useState(''), [busy,setBusy]=useState(false);
 const [tab,setTab]=useState('dashboard'), [selected,setSelected]=useState<Observation|null>(null);
 const [editing,setEditing]=useState(false),[draft,setDraft]=useState<Record<string,number[]>>({});
 const [notice,setNotice]=useState(''), [eventFilter,setEventFilter]=useState('business');
 const [offline,setOffline]=useState(false);
 const polling=useRef(false), mutation=useRef(false), generation=useRef(0);
 async function load(){
   if(polling.current || mutation.current)return;
   polling.current=true; const current=generation.current;
   try{const r=await fetch('/api/state');if(!r.ok)throw new Error('服务连接失败');const d=await r.json();
    if(current===generation.current){setData(d);setOffline(false);}}
   catch{setOffline(true);}finally{polling.current=false;}
 }
 useEffect(()=>{void load();const i=setInterval(load,1000);return()=>clearInterval(i);},[]);
 useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),4500);return()=>clearTimeout(t);},[notice]);
 async function post(path:string,body:object){
   if(mutation.current)return false;
   mutation.current=true;generation.current++;setBusy(true);setError('');
   try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'输入不符合要求');
    setData(result);setOffline(false);return true;
   }catch(e){setError((e as Error).message);return false;}finally{mutation.current=false;setBusy(false);}
 }
 const changeScenario=(scenario:string)=>post('/api/simulation',{scenario});
 const action=async(action:string)=>{if(await post('/api/task/action',{action}))setNotice(action==='pause'?'守护已暂停，历史记录仍保留':'已请求新的画面，正在重新确认');};
 const shownEvents=data?.events.filter(e=>eventFilter==='all'||!['snapshot_requested','snapshot_completed','scenario_changed'].includes(e.type))||[];
 const freshCount=data?.cameras.filter(c=>c.fresh).length||0;
 const result = offline?'unknown':data?.task.result||'initializing';
 const paused=data?.task.lifecycle==='paused';
 const StatusIcon=result==='confirmed'?ShieldCheck:result==='needs_attention'?AlertTriangle:CircleHelp;
 if(!data)return <div className="loading"><div className="brandmark"><ShieldCheck size={30}/></div><h2>EvidenceGuard</h2><p>{offline?'后端尚未连接，请先运行启动脚本':'正在连接双摄守护工作台…'}</p><button onClick={load}>重新连接</button></div>;

 return <div className="shell">
   <aside className="sidebar">
    <a className="brand" href="#" onClick={e=>{e.preventDefault();setTab('dashboard');}}><span className="brandmark"><ShieldCheck size={25}/></span><span>EvidenceGuard<small>让确认有据可查</small></span></a>
    <div className="workspace"><span className="workspace-icon"><Box size={18}/></span><div>黑客松实验空间<small>CAMERA LAB · 01</small></div><ChevronRight size={15}/></div>
    <div className="nav-label">工作空间</div>
    <nav>{[["dashboard","守护工作台",LayoutDashboard],["evidence","证据记录",Images],["devices","设备能力",Camera]].map(([id,label,Icon])=>{const I=Icon as typeof Camera;return <button key={id as string} className={tab===id?'active':''} onClick={()=>setTab(id as string)}><I size={19}/>{label as string}{id==='dashboard'&&<span className="nav-count">1</span>}</button>})}</nav>
    <div className="sidebar-bottom"><div className="lab-note"><FlaskConical size={19}/><b>正在使用模拟设备</b><p>真实 RTSP 链路，合成场景输入。正式摄像机待接入。</p><span>PROTOTYPE 0.1</span></div><div className="owner"><span>EG</span><div>安克黑客松项目<small>本地开发环境</small></div><span className="online-dot"/></div></div>
   </aside>
   <main>
    <header><div className="breadcrumb">实验空间 <ChevronRight size={13}/><span>{tab==='dashboard'?'守护工作台':tab==='evidence'?'证据记录':'设备能力'}</span></div><div className={'server-pill '+(offline?'disconnected':'')}><i/>{offline?'后端连接中断':'守护服务运行中'}</div></header>
    <div className="content">
      <div className="page-heading"><div><div className="eyebrow">EVIDENCE BEFORE CONFIDENCE</div><h1>{tab==='dashboard'?'双摄守护工作台':tab==='evidence'?'每次判断，都有来处':'从能力开始接入'}</h1><p>{tab==='dashboard'?'一个持续任务，两个观察视角。先看证据，再作判断。':tab==='evidence'?'查看状态变化、取图请求和支撑结论的原始画面。':'模拟能力已连接；真实型号能力等待官方 SDK 核验。'}</p></div><span className="fixture-badge"><FlaskConical size={15}/>合成场景验证</span></div>
      {offline&&<div className="error">后端连接已中断。以下为最后收到的数据，不能作为当前确认。</div>}
      {error&&<div className="error">{error}<button aria-label="关闭提示" onClick={()=>setError('')}><X size={15}/></button></div>}
      {data.worker.error&&<div className="error">观察服务发生错误：{data.worker.error}</div>}
      {tab==='dashboard'&&<>
       <div className="metrics"><Metric label="守护任务" value="01" suffix={paused?'已暂停':'持续观察中'} icon={<ScanLine/>}/><Metric label="新鲜画面" value={`${freshCount} / 2`} suffix={`时效上限 ${data.task.freshness_seconds} 秒`} icon={<Camera/>}/><Metric label="未解决告警" value={['open','acknowledged'].includes(data.task.alert)?'01':'00'} suffix={data.task.alert==='acknowledged'?'已知晓 · 待新证据复核':'依据持续观察更新'} icon={<Activity/>}/></div>
       <div className="workspace-grid"><section className="view-section"><div className="section-title"><h2>观察视角 <span>02</span></h2><button className="text-button" disabled={busy||offline} onClick={()=>{setEditing(!editing);setDraft(structuredClone(data.task.roi));}}><SlidersHorizontal size={14}/>{editing?'取消调整':'调整守护区域'}</button></div>
        <div className="camera-grid">{data.cameras.map(c=><CameraCard key={c.id} camera={c} editing={editing} roi={editing?draft[c.id]||c.roi:c.roi} onRoi={r=>setDraft(old=>({...old,[c.id]:r}))} onOpen={()=>c.observation&&setSelected(c.observation)}/>)}</div>
        {editing&&<div className="edit-bar"><span>在两个画面中分别拖动，圈出对应的同一物理区域。</span><button disabled={busy} className="primary" onClick={async()=>{if(await post('/api/task',{revision:data.task.revision,title:data.task.title,roi:draft})){setEditing(false);setNotice('区域已保存，新版本正在等待首次观察');}}}>确认区域 · 新版本</button></div>}
        <div className="source-note"><span className="tiny-dot"/> 合成素材 · 标记目标检测 <span>画面经 MediaMTX / RTSP 实际传输</span></div>
        <section className="panel simulation"><div className="section-title"><div><h2><FlaskConical size={17}/>场景实验</h2><p>改变输入，观察系统如何形成结论。</p></div><select aria-label="设备取图模式" value={data.settings.mode} disabled={busy||offline} onChange={e=>post('/api/simulation',{mode:e.target.value})}><option value="continuous">连续画面</option><option value="on_demand">按需取图</option><option value="event_only">仅事件片段</option></select></div><div className="scenarios">{Object.entries(data.scenarios).map(([key,label])=><button key={key} className={data.settings.scenario===key?'selected':''} disabled={busy||offline} onClick={()=>changeScenario(key)}>{data.settings.scenario===key?<Check size={14}/>:<span className="scenario-dot"/>}{label}</button>)}</div><div className="simulation-hint">{data.settings.mode==='event_only'?'事件片段结束后将没有新画面，证据过期应显示无法确认。':data.settings.scenario==='old_b'?'第二视角保留原采集时间；收到旧图不等于取得新证据。':'建议依次试试：箱子在区内 → A 遮挡 → 箱子移出 → 两个设备断流。'}</div></section>
       </section>
       <aside className="task-panel panel"><div className="task-kicker"><span>持续守护</span><span>v{data.task.revision}</span></div><div className="task-symbol"><Box size={25}/></div><h2>{data.task.title}</h2><p className="task-description">目标标记 #17 · 两个视角分别绑定区域</p><div className={`decision ${paused?'paused':result}`}><StatusIcon size={23}/><div><strong>{paused?'守护已暂停':labels[result]}</strong><p>{paused?'最后结果保留，恢复后重新获取证据。':offline?'连接中断，等待恢复后复核':data.task.reason}</p></div></div><dl><div><dt>最后一次确认</dt><dd>{fmt(data.task.last_confirmed_at)}</dd></div><div><dt>本次证据来源</dt><dd>{data.task.evidence.length?data.task.evidence.map(o=>o.device_id.toUpperCase()).join('、'):'等待有效证据'}</dd></div><div><dt>告警处置</dt><dd className={['open','acknowledged'].includes(data.task.alert)?'alert-text':''}>{{none:'暂无告警',open:'未处理',acknowledged:'已知晓，待复核',resolved:'已由新证据解决'}[data.task.alert]}</dd></div></dl><div className="task-actions"><button className="primary" disabled={busy||offline} onClick={()=>action('recheck')}><RefreshCw size={16}/>重新观察</button><button className="secondary" disabled={busy||offline} onClick={()=>action(paused?'resume':'pause')}>{paused?<Play size={15}/>:<Pause size={15}/>} {paused?'恢复守护':'暂停'}</button></div><div className="explanation"><ShieldCheck size={15}/><p>“重新观察”会请求新画面。只有新证据确认恢复后，告警才会解决。</p></div><div className="next-step"><div><span>接入进度</span><b>模拟链路验证</b></div><div className="progress-track"><i/></div><p>下一阶段：实拍素材与正式设备适配</p></div></aside></div>
      </>}
      {(tab==='dashboard'||tab==='evidence')&&<section className="panel history"><div className="section-title"><div><h2>证据时间线</h2><p>状态与原始画面一起保存，页面关闭后任务仍继续。</p></div><div className="segmented"><button className={eventFilter==='business'?'active':''} onClick={()=>setEventFilter('business')}>关键事件</button><button className={eventFilter==='all'?'active':''} onClick={()=>setEventFilter('all')}>全部记录</button></div></div><div className="event-list">{shownEvents.slice(0,tab==='dashboard'?8:50).map(e=><div className="event-row" key={e.sequence}><span className={'event-icon '+e.type}>{e.type==='alert_opened'?<AlertTriangle size={17}/>:e.type==='alert_resolved'?<CheckCheck size={17}/>:<Clock3 size={16}/>}</span><div className="event-main"><span className="event-type">{eventLabels[e.type]||e.type}<small>#{e.sequence} · v{e.revision}</small></span><strong>{e.text}</strong></div><div className="event-evidence">{e.evidence?.slice(0,2).map(o=><button key={o.frame_id} onClick={()=>setSelected(o)} title="查看原始证据"><img alt={`${o.device_id} 证据`} src={imageUrl(o)}/><ArrowUpRight size={12}/></button>)}</div><time>{fmt(e.at)}</time></div>)}{shownEvents.length===0&&<div className="empty">等待第一条守护记录</div>}</div>{tab==='dashboard'&&<button className="history-more" onClick={()=>setTab('evidence')}>查看证据记录 <ArrowUpRight size={14}/></button>}</section>}
      {tab==='devices'&&<><div className="device-grid">{data.cameras.map(c=><section key={c.id} className="panel device-card"><div className="device-icon"><Camera size={28}/></div><span className="fixture-badge">模拟适配器</span><h2>{c.id.toUpperCase()} · {c.label}</h2><p>计划接入型号：{c.expected_model}</p><dl><div><dt>实际输入</dt><dd>合成画面 / RTSP</dd></div><div><dt>传输连接</dt><dd>{c.transport_online?'已连接':'等待重连'}</dd></div><div><dt>画面通道</dt><dd>main</dd></div><div><dt>取图方式</dt><dd>{{continuous:'连续画面',on_demand:'按需取图',event_only:'仅事件片段'}[data.settings.mode]}</dd></div><div><dt>正式设备 SDK</dt><dd>待主办方提供</dd></div><div><dt>正式快照 / 并发 / 控制</dt><dd>待核验</dd></div></dl></section>)}</div><section className="panel capabilities-note"><h2>接入边界</h2><p>T8214 有两个镜头，SDK 是否提供独立通道尚未确认。当前两个模拟通道不代表正式设备的通道数量。</p><p>本轮实现的是设备输入、持续判断与证据展示。自然语言 Agent、通用目标识别和真实摄像机控制尚未接入。</p></section><section className="panel history"><div className="section-title"><h2>最近的取图请求</h2></div>{data.commands.slice().reverse().map(c=><div className="command-row" key={c.id}><Camera size={16}/><b>{c.device_id.toUpperCase()}</b><span>{c.reason}</span><em>{statusLabels[c.status]||c.status}</em><time>{fmt(c.requested_at)}</time></div>)}</section></>}
      <footer><span>EvidenceGuard · Anker Hackathon</span><span>本地验证版 · 原始证据可追溯</span></footer>
    </div>
   </main>
   {notice&&<div role="status" className="toast"><Check size={17}/>{notice}</div>}
   {selected&&<div className="modal-backdrop" onClick={()=>setSelected(null)}><section className="evidence-modal" role="dialog" aria-modal="true" aria-label="原始证据" onClick={e=>e.stopPropagation()}><div className="section-title"><div><h2>原始证据</h2><p>{selected.device_id.toUpperCase()} · 合成素材</p></div><button className="icon-button" aria-label="关闭证据" onClick={()=>setSelected(null)}><X/></button></div><img className="evidence-image" src={imageUrl(selected)} alt="未经区域覆盖的原始证据画面"/><div className="evidence-details"><div><span>采集时间</span><strong>{fmt(selected.captured_at)}</strong></div><div><span>接收时间</span><strong>{fmt(selected.received_at)}</strong></div><div><span>规则版本</span><strong>v{selected.revision}</strong></div><div><span>画面判断</span><strong>{{inside:'区内',outside:'区外',unknown:'无法判断'}[selected.relation]}</strong></div></div><p>{selected.reason}</p><code>{selected.frame_id}</code><a href={imageUrl(selected)} target="_blank" rel="noreferrer">打开原图 <ExternalLink size={14}/></a></section></div>}
  </div>
 }

function Metric({label,value,suffix,icon}:{label:string;value:string;suffix:string;icon:React.ReactNode}){return <div className="metric"><div><span>{label}</span><strong>{value}<small>{suffix}</small></strong></div><div className="metric-icon">{icon}</div></div>}

function CameraCard({camera:c,editing,roi,onRoi,onOpen}:{camera:CameraState;editing:boolean;roi:number[];onRoi:(r:number[])=>void;onOpen:()=>void}){
 const start=useRef<number[]|null>(null);
 const coords=(e:React.PointerEvent<SVGSVGElement>)=>{const r=e.currentTarget.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
 return <article className="camera-card"><div className="camera-card-title"><div><span className="camera-letter">{c.id==='cam-a'?'A':'B'}</span><b>{c.label}</b><small>{c.id.toUpperCase()}</small></div><span className={c.fresh?'connection fresh':'connection'}>{c.transport_online?<Wifi size={12}/>:<WifiOff size={12}/>} {c.fresh?'新鲜画面':c.transport_online?'画面已过期':'连接中断'}</span></div><div className={'camera-frame '+(editing?'editing':'')}>
  {c.image_url?<img src={c.image_url} alt={`${c.label}：模拟摄像头画面`}/>:<div className="frame-wait"><Camera size={28}/><span>等待视频流…</span></div>}
  <svg viewBox="0 0 640 400" preserveAspectRatio="none" aria-label={`${c.label}区域圈选`} onPointerDown={e=>{if(!editing)return;start.current=coords(e);e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(!editing||!start.current)return;const p=coords(e),s=start.current;onRoi([Math.min(s[0],p[0]),Math.min(s[1],p[1]),Math.max(s[0],p[0]),Math.max(s[1],p[1])]);}} onPointerUp={()=>{start.current=null;}}>
   <rect x={roi[0]*640} y={roi[1]*400} width={(roi[2]-roi[0])*640} height={(roi[3]-roi[1])*400} rx="3" fill="#9be3bb18" stroke="#f3ffda" strokeWidth="2" strokeDasharray="7 4"/>
   <rect x={roi[0]*640} y={roi[1]*400-25} width="92" height="23" rx="3" fill="#244f3d"/><text x={roi[0]*640+9} y={roi[1]*400-9} fill="white" fontSize="12">{editing?'拖动调整区域':'守护区域'}</text>
   {c.observation?.bbox&&!editing&&<rect x={c.observation.bbox[0]*640-6} y={c.observation.bbox[1]*400-6} width={(c.observation.bbox[2]-c.observation.bbox[0])*640+12} height={(c.observation.bbox[3]-c.observation.bbox[1])*400+12} fill="none" stroke="#f8c47c" strokeWidth="2"/>}
  </svg><span className="frame-label">合成素材</span>{!editing&&c.observation&&<button className="expand" aria-label={`查看${c.label}原图`} onClick={onOpen}><ArrowUpRight size={17}/></button>}
 </div><div className="camera-footer"><span><Clock3 size={12}/>{fmt(c.observation?.captured_at)}</span><span>{c.age===null?'尚无证据':`${Math.max(0,c.age).toFixed(1)} 秒前采集`}</span></div></article>
}
createRoot(document.getElementById('root')!).render(<App/>);
