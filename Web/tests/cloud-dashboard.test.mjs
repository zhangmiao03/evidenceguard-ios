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
