import {useEffect,useRef,useState} from 'react';
import {IOSPreview} from './IOSPreview';
import {useIOSTour} from './useIOSTour';
import {tourScenarios} from './tourData';
import './briefing.css';

const steps=['说出需求','圈定关注区域','建立观察基线','发现条件变化','收到提醒与证据'];
const totalSeconds=20,totalSteps=steps.length*tourScenarios.length;
const elapsedMs=(position:number)=>Math.round(position*totalSeconds*1000/totalSteps);
export function JudgeTour({onMonitor,onPage}:{onMonitor:()=>void;onPage?:(n:number)=>void}){
  const tour=useIOSTour(),apply=useRef(tour.presentScene);apply.current=tour.presentScene;
  const [position,setPosition]=useState(0),[playing,setPlaying]=useState(()=>!matchMedia('(prefers-reduced-motion: reduce)').matches),[scale,setScale]=useState(.6);
  const scene=tourScenarios[Math.floor(position/steps.length)],step=position%steps.length;
  useEffect(()=>{apply.current(scene.id,step);},[scene.id,step]);
  useEffect(()=>{const resize=()=>setScale(Math.min(.82,Math.max(.45,(innerHeight-205)/852),(innerWidth-72)/393));resize();window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
  useEffect(()=>{if(!playing)return;const timer=window.setInterval(()=>{if(document.hidden)return;if(position===totalSteps-1)setPlaying(false);else setPosition(position+1);},elapsedMs(position+1)-elapsedMs(position));return()=>clearInterval(timer);},[playing,position]);
  const description=[scene.prompt,`指定“${scene.area}”，并由用户确认开启。`,scene.present+'，作为后续判断的依据。',scene.changed+'，保留对应证据。','直接展示提醒画面与来源；可带着证据追问，看不清时返回“无法确认”。'][step];
  return <section className="eg-brief-tour" aria-label="自动场景导览">
    <div className="eg-brief-story"><span className="eg-media-eyebrow">从一句话，到有依据的提醒</span><h1>用一句话，<br/>教摄像头新 Skill。</h1><p className="eg-brief-lead">20 秒看完三个场景，每个场景约 7 秒。</p>
      <div className="eg-brief-scenes">{tourScenarios.map((s,i)=><button key={s.id} aria-pressed={s.id===scene.id} onClick={()=>setPosition(i*steps.length)}><small>0{i+1}</small><strong>{s.label}</strong><span>{s.id==='pet'?'进入区域 → 提醒':'物品离区 → 提醒'}</span></button>)}</div>
      <article className="eg-brief-current" aria-live={playing?'off':'polite'}><small>{scene.label} · {step+1} / 5</small><h2>{steps[step]}</h2><p>{description}</p><ol className="eg-brief-steps">{steps.map((title,i)=><li key={title} className={i===step?'current':i<step?'done':''}><span>{i<step?'✓':i+1}</span>{title}</li>)}</ol></article>
      <div className="eg-brief-controls"><button className="primary" aria-label={playing?'暂停自动导览':'继续自动导览'} onClick={()=>{if(position===totalSteps-1)setPosition(0);setPlaying(!playing);}}>{playing?'Ⅱ 暂停':'▶ 播放'}</button><button onClick={()=>{setPlaying(false);setPosition(n=>Math.max(0,n-1));}}>上一步</button><button onClick={()=>{setPlaying(false);setPosition(n=>Math.min(totalSteps-1,n+1));}}>下一步</button><button onClick={()=>{setPosition(0);setPlaying(true);}}>重播</button><small>{position===totalSteps-1&&!playing?`${totalSeconds} 秒 · 导览结束`:`${Number((elapsedMs(position)/1000).toFixed(1))} / ${totalSeconds} 秒`}</small></div>
      <p className="eg-brief-caption">交互脚本示例 · 不连接硬件。真实记录从下面继续查看。</p>
      <div className="eg-brief-links"><button onClick={()=>onPage?.(5)}>① 看真实 Skill 生成与修改 →</button><button onClick={()=>onPage?.(14)}>② 看向量检索的命中画面 →</button><button onClick={()=>onPage?.(13)}>③ 图像理解与处理 →</button><button onClick={onMonitor}>④ Agent 完整链路 →</button></div>
    </div>
    <div className="eg-brief-phone"><span>依据当前 iOS 前端的网页交互预览</span><div style={{width:393*scale,height:852*scale}}><div style={{width:393,height:852,transform:`scale(${scale})`,transformOrigin:'top left',pointerEvents:'none'}} aria-hidden="true" ref={node=>node?.setAttribute("inert","")}><IOSPreview tour={tour}/></div></div><small>原生硬件连接与控制由手机 SDK 执行</small></div>
  </section>;
}
