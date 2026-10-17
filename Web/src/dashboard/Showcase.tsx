import {useEffect,useState} from 'react';
import './showcase.css';
import './phone.css';
import {IOSPreview} from './IOSPreview';
import {useIOSTour} from './useIOSTour';
import {tourScenarios,type TourCondition} from './tourData';
import {TourGuide} from './TourGuide';
import {JudgeTour} from './JudgeTour';

export function Showcase({onMonitor,onPage}:{onMonitor:()=>void;onPage?:(page:number)=>void}) {
  const [manual,setManual]=useState(new URLSearchParams(location.search).get('tour')==='manual');
  useEffect(()=>{for(const s of tourScenarios)for(const src of [s.photo,s.changedPhoto]){const image=new Image();image.src=src;}},[]);
  return <><div className="eg-tour-mode"><button aria-pressed={!manual} onClick={()=>setManual(false)}>30 秒自动导览</button><button aria-pressed={manual} onClick={()=>setManual(true)}>自己操作 App</button></div>{manual?<ManualShowcase onMonitor={onMonitor} onPage={onPage}/>:<JudgeTour onMonitor={onMonitor} onPage={onPage}/>}</>;
}

function ManualShowcase({onMonitor,onPage}:{onMonitor:()=>void;onPage?:(page:number)=>void}) {
  const tour=useIOSTour(),[copied,setCopied]=useState(false),[large,setLarge]=useState(false),[scale,setScale]=useState(1);
  useEffect(()=>{const resize=()=>setScale(window.innerWidth>=1000&&!large?Math.max(.5,Math.min(1,(window.innerHeight-250)/852)):Math.min(1,(window.innerWidth-70)/393));resize();window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[large]);
  return <section className="eg-showcase">
    <header className="eg-showcase-heading"><div><span className="eg-showcase-kicker">EVIDENCEGUARD / APP WALKTHROUGH</span><h2>和 anker 说一件事，<em>让摄像头持续关注。</em></h2><p>跟随新版 App：聊需求、框选画面、确认守护，收到提醒后继续追问。</p></div><span className="eg-showcase-demo-tag">iOS 交互演示 · 示例数据 · 不连接硬件</span></header>
    <div className="eg-showcase-stage">
      <aside className="eg-showcase-guide"><small>选择一段体验</small><div className="eg-showcase-scenes">{tourScenarios.map((s,i)=><button key={s.id} aria-pressed={tour.sceneId===s.id} onClick={()=>tour.chooseScene(s.id)}><span>0{i+1}</span><strong>{s.label}<small>{s.camera} · {s.model}</small></strong><b>›</b></button>)}</div>
        <TourGuide key={tour.sceneId} tour={tour}/>
        <div className="eg-showcase-guidecard"><small>从需求到提醒</small><ol><li>说出要关注的对象与条件</li><li>获取画面，框选关注区域</li><li>确认开启，再检查基线与变化</li><li>在主对话查看提醒并追问</li></ol><button className="eg-showcase-primary" onClick={()=>tour.beginGuard()}>体验创建守护</button><p>也可以直接操作手机中的五个页面，体验历史检索、设备连接步骤和记忆管理。</p></div>
        <div className="eg-showcase-proof"><span>从交互走到真实运行</span><p>手机内是固定脚本示例。模型的真实提示词、工具调用、图片与最终回复，在监控页面逐条查看。</p><button onClick={onMonitor}>查看真实 Agent 链路 ↗</button><a href="https://demo.47.131.21.137.sslip.io/dashboard/downloads/evidenceguard-website.zip" download>下载可部署的完整网站 ZIP ↓</a></div>
      </aside>
      <div className="eg-tour-phone-column"><button className="eg-phone-size" onClick={()=>setLarge(!large)}>{large?'适应窗口':'放大手机细看'}</button><div className="eg-tour-phone-fit" style={{width:393*scale,height:852*scale}}><div style={{width:393,height:852,transform:`scale(${scale})`,transformOrigin:'top left'}}><IOSPreview tour={tour}/></div></div></div>
      <aside className="eg-showcase-inspector"><small>推进一次示例检查</small><h3>先看到基线，<br/>再判断变化。</h3><p>确认开启守护后，使用以下按钮模拟一次有效检查或断流。无需真实硬件。</p>
        <div className="eg-showcase-states">{([['baseline','建立基线'],['changed','条件触发'],['unknown','画面遮挡']] as [TourCondition,string][]).map(([id,label])=><button key={id} disabled={tour.currentGuard?.status!=='active'} aria-pressed={tour.condition===id} onClick={()=>tour.observe(id)}><span className={'eg-tour-dot '+id}/>{label}<span>{tour.condition===id?'✓':'○'}</span></button>)}</div>
        <div className="eg-showcase-observation" aria-live="polite"><small>当前示例结果</small><strong>{tour.outcome}</strong><p>{tour.currentGuard?.reason||'还没有开启守护。先完成需求与选框确认。'}</p><span>状态为脚本示例；参考图片不代表真实检查结果。</span></div>
        <div className="eg-showcase-real"><small>再看真实后端发生了什么</small><button onClick={()=>onPage?.(13)}>图像记忆与识图 →</button><button onClick={()=>onPage?.(14)}>实拍录像与向量检索 →</button><button onClick={onMonitor}>Agent 逐步回放 →</button></div>
        <dl><dt>新版五个入口</dt><dd>助手 / 摄像头守护 / 设备 / 记忆 / 我的</dd><dt>现场与历史</dt><dd>现场可讨论守护；历史只检索已保存资料。</dd><dt>连接与硬件</dt><dd>手机 App 前台单路取样；官方 SDK 调试位于“我的 → 设置”。Web 只展示流程。</dd></dl>
        <button onClick={async()=>{try{await navigator.clipboard.writeText(location.origin+'/dashboard?view=showcase');setCopied(true);}catch{setCopied(false);}}}>{copied?'作品入口已复制':'复制作品入口'}</button><small>依据最新 iOS 源码，导航基线为 1.0(17)；含新增首尾图分析流程示例。网页预览不是原生 iOS 模拟器。</small>
      </aside>
    </div>
  </section>;
}
