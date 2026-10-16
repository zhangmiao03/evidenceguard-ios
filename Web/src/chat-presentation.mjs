// Presentation only: preserve original payloads for diagnostics.
export const actions = {
  "devices_list": "查看摄像头列表",
  "device_inspect": "查看摄像头能力",
  "camera_observe": "查看摄像头新画面",
  "camera_events_query": "查看摄像头事件",
  "camera_ptz_step": "移动摄像头",
  "camera_goto_preset": "转到选定位置",
  "camera_set_night_vision": "调整夜视模式",
  "doorbell_light_set": "调整门铃灯光",
  "doorbell_reply_play": "播放门铃回复",
  "camera_record_clip": "录制一段视频",
  "operation_get": "查看操作进度",
  "camera_stop": "停止摄像头操作",
  "device_state_get": "查看设备状态",
  "device_settings_get": "查看摄像头设置",
  "device_settings_set": "调整摄像头设置",
  "camera_events_subscribe": "关注新的摄像头事件",
  "camera_events_unsubscribe": "停止关注摄像头事件",
  "camera_event_get": "查看事件详情",
  "camera_evidence_get": "查看事件资料",
  "camera_evidence_download": "保存事件资料",
  "camera_presets_list": "查看摄像头预置位置",
  "doorbell_replies_list": "查看门铃回复选项",
  "camera_talk_start": "开启对讲",
  "camera_talk_stop": "结束对讲",
  "camera_light_set": "调整摄像头灯光",
  "camera_dual_mode_set": "调整双摄画面",
  "camera_ptz_mode_set": "调整摄像头跟踪模式",
  "camera_panorama_generate": "生成全景画面",
  "operation_cancel": "取消操作",
  "list_camera_capabilities": "查看摄像头能力",
  "request_camera_snapshot": "查看摄像头新画面",
  "list_tasks": "查看任务",
  "get_task_state": "查看任务进度",
  "search_evidence": "查找事件资料",
  "read_stored_image": "查看已保存的图片",
  "search_recordings": "查找并核对录像",
  "draft_visual_skill": "整理守护草案",
  "list_skill_capabilities": "查看可用守护能力",
  "list_camera_events": "查看摄像头事件",
  "request_recheck": "重新查看现场",
  "read_home_report": "整理家庭报告",
  "read_proactive_context": "核对已有记录",
  "read_observation_image": "查看观察图片",
  "gmail_search": "查找邮件",
  "gmail_read": "读取邮件",
  "lark_chats": "查看会话列表",
  "lark_messages": "读取会话消息",
  "read_phone_context": "查看已共享的手机信息"
};
const controls = new Set(["camera_ptz_step", "camera_goto_preset", "camera_set_night_vision", "doorbell_light_set", "doorbell_reply_play", "camera_record_clip", "device_settings_set", "camera_events_subscribe", "camera_events_unsubscribe", "camera_talk_start", "camera_talk_stop", "camera_light_set", "camera_dual_mode_set", "camera_ptz_mode_set", "camera_panorama_generate", "camera_stop", "operation_cancel"]);
export const action = (tool = '') => actions[tool] || '处理请求';
export const progress = (tool = '') => (controls.has(tool) ? '正在准备' : '正在') + action(tool);
export const receipt = (tool = '', status = '') => action(tool) + ' · ' + ({completed:'已收到处理结果',failed:'未完成',unavailable:'暂不可用',unsupported:'暂不支持',awaitingApproval:'等待你确认',queued:'正在等待设备',executing:'正在执行',verifying:'正在核对结果',unknown:'结果尚未确认',cancelled:'已取消'}[status] || '状态待确认');
/** @param {{tool:string, executionState:string}} op */
export function operationStatus(op) {
  return ({awaitingApproval:'等待你确认，确认后才会'+action(op.tool),queued:'正在等待设备响应，尚未开始'+action(op.tool),executing:'正在'+action(op.tool),verifying:'正在确认设备是否已停止，请稍候',completed:'已收到设备处理回执，实际效果仍需核对',failed:'这次操作未完成，请检查设备连接后重试',cancelled:'这次操作已取消'})[op.executionState] || '操作结果尚未确认，请先核对设备状态';
}
/** @param {{tool:string, arguments?:Record<string, unknown>}} op
 * @param {{id:string, label?:string}[]} references */
export function operationDetails(op, deviceName = '所选摄像头', references = []) {
  const a = op.arguments || {}, parts = ['设备：'+chatText(deviceName, '所选摄像头')];
  const direction = {LEFT:'向左',RIGHT:'向右',UP:'向上',DOWN:'向下'}[String(a.direction)];
  if (direction) parts.push('方向：'+direction+'移动一步');
  if (typeof a.duration === 'number' && Number.isFinite(a.duration) && a.duration >= 1 && a.duration <= 300) parts.push('持续 '+Math.trunc(a.duration)+' 秒');
  if (['camera_light_set','doorbell_light_set'].includes(op.tool) && typeof a.enabled === 'boolean') parts.push(a.enabled ? '开启灯光' : '关闭灯光');
  if (op.tool === 'device_settings_set') {
    const field = {ptzSpeed:'转动速度',microphoneEnabled:'麦克风',audioRecordEnabled:'录像声音',statusLED:'状态指示灯'}[String(a.field)] || '所选设置';
    if (typeof a.value === 'boolean') parts.push(field+'：'+(a.value?'开启':'关闭'));
    else if (typeof a.value === 'number' && Number.isFinite(a.value)) parts.push(field+'：'+a.value);
    else parts.push('调整'+field+'，请先核对所选选项');
  }
  const audio = {required:'需要录入声音',forbidden:'不录入声音',allowIfPresent:'设备有音轨时一并录入'}[String(a.audioPolicy)];
  if (op.tool === 'camera_record_clip' && audio) parts.push(audio);
  for (const [key, label] of [['presetRef','位置'],['optionRef','选项'],['modeRef','模式'],['replyRef','门铃回复'],['channelRef','灯光']]) {
    if (typeof a[key] === 'string' && a[key]) parts.push(label+'：'+chatText(references.find(r => r.id === a[key])?.label || '', '已选择，名称暂未同步'));
  }
  if (a.scope === 'persistent') parts.push('该设置会持续生效');
  return parts.join(' · ');
}
export function chatError(raw = '') {
  const value = raw.toLowerCase();
  if (raw === '请选择有效的起止时间，开始时间须早于结束时间。') return raw;
  if (value.includes('输入已保留')) return '这次发送未完成，输入已保留，请重试。';
  if (/timeout|timed out|超时/.test(value)) return '等待响应超时，请稍后重试。';
  if (/offline|离线/.test(value)) return '设备暂时离线，请检查连接后重试。';
  if (/unauthorized|401/.test(value)) return '连接凭证已失效，请到设置重新连接。';
  return '这次处理未完成，请检查连接后重试。';
}
export function chatText(raw = '', fallback = '处理信息已记录，请查看相关状态。') {
  const value = raw.trim();
  if (!value) return fallback;
  try {
    const decoded = JSON.parse(value);
    if (typeof decoded === 'string' && decoded !== value) return chatText(decoded, fallback);
    if (decoded && !Array.isArray(decoded) && typeof decoded === 'object') {
      for (const key of ['text','content','body']) if (typeof decoded[key] === 'string') return chatText(decoded[key], fallback);
    }
    return fallback;
  } catch { /* A normal natural-language answer is not JSON. */ }
  let output = value.replace(/```[\s\S]*?(?:```|$)/g,'').replace(/<(?:tool_call|function_call|analysis)>[\s\S]*?(?:<\/(?:tool_call|function_call|analysis)>|$)/g,'');
  output = output.split(/\r?\n/).filter(line => !/[{}]|^[\[\]]|^[A-Za-z_][A-Za-z0-9_.]*\s*=|^["'].*["'],?$|^["'][A-Za-z_][A-Za-z0-9_]*["']\s*:|^(?:import\s|from\s|def\s|class\s|function\s|const\s|let\s|var\s|return\b|console\.|Traceback|File\s+"|raise\s|Exception|Error:|HTTP\/|curl\s)|=>|\\u[0-9a-fA-F]{4}|<\|[^>]+\|>|\b[A-Za-z_][A-Za-z0-9_]*\([^\n]*\)|\b(?:requestHash|executionState|tool_calls|tool_call_id|executorPlatform|deviceId|operationId)\s*[=:]/.test(line.trim())).join('\n');
  for (const [tool,label] of Object.entries(actions).sort((a,b) => b[0].length-a[0].length)) output = output.replace(new RegExp('\\b'+tool+'\\b','g'),label);
  output = output.replace(/`[^`]*`/g,'').replace(/\b(?:sdk|run|op|executor|proactive)-[A-Za-z0-9-]+\b|\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b(?:\([^\n)]*\))?/g,'相关记录').trim();
  return output || fallback;
}

/** @param {{type:string, payload?:{tool?:string}}} event */
export function eventProgress(event) {
  if (event.type === 'tool_started') return progress(event.payload?.tool);
  if (event.type === 'tool_completed') return '已处理'+action(event.payload?.tool)+'的请求，正在整理结果';
  if (event.type === 'tool_failed') return action(event.payload?.tool)+'未完成，正在核对原因';
  return ({run_queued:'请求已排队',run_started:'正在理解需求',model_started:'正在思考回复',camera_requested:'正在请求摄像头新画面',camera_completed:'已取得新画面',camera_failed:'画面请求未完成',video_search_started:'正在筛选已存录像',video_verification_started:'正在观看候选录像',response_completed:'回复已完成',run_failed:'本次请求未完成',run_cancelled:'已取消'})[event.type] || '正在处理请求';
}
