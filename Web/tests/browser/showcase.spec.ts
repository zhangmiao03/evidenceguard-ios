import {test,expect} from '@playwright/test';
import {sampleBundle} from '../../src/dashboard/data.mjs';

test('auth routing failure is visible, automatically recovers, and stale filters can be cleared',async({page})=>{
  let requests=0;
  await page.route('**/dashboard/api/info',r=>r.fulfill(++requests<2?{status:401,contentType:'application/json',body:'{}'}:{contentType:'application/json',body:JSON.stringify({mode:'competition',environments:[{id:'demo',title:'手机演示'}]})}));
  await page.route('**/dashboard/api/snapshot?*',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(sampleBundle())}));
  await page.goto('/dashboard');
  await expect(page.getByText(/数据接口返回 401/)).toBeVisible();
  await expect(page.getByRole('button',{name:'刷新云端数据'})).toBeVisible({timeout:8000});
  await page.locator('.judge-filter-fold > summary').click();
  await page.getByPlaceholder('Trace / 模型 / 事件 / 状态').fill('no-such-record');
  await expect(page.getByRole('button',{name:'清除全部筛选'})).toBeVisible();
  await page.getByRole('button',{name:'清除全部筛选'}).click();
  await expect(page.getByPlaceholder('Trace / 模型 / 事件 / 状态')).toHaveValue('');
});

test('image results and vector segments retain provenance and readable details',async({page})=>{
  const bundle:any=sampleBundle();
  const resource=(id:string,name:string,data:any)=>({id,kind:'resource',name,traceId:'snapshot:'+id,spanId:id,at:1000,source:'snapshot',platform:'backend',status:'snapshot',durationMs:null,data});
  bundle.records=[resource('ep','media_sdk_episodes',{id:'ep',cameraId:'camera-a',status:'completed',review:{review:{visible:'纸箱位于地垫内',uncertainties:'无法判断画外情况'}}}),resource('v','media_recordings',{id:'v',title:'测试录像',cameraId:'camera-a',sourceType:'synthetic_review',embeddingModel:'test-embedding',duration:10,status:'ready',signatureCompatible:true}),resource('s','media_video_segments',{id:'s',indexVersion:2,kind:'frame',frameOffsetSeconds:1,recordingId:'v',start:0,end:10,dimensions:1024,norm:1,normalized:true,signatureCompatible:true,status:'valid',vectorPreview:[.02,-.04]})];
  bundle.coverage={mediaIndex:{status:'connected',sampledAt:1000,currentSignature:'sig',tables:{video_segments:{total:1}},invalidVectorsInSample:0}};
  await page.goto('/dashboard?view=images');
  await page.getByLabel('导入追踪 JSON').setInputFiles({name:'media.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))});
  await page.getByText('视觉分析、事件核验与模型实际输入',{exact:true}).click();
  await expect(page.getByText('纸箱位于地垫内',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'查看完整结果与来源'}).click();
  await expect(page.getByRole('dialog')).toContainText('无法判断画外情况');
  await page.getByRole('button',{name:'关闭详情'}).click();
  await page.getByRole('navigation',{name:'Dashboard 页面'}).getByRole('button',{name:'视频向量库'}).click();
  await expect(page.locator('.eg-media-indexgrid')).toContainText('合成测试素材 · 真实入库');
  await page.getByText('本窗口向量详情 · 1 条',{exact:true}).click();
  await expect(page.getByText('1024 维',{exact:true})).toBeVisible();
  await expect(page.locator('.eg-media-vector')).toContainText('关键帧向量');
  await expect(page.locator('.eg-media-vector')).toContainText('v2 视频 / 关键帧双路索引');
  await page.getByRole('button',{name:'展开向量、签名与校验摘要'}).click();
  await expect(page.getByRole('dialog')).toContainText('vectorPreview');
  await page.getByRole('button',{name:'关闭详情'}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
