import test from 'node:test';
import assert from 'node:assert/strict';
import {guardModelCall} from '../src/dashboard/guard-link.mjs';
test('guard evidence links only explicit committed receipt and never discarded, private or nearby calls',()=>{
  const evidence={id:'evidence',guardRunId:'guard-1'};
  const finish={name:'guard.finished',traceId:'guard-1',data:{disposition:'committed',alertPublished:true,evidenceId:'evidence'}};
  const model={kind:'model',traceId:'guard-1',data:{}};
  assert.equal(guardModelCall(evidence,[finish,model]),model);
  for(const patch of [{disposition:'discarded'},{evidenceId:'other'},{alertPublished:false},{privateContent:true}]){
    assert.equal(guardModelCall(evidence,[{...finish,data:{...finish.data,...patch}},model]),null);
  }
  assert.equal(guardModelCall(evidence,[finish,{...model,traceId:'guard-other'}]),null);
  assert.equal(guardModelCall(evidence,[finish,{...model,data:{privateContent:true}}]),null);
  assert.equal(guardModelCall({id:'evidence'},[finish,model]),null);
});
