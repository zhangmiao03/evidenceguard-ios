import {useEffect,useRef,useState} from 'react';
import {IOSPreview} from './IOSPreview';
import {useIOSTour} from './useIOSTour';
import {tourScenarios} from './tourData';
import './briefing.css';

const steps=['说出需求','圈定关注区域','建立观察基线','发现条件变化','收到提醒与证据'];
export function JudgeTour({onMonitor,onPage}:{onMonitor:()=>void;onPage?:(n:number)=>void}){
  const tour=useIOSTour(),apply=useRef(tour.presentScene);apply.current=tour.presentScene;
  const [position,setPosition]=useState(0),[playing,setPlaying]=useState(()=>!matchMedia('(prefers-reduced-motion: reduce)').matches),[scale,setScale]=useState(.6);
  const scene=tourScenarios[Math.floor(position/5)],step=position%5;
  useEffect(()=>{apply.current(scene.id,step);},[scene.id,step]);
  useEffect(()=>{const resize=()=>setScale(Math.min(.82,Math.max(.45,(innerHeight-205)/852),(innerWidth-72)/393));resize();window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
  useEffect(()=>{if(!playing)return;const timer=window.setInterval(()=>{if(document.hidden)return;setPosition(n=>{if(n===14){setPlaying(false);return n;}return n+1;});},4000);return()=>clearInterval(timer);},[playing]);
  const description=[scene.prompt,`指定“${scene.area}”，并由用户确认开启。`,scene.present+'，作为后续判断的依据。',scene.changed+'，保留对应证据。','提醒回到主对话，可以继续追问依据；看不清时返回“无法确认”。'][step];
  return <section className="eg-brief-tour" aria-label="自动场景导览">
    <div className="eg-brief-story"><span className="eg-media-eyebrow">从一句话，到有依据的提醒</span><h1>让摄像头<br/>记住你在意的事。</h1><p className="eg-brief-lead">三个生活场景自动演示，无需逐个点击。</p>
      <div className="eg-brief-scenes">{tourScenarios.map((s,i)=><button key={s.id} aria-pressed={s.id===scene.id} onClick={()=>setPosition(i*5)}><small>0{i+1}</small><strong>{s.label}</strong><span>{s.id==='pet'?'进入区域 → 提醒':'物品离区 → 提醒'}</span></button>)}</div>
      <article className="eg-brief-current" aria-live={playing?'off':'polite'}><small>{scene.label} · {step+1} / 5</small><h2>{steps[step]}</h2><p>{description}</p><ol className="eg-brief-steps">{steps.map((title,i)=><li key={title} className={i===step?'current':i<step?'done':''}><span>{i<step?'✓':i+1}</span>{title}</li>)}</ol></article>
      <div className="eg-brief-controls"><button className="primary" aria-label={playing?'暂停自动导览':'继续自动导览'} onClick={()=>{if(position===14)setPosition(0);setPlaying(!playing);}}>{playing?'Ⅱ 暂停':'▶ 播放'}</button><button onClick={()=>{setPlaying(false);setPosition(n=>Math.max(0,n-1));}}>上一步</button><button onClick={()=>{setPlaying(false);setPosition(n=>Math.min(14,n+1));}}>下一步</button><button onClick={()=>{setPosition(0);setPlaying(true);}}>重播</button><small>{position===14&&!playing?'导览结束':`${position*4} / 60 秒`}</small></div>
      <p className="eg-brief-caption">交互脚本示例 · 不连接硬件。真实记录从下面继续查看。</p>
      <div className="eg-brief-links"><button onClick={()=>onPage?.(13)}>① 画面如何被理解 →</button><button onClick={()=>onPage?.(14)}>② 视频如何被找回 →</button><button onClick={onMonitor}>③ Agent 如何完成任务 →</button></div>
    </div>
    <div className="eg-brief-phone"><span>依据当前 iOS 前端的网页交互预览</span><div style={{width:393*scale,height:852*scale}}><div style={{width:393,height:852,transform:`scale(${scale})`,transformOrigin:'top left',pointerEvents:'none'}} aria-hidden="true" ref={node=>node?.setAttribute("inert","")}><IOSPreview tour={tour}/></div></div><small>原生硬件连接与控制由手机 SDK 执行</small></div>
  </section>;
}
