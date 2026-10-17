import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {chatText, chatError, action, progress, receipt, operationStatus, operationDetails, actions} from '../src/chat-presentation.mjs';
const cases = JSON.parse(readFileSync(new URL('../../Tests/ChatPresentation/cases.json',import.meta.url)));
test('assistant text hides technical payloads and preserves natural language (shared with iOS)', () => {
  for(const c of cases) assert.equal(chatText(c.input),c.expected);
});
test('operation phases do not claim movement before execution or physical success from receipts', () => {
  const op = {tool:'camera_ptz_step',executionState:'awaitingApproval',arguments:{direction:'LEFT'}};
  assert.match(operationStatus(op),/^等待你确认/);
  assert.match(operationStatus({...op,executionState:'queued'}),/尚未开始/);
  assert.equal(operationStatus({...op,executionState:'executing'}),'正在移动摄像头');
  assert.match(operationStatus({...op,executionState:'completed'}),/仍需核对/);
  assert.match(operationStatus({...op,executionState:'future_state'}),/尚未确认/);
  assert.match(operationDetails(op,'客厅'),/设备：客厅 · 方向：向左移动一步/);
  assert.match(operationDetails({tool:'camera_record_clip',arguments:{duration:10,audioPolicy:'forbidden'}}),/持续 10 秒 · 不录入声音/);
  assert.match(operationDetails({...op,arguments:{direction:'LEFT',durationMs:350}}),/移动 0.35 秒后停止/);
  assert.equal(action('sample_camera_vision'),'取新画面并分析');
  assert.equal(progress('camera_ptz_step'),'正在准备移动摄像头');
  assert.doesNotMatch(receipt('future_tool','future_state'),/future/);
  assert.doesNotMatch(chatError('TimeoutError requestHash=secret'),/secret|TimeoutError/);
});
test('every registered hardware tool has a user-facing action', () => {
 const catalog = JSON.parse(readFileSync(new URL('../../Cloud/server/evidenceguard/hardware_tools/contracts/camera-tools/tools.json',import.meta.url)));
 const tools = Array.isArray(catalog) ? catalog : catalog.tools;
 for(const tool of tools) { assert.ok(actions[tool.name],tool.name); assert.notEqual(action(tool.name),tool.name); }
});
