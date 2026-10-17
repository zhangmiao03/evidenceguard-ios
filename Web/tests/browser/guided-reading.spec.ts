import {test,expect} from '@playwright/test';
import {emptyBundle} from '../../src/dashboard/data.mjs';

test('all three guided scenarios finish with baseline, change, uncertainty and a frozen reminder without writes',async({page})=>{
  const writes:string[]=[];page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());});
  await page.goto('/dashboard?view=showcase&tour=manual');
  const guide=page.getByRole('region',{name:'场景逐步导览'}),phone=page.locator('.ios-current'),result=page.locator('.eg-showcase-observation');
  for(const name of ['门口包裹','室内宠物','工作室物品']){
    await page.locator('.eg-showcase-scenes').getByRole('button',{name:new RegExp(name)}).click();
    await guide.getByRole('button',{name:'开始逐步演示',exact:true}).click();
    await guide.getByRole('button',{name:'生成条件与示例选框',exact:true}).click();
    await expect(phone.locator('.ios-selection')).toHaveCount(1);
    await guide.getByRole('button',{name:'查看条件',exact:true}).click();
    await guide.getByRole('button',{name:'确认并开启演示',exact:true}).click();
    await expect(result).toContainText('检查中');
    await guide.getByRole('button',{name:'采样：建立基线',exact:true}).click();
    await expect(result).toContainText('已确认');
    const baselineSource=await phone.locator('.ios-frame img').getAttribute('src');
    await guide.getByRole('button',{name:'采样：条件触发',exact:true}).click();
    await expect(result).toContainText('需关注');
    const changedSource=await phone.locator('.ios-frame img').getAttribute('src');
    expect(changedSource).not.toBe(baselineSource);
    if(name!=='门口包裹'){
      const frame=await phone.locator('.ios-frame-canvas').boundingBox();
      const image=phone.locator('.ios-frame img');
      await expect.poll(()=>image.evaluate((img:HTMLImageElement)=>img.naturalWidth)).toBe(1586);
      const bounds=await image.boundingBox();
      expect(bounds!.width/frame!.width).toBeCloseTo(1,1);
      expect(bounds!.width/bounds!.height).toBeCloseTo(1586/992,1);
      await expect(phone.locator('.ios-scene-map')).toHaveCount(0);
      await expect(phone.locator('.ios-selection')).toHaveCount(1);
      await expect(phone.locator('.ios-frame')).toContainText('AI 场景演示');
    }
    await guide.getByRole('button',{name:'采样：画面遮挡',exact:true}).click();
    await expect(result).toContainText('无法确认');
    await guide.getByRole('button',{name:'查看提醒与追问',exact:true}).click();
    await expect(phone.locator('.ios-message').last()).toContainText('示例主动提醒');
    await phone.locator('.ios-message').last().getByRole('button',{name:'查看提醒画面',exact:true}).click();
    await expect(phone.locator('.ios-frame img')).toHaveAttribute('src',changedSource!);
  }
  await expect(page.getByRole('button',{name:'实拍录像与向量检索 →'})).toBeVisible();
  await page.getByRole('button',{name:'实拍录像与向量检索 →'}).click();
  await expect(page.getByRole('heading',{name:'视频向量库',exact:true})).toBeVisible();
  expect(writes).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('video groups show four windows and twelve image units, keep corpus calls out of searches and show private diagnostics',async({page})=>{
  const bundle:any=emptyBundle(),at=Date.now()/1000;
  const row=(id:string,name:string,data:any,kind='resource')=>({id,name,data,kind,at,traceId:'t'+id,spanId:id,status:'completed',platform:'backend',source:'snapshot',durationMs:200});
  const media={previewUrl:'/dashboard/api/media/demo/'+'b'.repeat(64),kind:'video',provenance:'stored_recording'};
  bundle.records=[row('v','media_recordings',{id:'v',title:'相机实拍验收副本',sourceType:'uploaded',duration:65,media:[media],signatureCompatible:true})];
  for(let i=0;i<4;i++)for(let j=0;j<4;j++)bundle.records.push(row(`s${i}${j}`,'media_video_segments',{id:`s${i}${j}`,clipId:`c${i}`,recordingId:'v',kind:j?'frame':'video',indexVersion:2,start:i*15,end:i*15+20,frameOffsetSeconds:i*15+j*4,dimensions:1024,signatureCompatible:true}));
  bundle.records.push(row('query','vector.search',{privateContent:true,candidateCount:4},'event'),row('p','request.snapshot',{request:{instructions:'Instruction:Compress the image into one word.\nQuery:'}},'prompt'),row('m','embedding_v2',{promptId:'p'},'model'));
  await page.route('**/dashboard/api/info',r=>r.fulfill({json:{mode:'competition',environments:[{id:'demo',title:'手机演示'}]}}));
  await page.route('**/dashboard/api/snapshot?*',r=>r.fulfill({json:bundle}));
  await page.route('**/dashboard/api/media/**',r=>r.fulfill({status:410,body:'expired'}));
  await page.goto('/dashboard?view=vectors');
  await page.getByText('查看全部录像、时间窗口与向量索引',{exact:true}).click();
  await page.getByText('其他检索诊断与建库调用',{exact:true}).click();
  await expect(page.locator('.eg-video-counts')).toContainText('12图像向量');
  await expect(page.getByRole('group',{name:'录像切片时间轴'}).or(page.locator('.eg-clip-tabs')).getByRole('button')).toHaveCount(4);
  await page.locator('.eg-clip-tabs button').nth(2).click();
  await expect(page.locator('.eg-frame-grid article')).toHaveCount(3);
  await page.getByRole('button',{name:'定位原片 38.0 s →',exact:true}).click();
  await expect(page.locator('.eg-video-position')).toContainText('原片定位：38.0 s');
  await expect(page.getByText('媒体副本暂不可用，请刷新数据。',{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'已记录 1 次私有检索'})).toBeVisible();
  await expect(page.getByText('建库输入 · 1 次模型调用',{exact:true})).toBeVisible();
  await expect(page.getByText('当前没有保留查询与返回的检索记录。', {exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
