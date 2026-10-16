import { test, expect, type Page } from "@playwright/test";
import { createServer } from "node:http";

// Explicit synthetic SDK transport: never contacts the vendor or real cameras.
const syntheticSDK = `
window.__sdkConstructed = []; window.__sdkDestroyed = 0;
window.WebSDK = {
  Provider: ({children}) => children,
  subscribeMediaChannelFrames: () => () => {},
  OpenAPIIntegration: class {
    constructor(config) { this.config = config; window.__sdkConstructed.push(config); }
    async onBeforeInit() {
      console.log('fixture-private-marker', this.config);
      const response = await fetch(this.config.apiDomain + '/v1/app/account/key_exchange', {
        method: 'POST', headers: {'Content-Type':'text/plain'}, body:'synthetic-key-exchange'
      });
      if (!response.ok) throw new Error('fixture-private-marker: ' + this.config.authorization);
    }
    getAuthService() { return {getWSSign: async () => {
      const response = await fetch(this.config.apiDomain + '/v1/smart/websdk/ws/sign', {
        headers: {Authorization:this.config.authorization}
      });
      if (!response.ok) throw new Error('fixture-private-marker: ' + this.config.authorization);
      return (await response.json()).data;
    }}; }
    async onBeforeDestroy() { window.__sdkDestroyed++; }
  }
};`;

async function prepare(page: Page, signature: unknown = "synthetic-signature") {
  const calls: {path: string; method: string; body: string | null; headers: Record<string, string>}[] = [];
  await page.route("**/sdk/index.js", route => route.fulfill({contentType: "application/javascript", body: syntheticSDK}));
  await page.route("**/api/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    calls.push({path, method: request.method(), body: request.postData(), headers: request.headers()});
    let json: unknown = [];
    if (path === "/api/bootstrap") json = {skills: [], cameras: [], evidence: [], agent: {}, personal: {revision: 0, preferences: {}, memories: [], inbox: [], messages: []}};
    if (path === "/api/agent/conversations/main") json = {id: "test-main", kind: "main"};
    if (path === "/api/hardware/snapshot") json = {devices: [], operations: [], tools: []};
    if (path === "/api/sdk/events") json = {events: [], truncated: false, continuousCoverage: false};
    if (path.endsWith("/key_exchange")) json = {code: 0};
    if (path.endsWith("/ws/sign")) json = {code: signature ? 0 : 463, data: signature};
    await route.fulfill({json});
  });
  await page.goto("/");
  return calls;
}

const credentials = {
  appName: "synthetic-app", clientId: "synthetic-client", presetKey: "synthetic-preset",
  eufyUserId: "synthetic-user", authorization: "synthetic-official-token",
};

test("issued Token verifies Web signature, stays in memory, and uses the team-authenticated proxy", async ({page}) => {
  const logs: string[] = [];
  page.on("console", message => logs.push(message.text()));
  const calls = await prepare(page);
  await page.getByLabel("团队访问令牌", {exact: true}).fill("synthetic-team-token");
  await page.getByRole("button", {name: "进入工作台 →"}).click();
  await expect(page.getByText("云端已连接", {exact: true}).first()).toBeVisible();
  await page.getByRole("navigation", {name: "主导航"}).getByRole("button", {name: "摄像头 Skill", exact: true}).click();
  await page.getByRole("button", {name: "＋ 接入设备", exact: true}).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("官方账号接入方式")).toHaveValue("token");
  for (const [label, value] of [
    ["App Name", credentials.appName], ["Client ID", credentials.clientId],
    ["Preset Key", credentials.presetKey], ["Eufy User ID", credentials.eufyUserId],
    ["赛事 Token", credentials.authorization],
  ]) await dialog.getByLabel(label, {exact: true}).fill(value);
  await expect(dialog.getByLabel("Client Secret", {exact: true})).toHaveCount(0);
  await expect(dialog.getByLabel("Account UUID", {exact: true})).toHaveCount(0);
  await dialog.getByRole("button", {name: "连接官方服务", exact: true}).click();
  await expect(dialog.getByRole("button", {name: "✓ 官方信令鉴权通过"})).toBeVisible();
  const vendor = calls.filter(call => call.path.startsWith("/api/sdk/openapi/"));
  expect(vendor.map(call => call.path.split("/v1/")[1])).toEqual(["app/account/key_exchange", "smart/websdk/ws/sign"]);
  expect(vendor[0].body).toBe("synthetic-key-exchange");
  expect(vendor[1].headers.authorization).toBe(credentials.authorization);
  expect(vendor.every(call => call.headers["x-eg-access-token"] === "synthetic-team-token")).toBe(true);
  const state = await page.evaluate(() => ({
    constructed: (window as any).__sdkConstructed.length, destroyed: (window as any).__sdkDestroyed,
    storage: JSON.stringify({...localStorage, ...sessionStorage}),
  }));
  expect(state.constructed).toBe(2); expect(state.destroyed).toBe(1);
  expect(state.storage).not.toContain(credentials.authorization);
  expect(logs.join("\n")).not.toContain("fixture-private-marker");
  expect(logs.join("\n")).not.toContain(credentials.authorization);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await dialog.getByRole("button", {name: "断开官方账号"}).click();
  await expect(dialog.getByLabel("赛事 Token", {exact: true})).toHaveValue("");
  await expect(dialog.getByLabel("Eufy User ID", {exact: true})).toHaveValue("");
});

test("ECDH alone cannot mark a Token valid when Web signature is missing", async ({page}) => {
  await prepare(page, "");
  const result = await page.evaluate(async auth => {
    const {authenticate} = await import("/src/sdk.ts");
    try { await authenticate(auth); return "unexpected-success"; }
    catch (error) { return String(error); }
  }, credentials);
  expect(result).toContain("Web 信令鉴权未通过");
  expect(result).not.toContain(credentials.authorization);
  expect(await page.evaluate(() => (window as any).__sdkDestroyed)).toBe(1);
});

test("disconnect aborts pending SDK authentication and cannot recreate credentials", async ({page}) => {
  await prepare(page);
  let requested = false;
  await page.route("**/api/sdk/openapi/v1/app/account/key_exchange", async route => {
    requested = true;
    // Intentionally unanswered; disconnect must abort the browser request.
  });
  await page.evaluate(auth => {
    (window as any).__authDone = import("/src/sdk.ts").then(async ({authenticate}) => {
      try { await authenticate(auth); return "unexpected-success"; }
      catch { return "cancelled"; }
    });
  }, credentials);
  await expect.poll(() => requested).toBe(true);
  await page.evaluate(async () => { (await import("/src/sdk.ts")).clearSDKCredentials(); });
  await expect.poll(() => page.evaluate(() => (window as any).__authDone)).toBe("cancelled");
  expect(await page.evaluate(() => (window as any).__sdkConstructed.length)).toBe(1);
});

test("SDK relay posts a real HTTP/1.1 body without requiring streaming-upload support", async ({page}) => {
  const bodies: string[] = [];
  const server = createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    bodies.push(Buffer.concat(chunks).toString());
    response.setHeader("Access-Control-Allow-Origin", "http://127.0.0.1:5178");
    response.setHeader("Content-Type", "application/json");
    response.end('{"ok":true}');
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address() as {port: number};
    await page.goto("/");
    const result = await page.evaluate(async port => {
      const {relaySDKRequest} = await import("/src/sdk-transport.ts");
      const target = `http://127.0.0.1:${port}/echo`;
      const request = new Request(target, {method: "POST", headers: {"Content-Type": "text/plain"}, body: "signed-body-fixture"});
      const response = await relaySDKRequest(fetch.bind(window), request, target, new Headers(request.headers));
      return response.json();
    }, address.port);
    expect(result).toEqual({ok: true}); expect(bodies).toEqual(["signed-body-fixture"]);
  } finally {
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
  }
});
