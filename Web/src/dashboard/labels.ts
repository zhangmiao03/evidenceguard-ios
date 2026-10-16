type Item = {name?:string;kind?:string;at?:number;traceId?:string;data:Record<string,any>};
export const eventLabel=(name:string) => ({chat:'对话模型', 'session.started':'媒体会话建立','session.stopped':'媒体会话停止','session.expired':'媒体会话过期','live.started':'取流开始回执','live.stopped':'取流停止回执','capture.frame_accepted':'画面已上传','agent.finished':'Agent 结束',codex_step:'AI 执行器步骤',image_review:'图片识别',frame_presence:'目标状态判断',video_verify:'视频复核',embedding:'图文 / 视频向量化','vector.search':'录像语义检索','request.snapshot':'模型输入快照','tool.started':'开始调用工具','tool.finished':'工具返回结果','agent.result':'最终回复','context.prepared':'组装上下文','model.output':'模型返回','api.completed':'接口请求完成','api.started':'接口请求开始','agent.started':'Agent 开始','media_sdk_episodes':'设备事件核验','media_sdk_events':'设备事件图片','media_evidence':'图片证据','media_visual_cache':'视觉结果缓存','media_recordings':'录像记录','media_video_segments':'录像切片'}[name] || name);
export const statusLabel=(s:string) => ({observed:'已记录',draft:'待确认草案',running:'执行中',stopped:'已停止',unsupported:'暂不支持',interrupted:'已中断',accepted:'已接收',connected:'已连接',not_configured:'未配置',completed:'已完成',ready:'可检索',valid:'有效',pending:'等待处理',failed:'失败',executor_ok:'执行成功',http_ok:'调用成功',http_error:'调用失败',unknown:'无法确认',matched:'复核匹配',not_matched:'复核不匹配',uncertain:'无法确认',indexing:'建立索引中',queued:'排队中',cancelled:'已取消',snapshot:'已采集',active:'运行中'}[s]||s);
export function deviceLabel(id:any,rows:Item[]=[]){
  if(!id)return '未关联设备';
  const device=rows.find(r=>r.name==='live_devices'&&r.data.id===id)?.data;
  const name=device?.name;
  if(typeof name==='string' && name.length<30 && /[\u4e00-\u9fff\s]/.test(name) && !/[a-f0-9]{16}/i.test(name))return name;
  const index=[...new Set(rows.flatMap(r=>[r.data.cameraId,...(r.name==='live_devices'?[r.data.id]:[])]).filter(Boolean))].sort().indexOf(id)+1;
  const type=device?.model==='T8171'?'云台摄像头':device?.model==='T8214'?'门铃':'摄像头';
  return `${type} ${Math.max(1,index)}`;
}
export function recordLabel(row:Item,rows:Item[]=[]){
  if(row.data.title)return row.data.title;
  if(row.data.query)return `检索：${row.data.query}`;
  if(row.data.cameraId || row.name==='live_devices')return deviceLabel(row.data.cameraId||row.data.id,rows);
  return eventLabel(row.name||'运行记录');
}
export function traceLabel(id:string,rows:Item[]){
  const group=rows.filter(r=>r.traceId===id),query=group.find(r=>r.data.query)?.data.query,model=group.find(r=>r.kind==='model'),first=group[0];
  const label=query?`检索：${query}`:model?eventLabel(model.name||'模型任务'):eventLabel(first?.name||'运行记录');
  return `${label} · ${first?.at?new Date(first.at*1000).toLocaleTimeString('zh-CN',{hour12:false}):'时间未采集'}`;
}
