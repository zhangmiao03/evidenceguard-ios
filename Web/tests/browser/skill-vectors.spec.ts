import {test,expect} from '@playwright/test';
import {emptyBundle} from '../../src/dashboard/data.mjs';

const url='/dashboard/api/media/demo/'+'a'.repeat(64);
const media={kind:'image',previewUrl:url,assetId:'a'.repeat(64),mime:'image/png',provenance:'indexed_frame'};
const row=(name:string,data:any,id=name)=>({id,name,data,kind:'resource',at:Date.now()/1000,traceId:id,spanId:id,status:'completed',platform:'backend',source:'snapshot',durationMs:null});
async function setup(page:any,records:any[]){
  const bundle:any=emptyBundle();bundle.records=records;
  await page.route('**/dashboard/api/info', (r:any)=>r.fulfill({json:{mode:'competition',environments:[{id:'demo',title:'比赛演示'}]}}));
  await page.route('**/dashboard/api/snapshot?*',(r:any)=>r.fulfill({json:bundle}));
  await page.route('**/dashboard/api/media/**',(r:any)=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAE0lEQVR4nGPMm9bDAANMcBZeDgBPBgGYhGdYuwAAAABJRU5ErkJggg==','base64')}));
}
test('custom Skill shows actual revisions, keeps unchanged conditions and never activates hardware',async({page})=>{
  const writes:string[]=[],errors:string[]=[];page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());});page.on('pageerror',e=>errors.push(e.message));
  const plan={title:'水瓶离开提醒',target:'红盖水瓶',selection:'object',trigger:'leaves',confirmationSeconds:30,completion:'once'};
  const revisions=[{revision:1,input:'看住红盖水瓶，离开区域后观察30秒，只提醒一次。',plan,durationMs:500,canActivate:false},{revision:2,input:'改成45秒，持续提醒，其余保持。',plan:{...plan,confirmationSeconds:45,completion:'continuous'},durationMs:450,canActivate:false}];
  await setup(page,[row('media_skill_generation_case',{model:'test-model',referenceMedia:[media],referenceOffset:44,revisions})]);
  await page.goto('/dashboard?view=tasks');
  await expect(page.getByRole('button',{name:'自定义 Skill',exact:false})).toBeVisible();
  const panel=page.getByRole('region',{name:'真实 Skill 生成与修改'});
  await expect(panel).toContainText('本次改动 2 项，其余规则保留');
  await expect(panel.locator('.eg-skill-fields')).toContainText('45 秒');
  await expect(panel).toContainText('未启动摄像头');
  await panel.getByRole('button',{name:'首次生成',exact:true}).click();
  await expect(panel.locator('.eg-skill-fields')).toContainText('30 秒');
  await expect(panel.locator('.eg-skill-fields')).toContainText('只提醒一次');
  await expect(panel.locator('.eg-skill-fields')).toContainText('红盖水瓶');
  await expect(panel.locator('.changed')).toHaveCount(0);
  await panel.getByRole('button',{name:'继续修改 · 第 2 版',exact:true}).click();
  await expect(panel.locator('.changed')).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect(writes).toEqual([]);expect(errors).toEqual([]);
});

test('vector retrieval shows matching frames and ranks, with clickable event times and honest pending candidates',async({page})=>{
  const writes:string[]=[],errors:string[]=[];page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());});page.on('pageerror',e=>errors.push(e.message));
  const first={id:'clip',recordingId:'v',segmentStart:30,segmentEnd:50,seekSeconds:41,verdict:'matched',summary:'一只手拿起水瓶',rank:1,ranking:{video:{rank:2,cosine:.3},frame:{rank:1,cosine:.4}},events:[{start:44,end:45,description:'水瓶再次被移动'}]};
  const second={id:'unverified',recordingId:'v',segmentStart:0,segmentEnd:20,seekSeconds:0,verdict:'candidate',summary:'尚未复核',rank:2};
  const data={text:'找到水瓶',queryType:'text',indexSignature:'sig',signatureCompatible:true,source:{recordingId:'v',title:'公开录像',duration:65},timings:{totalMs:500},candidateCount:2,verifiedCount:1,videos:[first,second]};
  const frame={kind:'frame',recordingId:'v',clipId:'clip',signature:'sig',frameOffsetSeconds:40,media:[media]};
  await setup(page,[row('media_retrieval_case',data),row('media_retrieval_case',{...data,queryType:'image_text',referenceMedia:[media]},'image-case'),row('media_video_segments',frame)]);
  await page.goto('/dashboard?view=vectors');
  const panel=page.getByRole('region',{name:'真实检索案例'});
  await expect(panel.locator('.eg-recall-outcome>b')).toHaveText('1');
  await expect(panel.getByRole('img',{name:'候选 1 的索引帧 40.0 s'})).toBeVisible();
  await expect(panel.locator('.eg-recall-card').first()).toContainText('视频排名 2 · 图像排名 1 → 融合排名 1');
  await panel.getByRole('button',{name:/水瓶再次被移动/}).click();
  await expect(panel.getByRole('status')).toContainText('44.0 s');
  await panel.getByRole('button',{name:'定位索引帧 40.0 s'}).click();await expect(panel.getByRole('status')).toContainText('40.0 s');
  await panel.locator('.eg-recall-card').nth(1).click();await expect(panel.locator('.eg-case-verdict')).toContainText('尚未复核');
  await expect(panel.locator('.eg-recall-strip img')).toHaveCount(0);
  await panel.getByRole('button',{name:'图片 + 文字 · 案例 2'}).click();
  await expect(panel.locator('.eg-query-image img')).toBeVisible();await expect(panel.getByRole('status')).toContainText('41.0 s');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect(writes).toEqual([]);expect(errors).toEqual([]);
});
