import {useState} from 'react';
import {publicMediaUrl} from './MediaPreview';
import {time,sec,type MediaRow} from './MediaPanels';
import './skill-studio.css';

type Box={x:number;y:number;width:number;height:number};
const labels:Record<string,string>={target:'关注对象',selection:'框选方式',trigger:'触发条件',confirmationSeconds:'观察跨度',completion:'提醒方式'};
function readable(key:string,value:any){
  if(key==='selection')return value==='object'?'框选具体对象及初始位置':value==='region'?'框选固定区域':String(value??'未生成');
  if(key==='trigger')return value==='leaves'?'离开所选区域时提醒':value==='enters'?'进入所选区域时提醒':'未生成';
  if(key==='completion')return value==='once'?'只提醒一次':value==='continuous'?'持续关注':'未生成';
  return key==='confirmationSeconds'?`${value} 秒，至少两次采样`:String(value??'未生成');
}
function SelectionPicture({media,offset}:{media:any[];offset:number}){
  const [box,setBox]=useState<Box|null>(null),[start,setStart]=useState<{x:number;y:number}|null>(null);
  const image=media?.find(m=>m.kind==='image'&&publicMediaUrl(m.previewUrl));
  function point(e:React.PointerEvent<HTMLDivElement>){const r=e.currentTarget.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};}
  return <div className="eg-skill-picture"><div className="eg-skill-image" aria-label="关注区域框选示意" onPointerDown={e=>{if(!image)return;e.currentTarget.setPointerCapture(e.pointerId);setStart(point(e));setBox(null);}} onPointerMove={e=>{if(!start)return;const p=point(e);setBox({x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),width:Math.abs(p.x-start.x),height:Math.abs(p.y-start.y)});}} onPointerUp={()=>setStart(null)} onPointerCancel={()=>setStart(null)}>
    {image?<img src={image.previewUrl} alt={`已公开实拍录像 ${sec(offset)} 的水瓶画面；用于演示框选，不是本次编译输入`} draggable={false}/>:<p>当前没有这次案例对应的可展示画面。</p>}
    {box&&box.width>.02&&box.height>.02&&<span className="eg-skill-roi" style={{left:box.x*100+'%',top:box.y*100+'%',width:box.width*100+'%',height:box.height*100+'%'}}><b>关注区域 · 示意</b></span>}
  </div><div className="eg-skill-image-caption"><span>实拍录像 · {sec(offset)}<small>拖动画面试框选；此选框只保存在浏览器。</small></span>{box&&<button onClick={()=>setBox(null)}>清除示意框</button>}</div><p>编译只接收文字。实际开启时，由 iOS 获取新画面、提交选框和用户确认；这张历史帧不能用来开启守护。</p></div>;
}

export function SkillStudio({rows,onSelect,onPage}:{rows:MediaRow[];onSelect:(row:any)=>void;onPage:(page:number)=>void}){
  const cases=rows.filter(r=>r.name==='media_skill_generation_case').sort((a,b)=>b.at-a.at);
  const item=cases[0],d=item?.data,revisions=d?.revisions||[];
  const [revision,setRevision]=useState(-1);
  const index=revision>=0&&revision<revisions.length?revision:Math.max(0,revisions.length-1);
  const current=revisions[index],plan=current?.plan,previous=revisions[index-1]?.plan;
  const changed=Object.keys(labels).filter(k=>previous&&plan&&plan[k]!==previous[k]);
  return <div className="eg-skill-studio">
    <header className="eg-skill-intro"><div><span className="eg-media-eyebrow">CUSTOM SKILL / 从需求生成规则</span><h2>你来定义要关注的事，<br/>AI 把它变成 Skill。</h2><p>自由描述对象与变化，再通过对话修改。生成的是可校验的规则草稿，用户确认后才开始守护。</p></div><div className="eg-skill-status"><b>{item?'真实后端生成记录':'等待公开生成记录'}</b><span>{item?'草稿已保存 · 未开启硬件':'当前环境没有公开的验证案例'}</span></div></header>
    <ol className="eg-skill-path"><li><b>01</b><strong>说出需求</strong><span>原话 + 已有草稿</span></li><li><b>02</b><strong>AI 生成规则</strong><span>对象、条件、观察跨度</span></li><li><b>03</b><strong>框选与确认</strong><span>手机新画面 + 版本校验</span></li><li><b>04</b><strong>持续检查</strong><span>基线 → 变化 → 提醒</span></li></ol>
    {item&&current?<section className="eg-skill-workbench" aria-label="真实 Skill 生成与修改">
      <div className="eg-skill-conversation"><span className="eg-media-eyebrow">一次真实的创建与修改</span><h3>看住这个水瓶</h3>
        <div className="eg-skill-revisions" aria-label="草稿版本">{revisions.map((r:any,i:number)=><button key={r.revision} aria-pressed={i===index} onClick={()=>setRevision(i)}>{i===0?'首次生成':`继续修改 · 第 ${i+1} 版`}</button>)}</div>
        {revisions.slice(0,index+1).map((r:any,i:number)=><blockquote className={i===index?'current':''} key={r.revision}><small>{i===0?'用户说':'用户接着说'}</small>{r.input}</blockquote>)}
        <SelectionPicture media={d.referenceMedia} offset={d.referenceOffset}/>
      </div>
      <div className="eg-skill-generated"><div className="eg-skill-plan-heading"><span>AI 生成的 Skill 草稿</span><b>第 {current.revision} 版</b></div><h3>{plan?.title||'还需要补充需求'}</h3>
        {plan?<dl className="eg-skill-fields">{Object.entries(labels).map(([key,label])=><div key={key} className={changed.includes(key)?'changed':''}><dt>{label}</dt><dd>{readable(key,plan[key])}{changed.includes(key)&&<small>本次修改 · 原为 {readable(key,previous[key])}</small>}</dd></div>)}</dl>:null}
        {current.question&&<p className="eg-skill-question">需要澄清：{current.question}</p>}{current.unsupportedReason&&<p className="eg-skill-question">能力边界：{current.unsupportedReason}</p>}
        <div className="eg-skill-delta">{changed.length?`本次改动 ${changed.length} 项，其余规则保留。`:plan?'规则来自本次模型返回，经过结构校验。':'缺少必要条件时继续提问，不擅自替用户生成规则。'}</div>
        <div className="eg-skill-confirm"><b>下一步 · 在 iOS 框选并确认</b><p>{current.summary||current.reason}</p><span>这次验证停在草稿阶段，未获取实时画面、未启动摄像头。</span></div>
        <details className="eg-brief-details"><summary>这份草稿的生成记录与源码依据</summary><p>{time(current.capturedAt)} · 本次接口耗时 {(current.durationMs/1000).toFixed(1)} 秒（含排队与轮询）。</p><p>模型：{d.model||'未记录'} · 执行器：{d.executor||'未记录'}</p><p>visual_skills/harness.py 解释原话；schema.py 校验规则；service.py 保存版本并控制确认和运行。框选图没有传入文字编译器。</p><button onClick={()=>onSelect(item)}>查看实际输入、规则与完整回执</button></details>
      </div>
    </section>:<section className="eg-ops-panel"><h3>当前筛选没有公开的生成结果</h3><p>这里不会用模板代替模型生成。可切换到比赛演示环境或导入包含公开 Skill 案例的离线快照。</p></section>}
    <section className="eg-skill-runtime"><div><span className="eg-media-eyebrow">确认之后，规则如何运行</span><h3>看清才判断，变化才提醒。</h3><p>先建立观察基线；连续有效采样满足跨度后确认条件变化。遮挡、断流或视角变化会返回无法确认。</p><button onClick={()=>onPage(13)}>查看真实画面、Depth 与光流处理 →</button></div><ol><li><b>建立基线</b><span>明确对象与固定区域</span></li><li><b>检查变化</b><span>比较参考图与当前图</span></li><li><b>保留证据</b><span>条件成立后生成提醒</span></li></ol></section>
    <p className="eg-skill-boundary">当前支持可见对象进入 / 离开固定区域；不生成任意执行代码，不做人脸身份判断或跨摄像头追踪。缺条件会追问，超出能力会说明原因。硬件连接与控制由手机官方 SDK 完成。</p>
  </div>;
}
