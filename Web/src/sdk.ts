import * as React from "react";
import * as ReactDOM from "react-dom";
import axios from "axios";
import { api } from "./api";
import { requireSecureConnection } from "./browser-support";
import { getDomain, exchangeKey, requestToken } from "./vendor";
import { HeaderBuilder } from "./vendor/header";
import { Request as VendorRequest } from "./vendor/request";
import { guardSDKLogs, relaySDKRequest } from "./sdk-transport";

export type SDKFrame = {
  blob: Blob;
  width: number;
  height: number;
  timestamp: number;
  capturedAt: number;
};
export type Auth = {
  appName: string;
  clientId: string;
  clientSecret: string;
  presetKey: string;
  eufyUserId: string;
  accountUuid: string;
};
export type TokenAuth = Pick<Auth, "appName" | "clientId" | "presetKey" | "eufyUserId"> & {
  authorization: string;
};
export interface SDKIntegration {
  onBeforeInit(): Promise<void>;
  getAuthService(): { getWSSign(): Promise<unknown> };
  onBeforeDestroy(): Promise<void>;
}
export const emptyAuth: Auth = {
  appName: "",
  clientId: "",
  clientSecret: "",
  presetKey: "",
  eufyUserId: "",
  accountUuid: "",
};
export interface SDK {
  Provider: React.ComponentType<{
    config: { stationSn: string; integration: unknown };
    children: React.ReactNode;
    loadingComponent?: React.ReactNode;
  }>;
  DeviceLiveLayout: React.ComponentType<{
    deviceSn: string;
    onError: (error: string) => void;
  }>;
  OpenAPIIntegration: new (config: Record<string, string>) => SDKIntegration;
  subscribeMediaChannelFrames: (
    sn: string,
    callback: (frame: SDKFrame) => void,
    options: {
      intervalMs: number;
      mimeType: "image/jpeg";
      quality: number;
      onError: (error: Error) => void;
    },
  ) => () => void;
}
declare global {
  interface Window {
    React: typeof React;
    ReactDOM: typeof ReactDOM;
    WebSDK: SDK;
  }
}
let loading: Promise<SDK> | undefined;
let patched = false;
let credentialGeneration = 0;
const pending = new Set<AbortController>();
export function loadSDK(): Promise<SDK> {
  guardSDKLogs();
  if (
    typeof window.WebSDK?.Provider !== "undefined" &&
    typeof window.WebSDK?.subscribeMediaChannelFrames === "function"
  )
    return Promise.resolve(window.WebSDK);
  if (!loading)
    loading = new Promise<SDK>((resolve, reject) => {
      window.React = React;
      window.ReactDOM = ReactDOM;
      const script = document.createElement("script");
      script.src = "/sdk/index.js";
      const timeout = window.setTimeout(() => {
        script.remove();
        reject(new Error("官方 Web SDK 加载超时"));
      }, 15000);
      script.onload = () => {
        clearTimeout(timeout);
        typeof window.WebSDK?.subscribeMediaChannelFrames === "function"
          ? resolve(window.WebSDK)
          : reject(new Error("SDK 版本缺少实时取帧接口"));
      };
      script.onerror = () => {
        clearTimeout(timeout);
        script.remove();
        reject(
          new Error("请先运行 scripts/import_web_sdk.py 恢复官方 Web SDK"),
        );
      };
      document.head.appendChild(script);
    }).catch((error) => {
      loading = undefined;
      throw error;
    });
  return loading;
}

function installProxy() {
  axios.defaults.headers.common["X-EG-Access-Token"] = api.token;
  if (patched) return;
  patched = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = new URL(
      input instanceof globalThis.Request ? input.url : String(input),
      location.href,
    );
    if (url.origin !== "https://openapi-us.eufylife.com")
      return original(input, init);
    const request = new globalThis.Request(input, init);
    const headers = new Headers(request.headers);
    headers.set("X-EG-Access-Token", api.token);
    const target = `${location.origin}/api/sdk/openapi${url.pathname}${url.search}`;
    const controller = new AbortController();
    const abort = () => controller.abort();
    pending.add(controller);
    request.signal.addEventListener("abort", abort, { once: true });
    if (request.signal.aborted) abort();
    const timer = setTimeout(abort, 30000);
    try {
      return await relaySDKRequest(original, request, target, headers, controller.signal);
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
      request.signal.removeEventListener("abort", abort);
    }
  };
}

export async function authenticate(auth: Auth | TokenAuth): Promise<unknown> {
  requireSecureConnection();
  if (!crypto.subtle) throw new Error("当前浏览器不支持安全的设备鉴权，请使用 HTTPS 和较新的浏览器。");
  if (Object.values(auth).some(value => !value.trim()))
    throw new Error("请填写完整的官方账号参数");
  clearSDKCredentials();
  const generation = credentialGeneration;
  const current = () => {
    if (generation !== credentialGeneration) throw new Error("官方账号连接已取消");
  };
  await loadSDK();
  current();
  installProxy();
  if ("authorization" in auth) {
    const config = {
      apiDomain: "https://openapi-us.eufylife.com",
      appName: auth.appName.trim(), clientId: auth.clientId.trim(),
      presetKey: auth.presetKey.trim(), userId: auth.eufyUserId.trim(),
      authorization: auth.authorization.trim(),
    };
    const probe = new window.WebSDK.OpenAPIIntegration(config);
    try {
      // Verify the issued token, not merely that ECDH succeeded. The live
      // Provider receives a fresh integration with its own lifecycle below.
      await probe.onBeforeInit();
      current();
      const sign = await probe.getAuthService().getWSSign();
      current();
      if (typeof sign !== "string" || !sign.trim())
        throw new Error("missing Web signature");
      return new window.WebSDK.OpenAPIIntegration(config);
    } catch {
      if (generation === credentialGeneration) clearSDKCredentials();
      throw new Error("赛事 Token 的 Web 信令鉴权未通过，请核对 PR/US 应用参数、Token 有效期和网络。");
    } finally {
      await probe.onBeforeDestroy?.();
    }
  }
  VendorRequest.AccessToken = "";
  VendorRequest.headerBuilder = new HeaderBuilder({
    appName: auth.appName,
    clientId: auth.clientId,
    CLIENT_SECRET: auth.clientSecret,
  });
  const domain = await getDomain("us", "US");
  current();
  if (new URL(domain).origin !== "https://openapi-us.eufylife.com")
    throw new Error("当前接入只配置了官方 US 环境，请核对赛事账号区域");
  const proxy = "/api/sdk/openapi";
  const ecdhKey = await exchangeKey(proxy, auth.presetKey);
  current();
  VendorRequest.ecdhKey = ecdhKey;
  VendorRequest.baseURL = proxy;
  const token = await requestToken({
    eufy_user_id: auth.eufyUserId,
    account_uuid: auth.accountUuid,
  });
  current();
  if (!token?.access_token) throw new Error("官方鉴权没有返回有效访问令牌");
  VendorRequest.AccessToken = token.access_token;
  return new window.WebSDK.OpenAPIIntegration({
    apiDomain: domain,
    userId: auth.eufyUserId,
    authorization: token.access_token,
    presetKey: auth.presetKey,
    appName: auth.appName,
    clientId: auth.clientId,
  });
}

export function clearSDKCredentials() {
  credentialGeneration++;
  pending.forEach(controller => controller.abort());
  pending.clear();
  VendorRequest.AccessToken = "";
  // Static signing state must not remain after a user disconnects the account.
  VendorRequest.headerBuilder = undefined as unknown as HeaderBuilder;
  VendorRequest.ecdhKey = undefined as unknown as typeof VendorRequest.ecdhKey;
  delete axios.defaults.headers.common["X-EG-Access-Token"];
}
