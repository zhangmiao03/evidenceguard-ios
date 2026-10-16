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
  await expect(page.getByRole("dialog").locator(".eg-ops-messages")).toContainText(
    "这是模拟提示词",
  );
  await page.getByRole("button", { name: "查看完整 Trace" }).click();
  await expect(
    page.getByRole("heading", { name: "任务运行时间线" }),
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

test("full content inspector shows prompt, model output, tool result and final runtime answer", async ({ page }) => {
  const bundle = sampleBundle();
  bundle.records = bundle.records.filter((r: any) => r.traceId === "demo-run-1");
  const capture = { version: 1, mode: "full_redacted", truncated: false };
  const longText = "真实输入正文测试".repeat(2600) + "INPUT-END";
  const prompt = bundle.records.find((r: any) => r.kind === "prompt");
  prompt.data = { capture, contentCapture: true, request: { model: "demo-vision-model", messages: [{ role: "system", content: longText }, { role: "tool", tool_call_id: "call-full", content: '{"count":0}' }] } };
  const model = bundle.records.find((r: any) => r.kind === "model");
  model.data = { ...model.data, capture, content: { response: { choices: [{ message: { role: "assistant", content: "MODEL-OUTPUT-TEXT" } }] } } };
  bundle.records.push({ ...model, id: "full-tool", kind: "event", name: "tool.finished", data: { tool: "list_tasks", capture, content: { arguments: { scope: "today", api_key: "never-show-this-key" }, result: [] } } });
  bundle.records.push({ ...model, id: "full-final", kind: "event", name: "agent.result", data: { capture, content: { answer: "FINAL-APP-ANSWER", toolReceipts: [] } } });
  await page.goto("/dashboard");
  await page.getByLabel("导入追踪 JSON").setInputFiles({ name: "full.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(bundle)) });
  await page.getByRole("navigation").getByRole("button", { name: "Agent 与模型" }).click();
  await page.locator(".eg-ops-row-link").filter({ hasText: "demo-vision-model" }).first().click();
  const detail = page.getByRole("dialog");
  await expect(detail.locator(".eg-ops-messages")).toContainText("INPUT-END");
  await expect(detail.getByText("工具回执", { exact: false })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "模型原始输出（脱敏）" })).toBeVisible();
  await expect(detail.getByTestId("record-content")).toContainText("MODEL-OUTPUT-TEXT");
  await page.getByRole("button", { name: "查看完整 Trace" }).click();
  await page.getByRole("button", { name: /TOOL.*list_tasks/ }).click();
  await expect(detail.getByRole("heading", { name: "工具参数", exact: true })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "工具返回结果", exact: true, level: 3 })).toBeVisible();
  await expect(detail).not.toContainText("never-show-this-key");
  await expect(detail).toContainText("[redacted]");
  await page.getByRole("button", { name: "查看完整 Trace" }).click();
  await page.getByRole("button", { name: /查看最终回复/ }).click();
  await expect(detail.getByRole("heading", { name: "最终回复（实际返回 App）" })).toBeVisible();
  await expect(detail.getByTestId("record-content")).toContainText("FINAL-APP-ANSWER");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
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

test("Codex inspector states the observed boundary and shows actual protocol instructions", async ({ page }) => {
  const bundle = sampleBundle();
  bundle.records = bundle.records.filter((r: any) => r.traceId === "demo-run-1");
  const model = bundle.records.find((r: any) => r.kind === "model");
  const capture = { version: 1, mode: "full_redacted", truncated: false };
  model.name = "codex_step"; model.status = "executor_ok";
  model.data = { ...model.data, capture, transport: "codex_app_server", usage: null, wireHttpVisible: false,
    content: { response: { role: "assistant", content: "CODEX-ACTUAL-OUTPUT" } } };
  bundle.records.push({ ...model, id: "codex-protocol", kind: "event", name: "codex.request",
    data: { capture, transport: "codex_app_server", method: "thread/start", content: { message: {
      method: "thread/start", params: { baseInstructions: "HOST-INSTRUCTIONS-AND-ADAPTER-SUFFIX", dynamicTools: [] } } } } });
  await page.goto("/dashboard");
  await page.getByLabel("导入追踪 JSON").setInputFiles({ name: "codex.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(bundle)) });
  await expect(page.getByText(/Codex 执行步骤：1/)).toBeVisible();
  await page.getByRole("navigation").getByRole("button", { name: "Agent 与模型" }).click();
  await page.locator(".eg-ops-row-link").filter({ hasText: "demo-vision-model" }).first().click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Codex 返回主程序的输出（脱敏）" })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("CODEX-ACTUAL-OUTPUT");
  await expect(page.getByRole("dialog")).toContainText("此步骤不计作 HTTP 请求");
  await page.getByRole("button", { name: "关闭详情" }).click();
  await page.locator(".eg-ops-row-link").filter({ hasText: "codex.request" }).click();
  await expect(page.getByRole("dialog")).toContainText("HOST-INSTRUCTIONS-AND-ADAPTER-SUFFIX");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
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
