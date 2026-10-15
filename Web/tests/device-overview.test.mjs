import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeDevices } from '../src/device-overview.mjs';
test('event-only devices remain visible but cannot invent a live identity', () => {
  assert.deepEqual(mergeDevices([{id:'one', name:'Doorbell', connection:'event_only', sn:'untrusted-event-sn'}], []),
    [{id:'one', name:'Doorbell', connection:'event_only', sn:''}]);
});
test('live identity and state override event metadata without duplicating cameras', () => {
  const result = mergeDevices([{id:'one',name:'Doorbell',connection:'event_only'}, {id:'two',name:'Room'}],
    [{id:'one',name:'Front',sn:'T8214REAL',connection:'online'}]);
  assert.equal(result.length,2); assert.equal(result[0].sn,'T8214REAL'); assert.equal(result[0].connection,'online');
  assert.equal(result[1].sn,'');
});
