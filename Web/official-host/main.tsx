// This shell hosts the organizer's original React UI in an isolated document.
// No official playback/configuration UI is reimplemented here.
import { createRoot } from "react-dom/client";
import axios from "axios";
import App from "@official/App";
import { loadWebIoTSdk } from "@official/utils/load-sdk";
import { seedAuthConfig } from "@official/config";
import "@official/styles/index.css";
import { proxyTarget } from "../src/official-protocol.mjs";
import { guardSDKLogs, relaySDKRequest } from "../src/sdk-transport";

guardSDKLogs();

let token = "",
  channel = "",
  started = false,
  stopped = false;
const root = createRoot(document.getElementById("root")!);
const originalFetch = window.fetch.bind(window);
const pending = new Set<AbortController>();
const send = (type: string, extra = {}) =>
  parent.postMessage({ type, channel, ...extra }, location.origin);
// Both axios requests made by the original Demo and fetch calls inside the
// unmodified UMD go through the same fixed-host, team-authenticated Cloud proxy.
axios.interceptors.request.use((config) => {
  const target = proxyTarget(
    new URL(config.url!, config.baseURL || location.origin).href,
    location.origin,
  );
  if (target) {
    config.baseURL = location.origin;
    config.url = target;
    config.headers.set("X-EG-Access-Token", token);
    config.timeout = 30000;
    const controller = new AbortController();
    pending.add(controller);
    config.signal = controller.signal;
  }
  if (stopped) throw new Error("官方工作区已结束");
  return config;
});
const releaseRequest = (signal: unknown) => {
  for (const controller of pending)
    if (controller.signal === signal) pending.delete(controller);
};
axios.interceptors.response.use(
  (response) => { releaseRequest(response.config.signal); return response; },
  (error) => { releaseRequest(error.config?.signal); return Promise.reject(error); },
);
window.fetch = async (input, init) => {
  if (stopped) throw new Error("官方工作区已结束");
  const url = new URL(
    input instanceof Request ? input.url : String(input),
    location.href,
  );
  const target = proxyTarget(url.href, location.origin);
  if (!target) return originalFetch(input, init);
  const request = new Request(input, init);
  const headers = new Headers(request.headers);
  if (target.startsWith("/api/sdk/official-ai/")) {
    headers.set("Authorization", `Bearer ${token}`);
  } else headers.set("X-EG-Access-Token", token);
  const controller = new AbortController();
  pending.add(controller);
  const abort = () => controller.abort();
  request.signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 90000);
  try {
    if (request.signal.aborted) abort();
    return await relaySDKRequest(originalFetch, request, location.origin + target, headers, controller.signal);
  } finally {
    clearTimeout(timer);
    pending.delete(controller);
    request.signal.removeEventListener("abort", abort);
  }
};

window.addEventListener("message", async (event) => {
  if (event.source !== parent || event.origin !== location.origin) return;
  const message = event.data;
  if (
    message?.type === "eg:official:init" &&
    !started &&
    typeof message.channel === "string"
  ) {
    started = true;
    channel = message.channel;
    token = message.token || "";
    seedAuthConfig(message.defaults || {});
    try {
      await loadWebIoTSdk();
      if (!stopped) {
        root.render(<App />);
        send("eg:official:mounted", {
          version: window.WebSDK.version || "未声明",
        });
      }
    } catch {
      document.getElementById("root")!.textContent =
        "官方 SDK 加载失败。请检查 /sdk/index.js 并重新进入。";
      send("eg:official:error");
    }
  }
  if (message?.channel !== channel || !started) return;
  if (message.type === "eg:official:token") token = message.token || "";
  if (message.type === "eg:official:stop") {
    if (stopped) return;
    stopped = true;
    pending.forEach((controller) => controller.abort());
    pending.clear();
    root.unmount(); // official Provider + raw frame subscription cleanup
    seedAuthConfig({});
    token = "";
    // Vendor Demo documents a ~100ms deferred transport cleanup and uses
    // 300ms for reconnect. Keep the same grace period before acknowledging.
    setTimeout(() => send("eg:official:stopped"), 350);
  }
});
if (parent === window)
  document.getElementById("root")!.textContent =
    "请从 EvidenceGuard 的“官方 SDK”工作区进入。";
else send("eg:official:ready");
