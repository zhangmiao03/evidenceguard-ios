import {test,expect} from '@playwright/test';
import {emptyBundle} from '../../src/dashboard/data.mjs';

test('default tour progresses without writes, can pause, and reaches all three outcomes',async({page})=>{
  const writes:string[]=[];page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());});
  await page.clock.install();await page.goto('/dashboard?view=showcase');
  await expect(page.getByRole('region',{name:'自动场景导览'})).toBeVisible();
  await page.getByRole('button',{name:'暂停自动导览',exact:true}).click();
  const current=page.locator('.eg-brief-current');
  const before=await current.innerText();await page.clock.runFor(8000);expect(await current.innerText()).toBe(before);
  for(const name of ['门口包裹','室内宠物','工作室物品']){
    await page.locator('.eg-brief-scenes').getByRole('button',{name:new RegExp(name)}).click();
    await expect(current).toContainText('说出需求');
    for(let i=0;i<4;i++)await page.getByRole('button',{name:'下一步',exact:true}).click();
    await expect(current).toContainText('收到提醒与证据');
    await expect(page.locator('.ios-current .ios-message').last()).toContainText('示例主动提醒');
  }
  await page.getByRole('button',{name:'重播',exact:true}).click();await page.clock.runFor(4100);
  await expect(current).toContainText('圈定关注区域');
  expect(writes).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.getByRole('button',{name:'自己操作 App',exact:true}).click();
  await expect(page.locator('.ios-current').getByRole('navigation',{name:'iOS 功能导航'})).toBeVisible();
});

test('reduced motion starts paused and real results explain recall, verification and preprocessing separately',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/dashboard?view=showcase');
  await expect(page.getByRole('button',{name:'继续自动导览'})).toBeVisible();
  const bundle:any=emptyBundle(),at=Date.now()/1000;
  const row=(name:string,data:any)=>({id:name,name,data,kind:'resource',at,traceId:name,spanId:name,status:'completed',platform:'backend',source:'snapshot',durationMs:null});
  bundle.records=[row('media_retrieval_case',{text:'找到水瓶',queryType:'text',source:{title:'已公开实拍录像'},signatureCompatible:true,timings:{embeddingMs:100,recallMs:5,totalMs:500},candidateCount:3,verifiedCount:2,videos:[{id:'c',recordingId:'v',verdict:'uncertain',verificationStatus:'completed',summary:'遮挡，无法确认动作',segmentStart:15,segmentEnd:35,seekSeconds:22}]}),row('media_processing_case',{source:{title:'实拍录像复算'},media:[],depth:{status:'completed'},flow:{status:'skipped',code:'FRAMES_NOT_ADJACENT'},mode:'stored_video_replay'}),row('vision_processing_status',{sameProcess:true,configuration:{depthReady:true,flowReady:true},endpoint_analysesCount:0}),row('media_evidence',{id:'e',reason:'图片里可见一名人员，身份未知',reviewStatus:'completed'})];
  await page.route('**/dashboard/api/info',r=>r.fulfill({json:{mode:'competition',environments:[{id:'demo',title:'手机演示'}]}}));
  await page.route('**/dashboard/api/snapshot?*',r=>r.fulfill({json:bundle}));
  await page.goto('/dashboard?view=vectors');
  await expect(page.getByRole('region',{name:'真实检索案例'})).toContainText('3 个候选窗口');
  await expect(page.locator('.eg-case-verdict')).toContainText('仍无法确认');
  await expect(page.getByRole('status').filter({hasText:'结果定位'})).toContainText('22.0 s');
  await page.goto('/dashboard?view=images');
  await expect(page.getByText('两帧间隔超过 1 秒',{exact:true})).toBeVisible();
  await expect(page.locator('.eg-image-memory-grid')).toContainText('观察结论已保存');
  await expect(page.locator('.eg-image-memory-grid')).toContainText('调用明细未留存关联');
  await expect(page.locator('.eg-processing-case')).toContainText('首尾分析入库 0 次');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
