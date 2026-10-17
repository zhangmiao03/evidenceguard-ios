import test from 'node:test';
import assert from 'node:assert/strict';
import {cloudJSON} from '../src/dashboard/cloud.mjs';

test('cloud discovery is anonymous and distinguishes auth and HTML routing errors',async()=>{
  let request;
  const result=await cloudJSON('/dashboard/api/info',{fetcher:async(p,init)=>{request=init;return new Response('{"mode":"competition"}',{headers:{'Content-Type':'application/json'}});}});
  assert.equal(result.mode,'competition');assert.equal(request.credentials,'omit');assert.equal(request.cache,'no-store');
  assert.equal(request.headers.Authorization,undefined);
  await assert.rejects(cloudJSON('/dashboard/api/info',{fetcher:async()=>new Response('{}',{status:401})}),/401.*无需填写 App 密钥/);
  await assert.rejects(cloudJSON('/dashboard/api/info',{fetcher:async()=>new Response('<html/>',{headers:{'Content-Type':'text/html'}})}),/网页而不是数据/);
});

test('cloud requests abort on deadline and parent cancellation',async()=>{
  const fetcher=async(_p,{signal})=>new Promise((_resolve,reject)=>{if(signal.aborted)reject(Error('aborted'));else signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true});});
  await assert.rejects(cloudJSON('/dashboard/api/info',{fetcher,timeout:5}),/超时/);
  const parent=new AbortController();parent.abort();
  await assert.rejects(cloudJSON('/dashboard/api/info',{fetcher,signal:parent.signal}),/aborted/);
});

test('a slow snapshot can finish after the old twelve-second deadline',async(t)=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let signal;
  const pending=cloudJSON('/dashboard/api/snapshot?environment=demo',{fetcher:async(_p,init)=>{
    signal=init.signal;
    return new Promise((resolve,reject)=>{
      signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true});
      setTimeout(()=>resolve(new Response('{"records":[]}',{headers:{'Content-Type':'application/json'}})),15000);
    });
  }});
  t.mock.timers.tick(15000);
  assert.deepEqual(await pending,{records:[]});
  assert.equal(signal.aborted,false);
  t.mock.timers.tick(60000);
  assert.equal(signal.aborted,false,'successful reads must clear the deadline timer');
});

test('the deadline also cancels a stalled JSON body after successful headers',async(t)=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const pending=cloudJSON('/dashboard/api/snapshot',{fetcher:async(_p,{signal})=>({
    ok:true,status:200,headers:new Headers({'Content-Type':'application/json'}),
    json:()=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true})),
  })});
  const rejected=assert.rejects(pending,/云端读取超时/);
  await Promise.resolve();
  t.mock.timers.tick(30000);
  await rejected;
});
