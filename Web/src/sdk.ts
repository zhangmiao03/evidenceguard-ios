import * as React from "react";
import * as ReactDOM from "react-dom";
import axios from "axios";
import { api } from "./api";
import { requireSecureConnection } from "./browser-support";
import { getDomain, exchangeKey, requestToken } from "./vendor";
import { HeaderBuilder } from "./vendor/header";
import { Request as VendorRequest } from "./vendor/request";

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
  OpenAPIIntegration: new (config: Record<string, string>) => unknown;
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
export function loadSDK(): Promise<SDK> {
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
  window.fetch = (input, init) => {
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
    return original(new globalThis.Request(target, request), {
      headers,
      credentials: "same-origin",
    });
  };
}

export async function authenticate(auth: Auth): Promise<unknown> {
  requireSecureConnection();
  if (!crypto.subtle) throw new Error("当前浏览器不支持安全的设备鉴权，请使用 HTTPS 和较新的浏览器。");
  await loadSDK();
  installProxy();
  VendorRequest.AccessToken = "";
  VendorRequest.headerBuilder = new HeaderBuilder({
    appName: auth.appName,
    clientId: auth.clientId,
    CLIENT_SECRET: auth.clientSecret,
  });
  const domain = await getDomain("us", "US");
  if (new URL(domain).origin !== "https://openapi-us.eufylife.com")
    throw new Error("当前接入只配置了官方 US 环境，请核对赛事账号区域");
  const proxy = "/api/sdk/openapi";
  VendorRequest.ecdhKey = await exchangeKey(proxy, auth.presetKey);
  VendorRequest.baseURL = proxy;
  const token = await requestToken({
    eufy_user_id: auth.eufyUserId,
    account_uuid: auth.accountUuid,
  });
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
  VendorRequest.AccessToken = "";
  // Static signing state must not remain after a user disconnects the account.
  VendorRequest.headerBuilder = undefined as unknown as HeaderBuilder;
  VendorRequest.ecdhKey = undefined as unknown as typeof VendorRequest.ecdhKey;
  delete axios.defaults.headers.common["X-EG-Access-Token"];
}
