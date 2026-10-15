import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

const camera = {
  id: "sdk-test",
  sn: "T8171TEST123",
  name: "测试客厅",
  model: "T8171",
  connection: "unknown",
  capabilities: {},
  evidence: "合成测试设备",
};
// Explicit SDK test double: these tests exercise our React/HTTP lifecycle,
// not the vendor media transport or real hardware. No external requests.
const sdkDouble = `
import React from '/node_modules/.vite/deps/react.js';
export const emptyAuth = {appName:'',clientId:'',clientSecret:'',presetKey:'',eufyUserId:'',accountUuid:''};
export function clearSDKCredentials() {}
export async function authenticate() { return {}; }
window.WebSDK = {
  Provider: ({children}) => children,
  DeviceLiveLayout: () => React.createElement('div', {'data-testid':'vendor-player'}, '合成播放器'),
  subscribeMediaChannelFrames: (_sn, cb) => {
    let timestamp = 0;
    const timer = setInterval(() => cb({blob:new Blob(['test-frame']),width:12,height:8,timestamp:++timestamp,capturedAt:Date.now()}), 100);
    return () => clearInterval(timer);
  }
};`;

async function setup(
  page: Page,
  options: {
    blockedStorage?: boolean;
    delayStart?: boolean;
    videoFallback?: boolean;
    asyncFailure?: boolean;
    challenge?: boolean;
    lateRun?: boolean;
  } = {},
) {
  const calls: { path: string; authorization?: string; time: number }[] = [];
  const uploads: any[] = [];
  let lastSequence = 0;
  if (options.blockedStorage)
    await page.addInitScript(() => {
      Storage.prototype.getItem = () => {
        throw new DOMException("blocked", "SecurityError");
      };
      Storage.prototype.setItem = () => {
        throw new DOMException("blocked", "SecurityError");
      };
    });
  let sdk = sdkDouble;
  if (options.videoFallback) {
    const video = execFileSync("ffmpeg", [
      "-hide_banner",
      "-loglevel",
      "error",
      "-f",
      "lavfi",
      "-i",
      "testsrc=size=64x48:rate=10",
      "-t",
      "4",
      "-pix_fmt",
      "yuv420p",
      "-c:v",
      "libx264",
      "-f",
      "mp4",
      "-movflags",
      "frag_keyframe+empty_moov",
      "pipe:1",
    ]);
    await page.route("**/synthetic-video.mp4", (route) =>
      route.fulfill({ contentType: "video/mp4", body: video }),
    );
    sdk = sdk.replace(
      "React.createElement('div', {'data-testid':'vendor-player'}, '合成播放器')",
      "React.createElement('video', {'data-testid':'vendor-player', autoPlay:true, muted:true, playsInline:true, loop:true, src:'/synthetic-video.mp4'})",
    );
    sdk += options.asyncFailure
      ? `\nwindow.WebSDK.subscribeMediaChannelFrames = (_sn, _cb, options) => { const t = setTimeout(() => options.onError(new Error('raw frames unavailable')), 350); return () => clearTimeout(t); };`
      : `\nwindow.WebSDK.subscribeMediaChannelFrames = () => { throw new Error('MediaStreamTrackProcessor unavailable'); };`;
  }
  await page.route("**/src/sdk.ts", (route) =>
    route.fulfill({ contentType: "application/javascript", body: sdk }),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    calls.push({
      path,
      authorization: route.request().headers().authorization,
      time: Date.now(),
    });
    let json: unknown = {};
    if (path === "/api/devices") json = [camera];
    if (path === "/api/bootstrap")
      json = {
        evidence: [],
        skills: [],
        cameras: [camera],
        agent: { ready: true, provider: "test" },
      };
    if (path === "/api/captures") json = [];
    if (path === "/api/hardware/snapshot") json = { devices: [], operations: [], tools: [] };
    if (path === "/api/sdk/events") json = { events: [], truncated: false, continuousCoverage: false };
    if (path === "/api/media-sessions") {
      if (options.delayStart)
        await new Promise((resolve) => setTimeout(resolve, 1000));
      json = {
        id: "live-test",
        deviceId: camera.id,
        token: "synthetic-session",
      };
    }
    if (path.endsWith("/heartbeat"))
      lastSequence = route.request().postDataJSON().sequence;
    if (path.endsWith("/commands"))
      json =
        options.challenge && lastSequence > 0 && !uploads.length
          ? [
              {
                requestId: "challenge-1",
                afterSequence: lastSequence,
                deadline: Date.now() / 1000 + 8,
              },
            ]
          : [];
    if (path.endsWith("/frames")) uploads.push(route.request().postDataJSON());
    if (path === "/api/agent/conversations/main")
      json = { id: "chat-test", kind: "main", title: "助手主对话" };
    if (path === "/api/agent/conversations")
      json = [{ id: "chat-test", kind: "main", title: "助手主对话" }];
    if (path === "/api/agent/conversations/chat-test") json = [];
    if (path === "/api/agent/runs") {
      if (options.lateRun)
        await new Promise((resolve) => setTimeout(resolve, 1200));
      json = { id: "run-test", status: "running", message: "test" };
    }
    if (path === "/api/runs/run-test")
      json = { id: "run-test", status: "running", message: "test" };
    if (path.endsWith("/stop"))
      await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({ json });
  });
  await page.goto("/");
  return Object.assign(calls, { uploads });
}

async function enter(page: Page) {
  await page
    .getByLabel("团队访问令牌", { exact: true })
    .fill("synthetic-team-token");
  await page.getByRole("button", { name: "进入工作台 →" }).click();
  await expect(page.getByText("云端已连接", { exact: true })).toBeVisible();
}

async function live(page: Page) {
  await enter(page);
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "摄像头 Skill", exact: true })
    .click();
  await page.getByRole("button", { name: /测试客厅.*T8171/ }).click();
  await page.getByRole("button", { name: "＋ 接入设备", exact: true }).click();
  const dialog = page.getByRole("dialog");
  for (const input of await dialog.locator("input").all()) {
    const type = await input.getAttribute("type");
    if (type !== "checkbox") await input.fill("synthetic");
  }
  await dialog.getByRole("button", { name: "连接官方服务" }).click();
  await expect(
    dialog.getByRole("button", { name: "✓ 官方鉴权完成" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "▶ 开始直播" }).click();
}

test("workspace loads when browser storage is unavailable", async ({
  page,
}) => {
  await setup(page, { blockedStorage: true });
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await enter(page);
});

test("responsive settings retain keyboard focus and fit the viewport", async ({
  page,
}) => {
  await setup(page);
  await page.getByRole("button", { name: "＋ 接入设备", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "＋ 接入设备", exact: true }),
  ).toBeFocused();
});

test("logout releases live session with the original team credential", async ({
  page,
}) => {
  const calls = await setup(page);
  await live(page);
  await expect(page.getByTestId("vendor-player")).toBeVisible();
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "进入工作台 →" }),
  ).toBeVisible();
  const stopped = calls.find((c) => c.path.endsWith("/stop"));
  expect(stopped).toBeDefined();
  expect(stopped?.authorization).toBe("Bearer synthetic-team-token");
  await expect(page.getByTestId("vendor-player")).toHaveCount(0);
});

test("official switch waits for a late start and its stop receipt", async ({
  page,
}) => {
  const calls = await setup(page, { delayStart: true });
  await live(page);
  await expect
    .poll(() => calls.some((c) => c.path === "/api/media-sessions"))
    .toBe(true);
  await page.getByRole("button", { name: "切换至官方 SDK ↗" }).click();
  await expect(
    page.getByRole("heading", { name: "官方 SDK 工作区" }),
  ).toBeVisible();
  expect(calls.some((c) => c.path.endsWith("/stop"))).toBe(true);
  await expect(page.getByTestId("vendor-player")).toHaveCount(0);
});

test("immediate restart waits until the previous media session is released", async ({
  page,
}) => {
  const calls = await setup(page);
  await live(page);
  await expect(page.getByTestId("vendor-player")).toBeVisible();
  await page.getByRole("button", { name: "停止直播", exact: true }).click();
  await page.getByRole("button", { name: "▶ 开始直播" }).click();
  await expect
    .poll(() => calls.filter((c) => c.path === "/api/media-sessions").length)
    .toBe(2);
  const firstStop = calls.find((c) => c.path.endsWith("/stop"))!;
  const secondStart = calls.filter((c) => c.path === "/api/media-sessions")[1];
  expect(firstStop).toBeDefined();
  expect(secondStart.time - firstStop.time).toBeGreaterThanOrEqual(450);
});

test("no UUID or AbortSignal.timeout helper still loads and connects", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(crypto, "randomUUID", { value: undefined });
    Object.defineProperty(AbortSignal, "timeout", { value: undefined });
  });
  await setup(page);
  await enter(page);
});

test("plain LAN HTTP renders guidance without sending credentials", async ({
  page,
}) => {
  let sent = false;
  await page.route("http://192.0.2.1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) {
      sent = true;
      await route.abort();
      return;
    }
    const response = await route.fetch({
      url: "http://127.0.0.1:5178" + url.pathname + url.search,
    });
    await route.fulfill({ response });
  });
  await page.goto("http://192.0.2.1/");
  await page
    .getByLabel("团队访问令牌", { exact: true })
    .fill("synthetic-token");
  await page.getByRole("button", { name: "进入工作台 →" }).click();
  await expect(page.getByRole("alert")).toContainText("HTTPS");
  expect(sent).toBe(false);
});

for (const asyncFailure of [false, true])
  test(`video-frame fallback uploads a subsequent JPEG (${asyncFailure ? "async error" : "no raw API"})`, async ({
    page,
  }, testInfo) => {
    test.skip(
      !(await page.evaluate(
        () =>
          typeof HTMLVideoElement.prototype.requestVideoFrameCallback ===
          "function",
      )),
      "This browser build lacks requestVideoFrameCallback; the separate unsupported-browser test must pass.",
    );
    const calls = await setup(page, {
      videoFallback: true,
      asyncFailure,
      challenge: true,
    });
    await live(page);
    try {
      await expect
        .poll(() => calls.uploads.length, { timeout: 12000 })
        .toBeGreaterThan(0);
    } catch (error) {
      await testInfo.attach("video-diagnostics", {
        contentType: "application/json",
        body: JSON.stringify(
          await page
            .getByTestId("vendor-player")
            .evaluate((element: HTMLVideoElement) => ({
              readyState: element.readyState,
              error: element.error?.message,
              errorCode: element.error?.code,
              paused: element.paused,
              time: element.currentTime,
              frameCallback: typeof element.requestVideoFrameCallback,
              h264: element.canPlayType('video/mp4; codecs="avc1.42E01E"'),
              webm: element.canPlayType('video/webm; codecs="vp8"'),
            })),
        ),
      });
      throw error;
    }
    const sample = calls.uploads[0];
    expect(sample.requestId).toBe("challenge-1");
    expect(sample.width).toBe(64);
    expect(sample.height).toBe(48);
    expect(
      Buffer.from(sample.imageBase64, "base64").subarray(0, 3).toString("hex"),
    ).toBe("ffd8ff");
  });

test("unsupported frame APIs fail explicitly and never upload a cached image", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(
      HTMLVideoElement.prototype,
      "requestVideoFrameCallback",
      { value: undefined },
    );
    delete (window as any).MediaStreamTrackProcessor;
  });
  const calls = await setup(page, { videoFallback: true, challenge: true });
  await live(page);
  await expect(page.getByText(/此浏览器缺少逐帧读取能力/)).toBeVisible();
  expect(calls.uploads).toHaveLength(0);
  await expect
    .poll(() => calls.some((c) => c.path.endsWith("/stop")))
    .toBe(true);
});

test("leaving the foreground stops frame collection", async ({ page }) => {
  const calls = await setup(page);
  await live(page);
  await expect(page.getByTestId("vendor-player")).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect
    .poll(() => calls.some((c) => c.path.endsWith("/stop")))
    .toBe(true);
  await expect(page.getByTestId("vendor-player")).toHaveCount(0);
});

test("stopping live cancels an Agent run returned after navigation", async ({
  page,
}) => {
  const calls = await setup(page, { lateRun: true });
  await live(page);
  await expect(page.getByTestId("vendor-player")).toBeVisible();
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "助手", exact: true })
    .click();
  await page.getByRole("textbox", { name: "消息输入框" }).fill("现在画面里有什么？");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect
    .poll(() => calls.some((c) => c.path === "/api/agent/runs"))
    .toBe(true);
  await page.getByRole("button", { name: "停止直播", exact: true }).click();
  await expect
    .poll(() => calls.some((c) => c.path === "/api/runs/run-test/cancel"))
    .toBe(true);
});

test("restored official bundle loads its original form and returns cleanly", async ({
  page,
}) => {
  test.skip(
    !existsSync("public/official-demo/manifest.json"),
    "Requires the locally restored organizer Demo; never copied into CI.",
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "切换至官方 SDK ↗" }).click();
  await page.getByRole("button", { name: "打开官方原版 Demo →" }).click();
  const frame = page.frameLocator('iframe[title="主办方官方 Web SDK Demo"]');
  await expect(frame.locator("input").first()).toBeVisible();
  await expect(frame.locator("input")).not.toHaveCount(0);
  expect(errors).toEqual([]);
  await page.getByRole("button", { name: "← 返回 EvidenceGuard" }).click();
  await expect(page.locator("iframe")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "进入工作台 →" }),
  ).toBeVisible();
});
