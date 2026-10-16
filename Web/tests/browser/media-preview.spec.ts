import {test,expect} from '@playwright/test';
import {sampleBundle} from '../../src/dashboard/data.mjs';
import {readFileSync} from 'node:fs';
for (const executor of ['http','codex'] as const) test(`${executor}: actual media references, model inputs and retrieval results are inspectable without leaking IDs or fetching arbitrary URLs`,async({page})=>{
 const bundle:any=sampleBundle(),capture={version:1,mode:'full_redacted',truncated:false};
 const image='/dashboard/api/media/demo/'+'a'.repeat(64),video='/dashboard/api/media/demo/'+'b'.repeat(64);
 const media={kind:'image',previewUrl:image,provenance:executor==='codex'?'executor_input':'exact_model_input'};
 const row=(id:string,name:string,data:any,kind='resource')=>({id,name,data:{...data,...(executor==='codex'&&['model','prompt'].includes(kind)?{transport:'codex_app_server',inputBoundary:'host_to_codex'}:{})},kind,at:1000,traceId:'test-task',spanId:id,platform:'backend',source:'snapshot',status:'completed',durationMs:100});
 bundle.records=[row('device','live_devices',{id:'opaque-camera-8fba5847e9974a',model:'T8171',name:'opaque-91746323cfe6b5'}),
  row('prompt','request.snapshot',{capture,inputMedia:[media,{kind:'image',previewUrl:'https://untrusted.invalid/image'}],request:{messages:[{role:'user',content:'请描述这张图'}]}},'prompt'),
  row('model',executor==='codex'?'codex_step':'image_review',{capture,promptId:'prompt',model:'doubao-test',content:{response:executor==='codex'?{content:'{"visible":"真实调用结果测试","uncertainties":"单帧限制"}'}:{choices:[{message:{content:'{"visible":"真实调用结果测试","uncertainties":"单帧限制"}'}}]}}},'model'),
  row('episode','media_sdk_episodes',{cameraId:'opaque-camera-8fba5847e9974a',media:[media],review:{visible:'设备来源测试画面'}}),
  row('recording','media_recordings',{id:'recording',title:'检索测试录像',sourceType:'synthetic_review',media:[{kind:'video',previewUrl:video}]}),
  row('search','vector.search',{capture,query:'包裹何时离开区域',content:{arguments:{query:'包裹何时离开区域'},result:{status:'completed',candidateCount:1,videos:[{recordingId:'recording',title:'检索测试录像',similarity:.73456,verdict:'uncertain',summary:'遮挡期间无法确认拿取动作',segmentStart:0,segmentEnd:10,seekSeconds:4}]}}},'event')];
 const outside:string[]=[];page.on('request',r=>{if(r.url().includes('untrusted.invalid'))outside.push(r.url());});
 await page.route('**/dashboard/api/media/demo/*',r=>r.fulfill({contentType:'image/jpeg',body:readFileSync(new URL('../../src/dashboard/assets/PetThumb.jpg',import.meta.url))}));
 await page.goto('/dashboard?view=images');
 await page.getByLabel('导入追踪 JSON').setInputFiles({name:'media.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))});
 await page.getByText('视觉分析、事件核验与模型实际输入',{exact:true}).click();
 await expect(page.getByText('真实调用结果测试',{exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'云台摄像头 1'})).toBeVisible();
 await page.getByRole('button',{name:'豆包识图实际输入 · 放大图片 1'}).click();
 await expect(page.locator('dialog[open] img')).toHaveAttribute('src',image);
 await page.getByRole('button',{name:'关闭图片预览'}).click();
 await page.getByRole('button',{name:'查看上传图片、提示词与完整输出'}).click();
 await expect(page.getByRole('dialog').getByRole('img').first()).toBeVisible();
 await expect(page.getByRole('dialog')).toContainText('请描述这张图');
 if (executor==='codex') await expect(page.getByRole('dialog')).toContainText('本次传给 AI 执行器的媒体');
 await page.getByRole('button',{name:'关闭详情'}).click();
 await page.getByRole('navigation',{name:'Dashboard 页面'}).getByRole('button',{name:'视频向量库'}).click();
 await expect(page.getByText('“包裹何时离开区域”')).toBeVisible();
 await expect(page.getByText('0.7346',{exact:true})).toBeVisible();
 await expect(page.getByText('遮挡期间无法确认拿取动作')).toBeVisible();
 await expect(page.locator('.eg-search-candidate a[download="录像.mp4"]')).toHaveAttribute('href',video);
 await expect(page.locator('.eg-search-candidate')).toContainText('媒体副本暂不可用');
 await page.getByRole('button',{name:'图片向量输入',exact:true}).click();
 await expect(page.getByText(/当前没有可公开展示的图片查询/)).toBeVisible();
 expect(outside).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
