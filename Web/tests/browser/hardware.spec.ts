import { test, expect } from '@playwright/test';

test('event-only camera, millisecond timeline and native confirmation are usable on desktop/mobile', async ({page}) => {
  const camera={id:'sdk-event-only',name:'客厅云台',model:'T8171',connection:'event_only',capabilities:{},evidence:'事件'};
  const op:any={id:'op-test',deviceId:camera.id,taskId:'device:'+camera.id,tool:'device_settings_set',requestHash:'exact-request',
    executionState:'awaitingApproval',executorPlatform:'iOS',requestedPlatform:'Web',arguments:{field:'statusLED',value:true},sdkUsed:false};
  const confirmations:any[]=[]; const errors:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let json:any=[];
    if(path==='/api/bootstrap') json={skills:[],cameras:[camera],evidence:[],agent:{ready:false,provider:'test'},personal:{revision:0,preferences:{},memories:[],inbox:[],messages:[]}};
    if(path==='/api/agent/conversations/main') json={id:'main-test',title:'助手',kind:'main',updatedAt:1,unreadCount:0};
    if(path==='/api/sdk/events') json={events:[{id:'event-1',cameraId:camera.id,deviceName:camera.name,startMs:1791766800000,endMs:1791766801000,
      detectionType:'人物',hasVideo:true,imageUrl:null,reviewStatus:'metadata_only',reason:'仅保存元数据',sourceType:'official_sdk'}],truncated:false,continuousCoverage:false};
    if(path==='/api/hardware/snapshot') json={devices:[{id:camera.id,label:camera.name,executorPlatform:'iOS',executorOnline:true,capabilityRevision:'revision',viewRevision:1,settingsRevision:0,
      privacy:'off',routes:{device_settings_set:{ready:true,sdkMapping:'test'}},validationResults:[]}],operations:[op],tools:[]};
    if(path==='/api/hardware/confirmations') { const body=route.request().postDataJSON(); confirmations.push(body); op.executionState='queued'; json=op; }
    await route.fulfill({json});
  });
  await page.goto('/');
  await page.getByLabel('团队访问令牌',{exact:true}).fill('synthetic-team-token');
  await page.getByRole('button',{name:'进入工作台 →'}).click();
  await expect(page.getByText('云端已连接',{exact:true}).first()).toBeVisible();
  await page.getByRole('button',{name:'摄像头 Skill',exact:false}).first().click();
  await expect(page.getByText('事件已登记',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'客厅云台',exact:false}).click();
  await expect(page.getByText('本条无图片',{exact:true})).toBeVisible();
  await expect(page.getByText('仅设备报告，暂无可核验图片',{exact:false})).toBeVisible();
  await expect(page.getByText('SDK 标记有录像，尚未下载',{exact:false})).toBeVisible();
  await expect(page.getByText('设备事件时间 2026',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'确认这次操作'})).toBeVisible();
  await page.getByRole('button',{name:'确认这次操作'}).click();
  await expect(page.getByText('等待执行端领取 · 执行端 iOS')).toBeVisible();
  expect(confirmations).toEqual([{operationId:'op-test',requestHash:'exact-request',decision:'approve'}]);
  expect(errors).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});

test('Web host polls stop during observation, retries only receipts, and drains with the original team credential',async ({page})=>{
  const calls:{path:string;body:any;auth?:string;executor?:string}[]=[];
  let claimed=0, receipts=0, release!:()=>void;
  const observation=new Promise<void>(resolve=>{release=resolve;});
  const op={id:'op-observe',tool:'camera_observe',deviceId:'sdk-test',executorPlatform:'Web',leaseToken:'synthetic-lease'};
  await page.route('**/sdk/index.js',route=>route.fulfill({contentType:'application/javascript',body:'/* explicit test artifact */'}));
  await page.route('**/api/**',async route=>{
    const request=route.request(), path=new URL(request.url()).pathname;
    const body=request.postDataJSON();
    calls.push({path,body,auth:request.headers().authorization,executor:request.headers()['x-eg-executor-token']});
    let json:any={};
    if(path==='/api/hardware/executors') json={executorId:'executor-test',token:'synthetic-executor',deviceId:'sdk-test'};
    if(path.endsWith('/claim')) json=claimed++===0?{command:'execute',operation:op}:claimed===2?{command:'stop',operation:op}:{command:null};
    if(path.endsWith('/observe')) { await observation; json={executionState:'cancelled'}; }
    if(path.endsWith('/result')) {
      if (receipts++ === 0) { await route.abort('failed'); return; }
      release(); json={executionState:'cancelled'};
    }
    await route.fulfill({json});
  });
  await page.goto('/');
  await page.evaluate(async()=>{
    const {api}=await import('/src/api.ts');
    const {WebToolExecutor}=await import('/src/hardware-tools.ts');
    api.token='original-test-team';
    const host=new WebToolExecutor({id:'sdk-test',sn:'T8171TEST',model:'T8171',name:'test',connection:'online',capabilities:{},evidence:''},
      {id:'live-test',deviceId:'sdk-test',token:'synthetic-media'},()=>{});
    (window as any).__hardwareTestHost=host;
    host.start(); api.token='replacement-test-team';
  });
  await expect.poll(()=>calls.filter(c=>c.path.endsWith('/result')).length).toBe(2);
  await page.evaluate(async()=>{ await (window as any).__hardwareTestHost.stop(); });
  const registration=calls.find(c=>c.path==='/api/hardware/executors')!;
  expect(registration.body.privacy).toBe('unknown');
  expect(Object.keys(registration.body.routes)).toEqual(['camera_observe']);
  expect(calls.find(c=>c.path.endsWith('/result'))!.body.status).toBe('stopped');
  expect(calls.filter(c=>c.path.endsWith('/observe')).length).toBe(1);
  const replayed = calls.filter(c=>c.path.endsWith('/result'));
  expect(replayed[0].body).toEqual(replayed[1].body);
  for(const call of calls.filter(c=>c.path.includes('/api/hardware/'))) expect(call.auth).toBe('Bearer original-test-team');
  expect(calls.find(c=>c.path.endsWith('/disconnect'))!.executor).toBe('synthetic-executor');
});
