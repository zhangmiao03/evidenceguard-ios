import doorPhoto from './assets/DoorScene.jpg';
import petPhoto from './assets/PetThumb.jpg';
import studioPhoto from './assets/BoxThumb.jpg';
import takenPhoto from './assets/EvidenceScene.jpg';

// Design assets and deterministic examples only. Never bind this tour to an API.
export const tourScenarios = [
  {id:'door',label:'门口包裹',camera:'前门门铃',device:'doorbell',model:'T8214',title:'包裹离区提醒',target:'纸箱',area:'门口地垫',trigger:'离开区域',selection:'object',prompt:'帮我看住门口的包裹，离开地垫时提醒我；看不清时不要判断。',photo:doorPhoto,changedPhoto:takenPhoto,present:'包裹仍在地垫内',changed:'包裹已不在关注区域',memory:'包裹离开门口地垫时提醒我，画面不清楚时先不要判断。',box:{x:.4,y:.45,width:.36,height:.44}},
  {id:'pet',label:'室内宠物',camera:'客厅云台',device:'indoor',model:'T8171',title:'宠物进入沙发区域',target:'狗',area:'沙发前方',trigger:'进入区域',selection:'category',prompt:'狗进入沙发前方区域时提醒我，先连续观察十五秒。',photo:petPhoto,changedPhoto:petPhoto,present:'触发前基线：关注区域内没有狗',changed:'狗进入了关注区域',memory:'关注宠物在客厅的活动，描述可见情况，不推断健康状态。',box:{x:.15,y:.32,width:.7,height:.58}},
  {id:'studio',label:'工作室物品',camera:'客厅云台',device:'indoor',model:'T8171',title:'工作台物品看护',target:'工作台上的相机',area:'工作台',trigger:'离开区域',selection:'object',prompt:'工作台上的相机离开原来的位置时提醒我。',photo:studioPhoto,changedPhoto:studioPhoto,present:'关注物品仍在工作台上',changed:'关注物品不在原来区域',memory:'重要物品变化时附上证据，不推断拿取者身份。',box:{x:.3,y:.28,width:.42,height:.61}},
] as const;
export type TourScene = typeof tourScenarios[number];
export type TourCondition = 'baseline'|'changed'|'unknown';
export type TourBox = {x:number;y:number;width:number;height:number};
export const tourTabs = [{title:'助手',icon:'chat'},{title:'摄像头守护',icon:'camera'},{title:'设备',icon:'devices'},{title:'记忆',icon:'memory'},{title:'我的',icon:'profile'}];
export const tourCameras = [{id:'doorbell',name:'前门门铃',model:'T8214'},{id:'indoor',name:'客厅云台',model:'T8171'}];

export function selectionBox(a:{x:number;y:number},b:{x:number;y:number}):TourBox|null {
  const clamp=(v:number)=>Math.min(1,Math.max(0,v));
  const x1=clamp(a.x),x2=clamp(b.x),y1=clamp(a.y),y2=clamp(b.y);
  return Math.abs(x1-x2)<.02||Math.abs(y1-y2)<.02?null:{x:Math.min(x1,x2),y:Math.min(y1,y2),width:Math.abs(x1-x2),height:Math.abs(y1-y2)};
}
