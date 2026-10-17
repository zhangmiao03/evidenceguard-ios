import {test,expect} from '@playwright/test';
import {emptyBundle} from '../../src/dashboard/data.mjs';

test('per-check diagnostics show exact flow input, original prompt, outcome and truthful replay boundary',async({page})=>{
  const bundle:any=emptyBundle(),at=Date.now()/1000,traceId='guard-fixture';
  let seq=0;
  const event=(name:string,data:any={},status='completed',kind='event')=>({id:name+seq,name,kind,at,
    traceId,spanId:'span',platform:'backend',source:'local',status,durationMs:123,data:{...data,guardSequence:++seq}});
  const img=(label:string,i:number)=>({label,kind:'image',mime:'image/png',status:'available',
    provenance:'exact_model_input',previewUrl:'/dashboard/api/media/demo/'+String(i).repeat(64)});
  bundle.records=[
    event('vision_processing_status',{guardRunCoverage:'per_run_v1'},'completed','resource'),
    event('guard.started',{mode:'stored_video_replay',title:'隔离测试录像'}),
    event('guard.capture',{frame:{sourceType:'stored_video_replay'}}),
    event('guard.preprocessing',{},'started'),
    event('guard.preprocessing',{depth:{status:'completed'},flow:{status:'completed',quality:'diagnostic_checks_passed_not_ground_truth'}}),
    event('request.snapshot',{contentCapture:true,capture:{version:1,mode:'full_redacted'},
      request:{messages:[{role:'system',content:'EXACT GUARD PROMPT'}]},inputMedia:[
        img('用户确认的参考画面 · 全图',1),img('参考局部',2),img('当前采样画面 · 全图',3),img('当前局部',4),
        img('a 同帧相对逆深度',5),img('b 同帧相对逆深度',6),img('光流诊断',7)]},'completed','prompt'),
    event('guard.observe',{model:'test-model',content:{response:{choices:[{message:{content:'EXACT MODEL RESPONSE'}}]}}},'http_ok','model'),
    event('guard.finished',{mode:'stored_video_replay',disposition:'replay_only',judgment:{state:'unknown',reason:'无法确认目标'},alertPublished:false}),
  ];
  const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO1sAAAAASUVORK5CYII=','base64');
  await page.route('**/dashboard/api/media/**',r=>r.fulfill({body:pixel,contentType:'image/png'}));
  await page.route('**/dashboard/api/info',r=>r.fulfill({json:{mode:'competition',environments:[{id:'demo',title:'手机演示'}]}}));
  await page.route('**/dashboard/api/snapshot?*',r=>r.fulfill({json:bundle}));
  await page.goto('/dashboard?view=images');
  const section=page.getByRole('region',{name:'守护逐次处理记录'});
  await expect(section).toContainText('尚无实时守护记录');
  await expect(section).toContainText('保存视频验证 1 次');
  await expect(section).toContainText('无法确认');
  await expect(section).toContainText('光流通过诊断检查');
  await expect(section.locator('img[alt="本次提交的光流"]')).toBeVisible();
  await section.getByText(/提示词、模型正文与每步诊断/).click();
  await section.getByRole('button',{name:/查看本次提示词与模型输入/}).click();
  await expect(page.getByRole('dialog',{name:'追踪详情'})).toContainText('EXACT GUARD PROMPT');
  await page.getByRole('button',{name:'关闭详情 ×',exact:true}).click();
  await section.getByRole('button',{name:/查看模型返回正文/}).click();
  await expect(page.getByRole('dialog',{name:'追踪详情'})).toContainText('EXACT MODEL RESPONSE');
  await page.getByRole('button',{name:'关闭详情 ×',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('capture failure and discarded results do not appear as successful guard alerts',async({page})=>{
  const bundle:any=emptyBundle(),at=Date.now()/1000;
  const row=(name:string,status:string,data:any)=>({id:name,name,kind:'event',at,traceId:'guard-failed',
    spanId:'s',platform:'backend',source:'local',status,data});
  bundle.records=[
    row('guard.started','started',{mode:'live_guard'}),
    row('guard.capture','failed',{}),
    row('guard.preprocessing','skipped',{code:'CAPTURE_UNAVAILABLE',depth:{status:'skipped'},flow:{status:'skipped'}}),
    row('guard.finished','completed',{disposition:'discarded',judgment:{state:'outside',reason:'old result'}}),
  ];
  await page.route('**/dashboard/api/info',r=>r.fulfill({json:{mode:'competition',environments:[{id:'demo',title:'手机演示'}]}}));
  await page.route('**/dashboard/api/snapshot?*',r=>r.fulfill({json:bundle}));
  await page.goto('/dashboard?view=images');
  const section=page.getByRole('region',{name:'守护逐次处理记录'});
  await expect(section).toContainText('结果已丢弃');
  await expect(section).toContainText('本次没有获得设备画面');
  await expect(section).not.toContainText('本次已生成提醒证据');
  await expect(section).not.toContainText('尚无实时守护记录');
});
