import { test, expect } from "@playwright/test";
import { sampleBundle } from "../../src/dashboard/data.mjs";

test("offline dashboard: import, trace, model prompt, filter and export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", { name: "运行总览", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("尚未加载数据", { exact: true })).toBeVisible();
  await page
    .getByLabel("导入追踪 JSON")
    .setInputFiles({
      name: "sample.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(sampleBundle())),
    });
  await expect(page.getByText("模拟数据 · 不用于业务结论")).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Agent 与模型" })
    .click();
  await page
    .locator(".eg-ops-row-link")
    .filter({ hasText: "demo-vision-model" })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "查看关联提示词" }).click();
  await expect(page.getByRole("dialog").locator("pre")).toContainText(
    "这是模拟提示词",
  );
  await page.getByRole("button", { name: "查看完整 Trace" }).click();
  await expect(
    page.getByRole("heading", { name: "Trace 时间线" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭详情" }).click();
  await page.getByPlaceholder("Trace / 模型 / 事件 / 状态").fill("http_error");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ 导出", exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toContain("SYNTHETIC");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("invalid import preserves current data and missing backend remains offline", async ({
  page,
}) => {
  await page.route("**/api/ops/snapshot", (r) =>
    r.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "本地追踪未启用" }),
    }),
  );
  await page.goto("/dashboard");
  await page
    .getByLabel("导入追踪 JSON")
    .setInputFiles({
      name: "bad.json",
      mimeType: "application/json",
      buffer: Buffer.from('{"schemaVersion":"unknown"}'),
    });
  await expect(page.getByRole("alert")).toContainText("不支持");
  await page.getByRole("button", { name: "连接本地服务" }).click();
  await page.getByRole("button", { name: "读取同源本地 API" }).click();
  await expect(page.getByRole("alert")).toContainText("本地追踪未启用");
  await expect(page.getByText("尚未加载数据", { exact: true })).toBeVisible();
});

test("all dashboard pages render without horizontal page overflow", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await page
    .getByLabel("导入追踪 JSON")
    .setInputFiles({
      name: "sample.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(sampleBundle())),
    });
  for (const name of [
    "设备与取流",
    "对话与 Trace",
    "提示词与上下文",
    "Skill 与任务",
    "证据与录像",
    "质量与试跑",
    "用量与覆盖",
    "数据与版本",
  ]) {
    await page.getByRole("navigation").getByRole("button", { name }).click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  }
});
