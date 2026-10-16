import {test,expect} from '@playwright/test';
import {sampleBundle} from '../../src/dashboard/data.mjs';

test('private SeedLite calls remain inspectable without publishing analysis bodies',async({page})=>{
  const bundle:any=sampleBundle();
  bundle.records=[{id:'endpoint-call',kind:'model',name:'vision.endpoints',traceId:'endpoint-run',spanId:'endpoint-span',at:1000,source:'local',platform:'backend',status:'http_ok',durationMs:432,
    data:{privateContent:true,model:'doubao-seed-2-1-lite-260915',operation:'vision.endpoints'}}];
  await page.goto('/dashboard?view=images');
  await page.getByLabel('导入追踪 JSON').setInputFiles({name:'endpoints.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))});
  await page.getByText('视觉分析、事件核验与模型实际输入',{exact:true}).click();
  const calls=page.locator('.eg-vision-calls');
  await expect(calls).toContainText('SeedLite 首尾图分析');
  await expect(calls).toContainText('doubao-seed-2-1-lite-260915');
  await expect(calls).toContainText('结果正文请在 App 中查看');
  await expect(calls.locator('img')).toHaveCount(0);
  await page.getByRole('button',{name:'查看上传图片、提示词与完整输出'}).click();
  await expect(page.getByRole('dialog')).toContainText('私有查询');
});
