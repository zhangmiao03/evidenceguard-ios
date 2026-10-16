import {useState} from 'react';
import type {IOSTour} from './useIOSTour';

const steps=[
  ['一句话交代需求','读手机里的需求，看看对象、位置和触发条件。','生成条件与示例选框'],
  ['确认关注区域','已加载示例画面与选区；也可以在手机里重画。','查看条件'],
  ['由用户确认开启','检查对象、持续时间和遮挡处理；确认前不执行。','确认并开启演示'],
  ['建立触发前基线','先确认变化前的状态，不能只凭一张结果图下结论。','采样：建立基线'],
  ['观察条件发生','两次有效样本达到设定跨度。这里压缩演示时间，不代表真实检测。','采样：条件触发'],
  ['遇到遮挡怎么办','刚才的提醒已进入主对话。接着模拟一次不可用画面。','采样：画面遮挡'],
  ['保留无法确认','遮挡后不继续给出确定性判断；恢复后需重新建立基线。','查看提醒与追问'],
  ['回到对话，继续追问','手机保留触发时的提醒。点击“查看提醒画面”或继续追问；再去监控页核对真实数据。','重新演示'],
];
export function TourGuide({tour:t}:{tour:IOSTour}){
  const [step,setStep]=useState(-1);
  function start(){t.restartScene();setStep(0);}
  function next(){
    if(step<0||step===7){start();return;}
    if(step===0)t.patchGuard({stage:1,frame:true,box:{...t.scene.box},result:'pending',reason:'等待框选与确认'});
    if(step===1)t.patchGuard({stage:2});
    if(step===2)t.activate();
    if(step===3)t.observe('baseline');
    if(step===4)t.observe('changed');
    if(step===5)t.observe('unknown');
    if(step===6){t.selectTopic('main');t.root(0);}
    setStep(s=>s+1);
  }
  const valid=step<0||step===7||(t.route==='guard'&&t.editor?.sceneId===t.sceneId&&
    (step===0?t.editor.stage===0:step===1?t.editor.stage===1&&!!t.editor.frame&&!!t.editor.box:step===2?t.editor.stage===2&&t.editor.status==='draft':t.editor.status==='active'));
  return <section className="eg-guided-tour" aria-label="场景逐步导览">
    <small>{step<0?'建议从这里开始':`第 ${step+1} / ${steps.length} 步 · ${t.scene.label}`}</small>
    <h3>{step<0?'跟着做一次完整守护':steps[step][0]}</h3>
    <p aria-live="polite">{step<0?`“${t.scene.prompt}”`:steps[step][1]}</p>
    <div className="eg-guide-progress" aria-label="导览进度">{steps.map(([label],i)=><span key={label} className={i<=step?'done':''} title={label}/>)}</div>
    <button className="eg-showcase-primary" onClick={next} disabled={!valid}>{step<0?'开始逐步演示':steps[step][2]}</button>
    {step>=0&&<button className="eg-guide-reset" onClick={start}>重新开始此场景</button>}
    {!valid&&<p role="status">你已切到自由操作，可重新开始导览。真实业务不受影响。</p>}
    <small>固定脚本 · 仅重置网页示例；同一摄像头的另一示例会暂停。</small>
  </section>;
}
