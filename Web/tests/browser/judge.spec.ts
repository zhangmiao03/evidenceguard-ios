import { test, expect } from "@playwright/test";
import { sampleBundle } from "../../src/dashboard/data.mjs";
function fixture() {
  const b: any = sampleBundle();
  b.records = b.records.filter((r: any) => r.traceId === "demo-run-1");
  const model = b.records.find((r: any) => r.kind === "model"),
    base = { ...model, kind: "event", status: "completed" };
  const prompt = b.records.find((r: any) => r.kind === "prompt");
  prompt.data.request.messages = [
    { role: "system", content: "只按证据回复" },
    { role: "user", content: "看一下这张来源图片" },
  ];
  b.records.push({
    ...base,
    id: "tool-start",
    name: "tool.started",
    at: model.at + 0.1,
    data: {
      tool: "read_stored_image",
      content: {
        arguments: { evidenceId: "evidence-abcdef12345678901234567890" },
      },
    },
  });
  b.records.push({
    ...base,
    id: "tool-final",
    name: "tool.finished",
    at: model.at + 0.2,
    data: {
      tool: "read_stored_image",
      content: {
        arguments: { api_key: "must-not-appear" },
        result: { visible: "看到了纸箱", uncertainties: "画面部分遮挡" },
      },
    },
  });
  b.records.push({
    ...base,
    id: "runtime-final",
    name: "agent.result",
    at: model.at + 0.3,
    data: { content: { answer: "可见纸箱，但无法确认画外情况。" } },
  });
  b.coverage = {
    observability: "connected",
    contentCapture: true,
    server: {
      at: model.at,
      cpuPercent: 25,
      cpuCount: 2,
      memoryUsedBytes: 1000,
      memoryTotalBytes: 4000,
      diskUsedBytes: 100,
      diskTotalBytes: 1000,
      diskFreeBytes: 900,
      services: [
        { environment: "review", state: "active", rssBytes: 20, pid: 321 },
      ],
    },
    deployment: {
      processMatchesObserver: true,
      diskVsRunning: [],
      diskVsRepository: [
        {
          path: "harness/runtime.py",
          status: "changed",
          actual: "a".repeat(64),
          expected: "b".repeat(64),
        },
      ],
      fileCount: 48,
      referenceRevision: "c".repeat(40),
    },
  };
  return b;
}
test("judge replay expands actual steps, preserves unknown result and makes no business writes", async ({
  page,
}) => {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (!["GET", "HEAD"].includes(r.method())) writes.push(r.url());
  });
  await page.goto("/dashboard?view=agent");
  await page
    .getByLabel("导入追踪 JSON")
    .setInputFiles({
      name: "judge.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(fixture())),
    });
  await expect(
    page.getByRole("region", { name: "Agent Loop 结构" }),
  ).toBeVisible();
  await page
    .locator(".judge-loop-grid button")
    .filter({ hasText: "执行工具" })
    .click();
  await expect(page.locator(".judge-phase-info")).toContainText(
    "硬件执行只在手机 SDK",
  );
  await page
    .getByRole("list", { name: "任务步骤" })
    .getByRole("button", { name: /返回：查看已保存图片/ })
    .click();
  await page.getByText("展开本步完整输入、输出与参数", { exact: true }).click();
  await expect(page.locator(".judge-step-detail")).toContainText("看到了纸箱");
  await expect(page.locator(".judge-step-detail")).not.toContainText(
    "must-not-appear",
  );
  await expect(page.locator(".judge-result")).toContainText("无法确认画外情况");
  await page.getByRole("button", { name: "查看最终回复原文" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "最终回复（实际返回 App）",
  );
  await page.getByRole("button", { name: "关闭详情" }).click();
  await expect(page.locator(".judge-filter-fold")).not.toHaveAttribute(
    "open",
    "",
  );
  expect(writes).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
});
test("shared environment survives navigation; health and source checks hide technical hashes until expanded", async ({
  page,
}) => {
  const requests: string[] = [];
  await page.route("**/dashboard/api/info", (r) =>
    r.fulfill({
      json: {
        mode: "competition",
        environments: [
          { id: "demo", title: "手机演示" },
          { id: "review", title: "检索验证" },
        ],
      },
    }),
  );
  await page.route("**/dashboard/api/snapshot?*", (r) => {
    requests.push(r.request().url());
    return r.fulfill({ json: fixture() });
  });
  await page.goto("/dashboard?view=server&environment=review");
  await expect(page.getByLabel("后端环境")).toHaveValue("review");
  await expect(page.locator(".judge-service-grid")).toContainText(
    "检索验证后端",
  );
  await page
    .getByRole("navigation", { name: "Dashboard 页面" })
    .getByRole("button", { name: "部署代码核对" })
    .click();
  await expect(page).toHaveURL(/view=deployment&environment=review/);
  await expect(page.locator(".judge-deploy-checks")).toContainText(
    "1 个文件差异",
  );
  await expect(
    page.getByText("c".repeat(40), { exact: true }),
  ).not.toBeVisible();
  await page
    .getByText("开发者核验：版本编号、SHA-256 与文件指纹", { exact: true })
    .click();
  await expect(page.getByText("c".repeat(40), { exact: true })).toBeVisible();
  expect(
    requests.every(
      (u) => new URL(u).searchParams.get("environment") === "review",
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
});
