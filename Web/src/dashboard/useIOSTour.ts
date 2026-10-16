import {useEffect, useState} from 'react';
import {tourScenarios, type TourBox, type TourCondition, type TourScene} from './tourData';

export type TourGuard = {id:string;sceneId:string;prompt:string;stage:0|1|2;status:'draft'|'active'|'completed';frame:boolean;box:TourBox|null;seconds:number;once:boolean;result:'pending'|'checking'|'confirmed'|'issue'|'unknown';reason:string;baseline:boolean;evidence:boolean;analysis?:{text:string;sample:TourCondition;cached:boolean}};
type Message = {role:'user'|'assistant';text:string;mode:'live'|'history';kind?:'frame'|'guard'|'history'|'reminder';sceneId:string;condition:TourCondition};
type Topic = {id:string;title:string;messages:Message[]};
type Memory = {id:number;content:string;temporary:boolean;source:string};
export const guardLabels={pending:'待确认',checking:'检查中',confirmed:'已确认',issue:'需关注',unknown:'无法确认'};
const draftFor=(scene:TourScene):TourGuard=>({id:scene.id,sceneId:scene.id,prompt:scene.prompt,stage:0,status:'draft',frame:false,box:null,seconds:15,once:false,result:'pending',reason:'条件待确认',baseline:false,evidence:false});

/** Browser-only sample state. This module intentionally imports no API/SDK client. */
export function useIOSTour() {
  const [sceneId,setSceneId]=useState('door'),[tab,setTab]=useState(0),[stack,setStack]=useState<string[]>([]);
  const [condition,setCondition]=useState<TourCondition>('baseline'),[camera,setCamera]=useState('doorbell');
  const [mode,setMode]=useState<'live'|'history'>('live'),[toolsOpen,setToolsOpen]=useState(false),[showFrame,setShowFrame]=useState(false);
  const [topics,setTopics]=useState<Topic[]>([{id:'main',title:'anker 主对话',messages:[]}]),[topicId,setTopicId]=useState('main'),[input,setInput]=useState('');
  const [guards,setGuards]=useState<TourGuard[]>([]),[editorId,setEditorId]=useState('door'),[revision,setRevision]=useState(''),[error,setError]=useState('');
  const [automaticMemory,setAutomaticMemory]=useState(true),[memoryFilter,setMemoryFilter]=useState('all');
  const [memories,setMemories]=useState<Memory[]>([{id:1,content:'画面不清楚时，请先说明无法确认。',temporary:false,source:'你手动记下的'}]);
  const [memoryText,setMemoryText]=useState(''),[temporary,setTemporary]=useState(false),[removing,setRemoving]=useState<number|null>(null);
  const [nearby,setNearby]=useState(false),[deviceName,setDeviceName]=useState('平板中枢 · 示例设备'),[deviceKind,setDeviceKind]=useState('平板中枢');
  const [bluetooth,setBluetooth]=useState<{name:string;kind:string;connected:boolean}[]>([]);
  const [nickname,setNickname]=useState('小安'),[toast,setToast]=useState('');
  const [preferences,setPreferences]=useState({phone:false,proactive:true,morning:true,evening:true,automaticObservation:false,eventSync:true});
  const [morningHour,setMorningHour]=useState('8'),[eveningHour,setEveningHour]=useState('21');
  const [query,setQuery]=useState(''),[reference,setReference]=useState(false),[cropBox,setCropBox]=useState<TourBox|null>(null),[cropping,setCropping]=useState(false),[period,setPeriod]=useState('全部日期'),[searchCamera,setSearchCamera]=useState('all'),[searched,setSearched]=useState(false);
  const scene=tourScenarios.find(s=>s.id===sceneId)!;
  const editor=guards.find(g=>g.id===editorId);
  const editorScene=tourScenarios.find(s=>s.id===editor?.sceneId)||scene;
  const currentGuard=guards.find(g=>g.sceneId===sceneId);
  const topic=topics.find(t=>t.id===topicId)||topics[0];
  const route=stack.at(-1)||'';
  useEffect(()=>{if(!toast)return;const timer=window.setTimeout(()=>setToast(''),4000);return()=>clearTimeout(timer);},[toast]);
  function go(page:string){setStack(s=>[...s,page]);setToolsOpen(false);setError('');}
  function back(){setStack(s=>s.slice(0,-1));setError('');}
  function root(next:number){if(next===1&&camera==='all')setCamera(scene.device);setTab(next);setStack([]);setToolsOpen(false);setError('');}
  function chooseScene(id:string){const next=tourScenarios.find(s=>s.id===id)!;setSceneId(id);setCamera(next.device);setCondition('baseline');setShowFrame(false);setReference(false);setCropBox(null);setSearched(false);root(0);}
  function openEvidence(id=sceneId){const next=tourScenarios.find(s=>s.id===id)!;setSceneId(id);setCamera(next.device);go('evidence');}
  function patchGuard(patch:Partial<TourGuard>){setGuards(items=>items.map(g=>g.id===editorId?{...g,...patch}:g));setError('');}
  function beginGuard(id=sceneId){
    const selected=tourScenarios.find(s=>s.id===id)!;setEditorId(id);setSceneId(id);setCamera(selected.device);
    setGuards(items=>items.some(g=>g.id===id)?items:[...items,draftFor(selected)]);
    setTab(1);setStack(['guard']);setToolsOpen(false);setError('');setRevision('');
  }
  function restartScene(){
    // Explicit guide reset affects browser examples only, never a device or API.
    setGuards(items=>[...items.filter(g=>g.id!==sceneId).map(g=>tourScenarios.find(s=>s.id===g.sceneId)?.device===scene.device?{...g,status:'draft' as const,stage:1 as const,frame:false,box:null,baseline:false,result:'pending' as const,reason:'切换演示场景，已暂停'}:g),draftFor(scene)]);
    setTopics(items=>items.map(t=>t.id==='main'?{...t,messages:t.messages.filter(m=>m.sceneId!==sceneId)}:t));
    setTopicId('main');setCondition('baseline');setMode('live');setInput('');setPreferences(p=>({...p,proactive:true}));beginGuard();
  }
  function generate(){if(!editor?.prompt.trim())return;patchGuard({stage:1,frame:false,box:null,result:'pending',reason:'等待框选与确认'});}
  function revise(){
    if(!editor)return;
    if(!/一次|持续|分钟|秒/.test(revision)){setError('此处演示固定条件修改。可试试“改为一分钟，只提醒一次”。');return;}
    const seconds=revision.includes('一分钟')?60:revision.includes('三十')||revision.includes('30秒')?30:editor.seconds;
    patchGuard({prompt:editor.prompt+'\n补充：'+revision,seconds,once:revision.includes('一次')?true:revision.includes('持续')?false:editor.once,stage:1,frame:false,box:null});setRevision('');
  }
  function activate(){
    if(!editor?.frame||!editor.box||editor.stage!==2)return;
    if(guards.some(g=>g.id!==editor.id&&g.status==='active'&&tourScenarios.find(s=>s.id===g.sceneId)?.device===editorScene.device)){setError('这台摄像头已有运行中的守护，请先暂停原守护。');return;}
    patchGuard({status:'active',result:'checking',baseline:false,reason:'正在等待新的有效观察',evidence:false,analysis:undefined});setToast('演示守护已开启，等待有效检查');
  }
  function pause(){patchGuard({status:'draft',stage:1,box:null,frame:false,baseline:false,result:'pending',reason:'已暂停，需要获取新画面并重新框选',analysis:undefined});setToast('已暂停，旧选框已清除');}
  function compareEndpoints(){
    if(!editor||editor.status==='draft')return;
    const text=editor.result==='checking'?'示例：尚无最近的有效采样，无法进行首尾核对。':editor.result==='unknown'?'示例：最近采样不可用或缺少基线，不能确认变化。':`示例核对：${editor.reason}。这只是两张保存图片的对照，不代表中间过程持续可见。`;
    patchGuard({analysis:{text,sample:condition,cached:editor.analysis?.text===text&&editor.analysis?.sample===condition}});
  }
  function observe(next:TourCondition){
    setCondition(next);if(!currentGuard||currentGuard.status!=='active')return;
    const baseline=next==='baseline',unknown=next==='unknown'||(!currentGuard.baseline&&next==='changed');
    const issue=!baseline&&!unknown;
    const reason=baseline?scene.present:next==='unknown'?'画面被遮挡，无法确认；恢复后重新建立基线。':unknown?'尚未建立触发前基线，不能直接判定发生变化。':scene.changed;
    setGuards(items=>items.map(g=>g.id===currentGuard.id?{...g,result:unknown?'unknown':issue?'issue':'confirmed',reason,baseline:unknown?false:baseline||g.baseline,evidence:g.evidence||issue,status:issue&&g.once?'completed':g.status}:g));
    if(issue&&!currentGuard.evidence&&preferences.proactive){
      setTopics(items=>items.map(t=>t.id==='main'?{...t,messages:[...t.messages,{role:'assistant',text:scene.changed+'。已保留提醒画面，可以继续追问。',kind:'reminder',sceneId,mode:'live',condition:'changed'}]}:t));
      setToast('一条示例提醒已进入 anker 主对话');
    }
  }
  function ask(){
    const text=input.trim();if(!text)return;
    const kind=mode==='history'?'history':/守护|看住|提醒/.test(text)?'guard':'frame';
    const reply=mode==='history'?'可以在已保存录像中按文字或参考图片检索，再打开原片核对。这个历史模式不会请求现场画面，也不会修改守护。':kind==='guard'?'一起确认这件事。先说清对象和条件，再获取画面、框选区域，最后由你确认开启。':condition==='unknown'?'当前示例画面不可用，我无法确认现场情况。等待新的有效画面后再判断。':`示例观察：${condition==='changed'?scene.changed:scene.id==='pet'?'参考画面里可见一只狗':scene.present}。结论只对应这次画面，不能据此判断画外情况。`;
    setTopics(items=>items.map(t=>t.id===topicId?{...t,messages:[...t.messages,{role:'user',text,mode,sceneId,condition},{role:'assistant',text:reply,mode,sceneId,kind,condition}]}:t));setInput('');setToolsOpen(false);
  }
  function newTopic(){const id='topic-'+Date.now();setTopics(items=>[...items,{id,title:'新对话 '+items.length,messages:[]}]);setTopicId(id);setInput('');root(0);}
  function selectTopic(id:string){setTopicId(id);root(0);}
  function remember(){const content=memoryText.trim();if(!content||content.length>500)return;setMemories(items=>[{id:Date.now(),content,temporary,source:'你手动记下的'},...items]);setMemoryText('');setTemporary(false);back();setToast('已记住 · 仅保留在本次网页演示');}
  function openMemory(){setMemoryText('');setTemporary(false);go('add-memory');}
  function toggle(key:keyof typeof preferences){setPreferences(p=>({...p,[key]:!p[key]}));}
  function selectCamera(id:string){setCamera(id);if(id!=='all'&&scene.device!==id){const next=tourScenarios.find(s=>s.device===id)!;setSceneId(next.id);setCondition('baseline');setReference(false);setCropBox(null);setSearched(false);}setShowFrame(false);}
  function connectBluetooth(){setBluetooth([{name:deviceName.trim()||'示例设备',kind:deviceKind,connected:true}]);back();setToast('示例流程完成；没有连接真实蓝牙设备');}
  function followEvidence(){root(0);setMode('live');setInput('刚才的提醒说明了什么？有哪些不能确认的地方？');}
  const outcome=currentGuard?guardLabels[currentGuard.result]:'尚未创建守护';
  return {sceneId,scene,condition,tab,route,stack,root,go,back,chooseScene,observe,outcome,toolsOpen,setToolsOpen,showFrame,setShowFrame,
    camera,selectCamera,mode,setMode,topic,topicId,topics,input,setInput,ask,newTopic,selectTopic,
    guards,editor,editorScene,currentGuard,beginGuard,restartScene,patchGuard,generate,revise,revision,setRevision,activate,pause,compareEndpoints,error,
    automaticMemory,setAutomaticMemory,memoryFilter,setMemoryFilter,memories,setMemories,memoryText,setMemoryText,temporary,setTemporary,removing,setRemoving,remember,openMemory,
    nearby,setNearby,deviceName,setDeviceName,deviceKind,setDeviceKind,bluetooth,setBluetooth,connectBluetooth,
    nickname,setNickname,toast,setToast,preferences,toggle,morningHour,setMorningHour,eveningHour,setEveningHour,
    query,setQuery,reference,setReference,cropBox,setCropBox,cropping,setCropping,period,setPeriod,searchCamera,setSearchCamera,searched,setSearched,followEvidence,openEvidence};
}
export type IOSTour = ReturnType<typeof useIOSTour>;
