import * as React from "react";
import * as ReactDOM from "react-dom";
import { useEffect, useRef, useState } from "react";
type Frame = {
  blob: Blob;
  width: number;
  height: number;
  timestamp: number;
  capturedAt: number;
};
type SDK = {
  Provider: React.ComponentType<{
    config: { stationSn: string; integration: unknown };
    children: React.ReactNode;
    loadingComponent?: React.ReactNode;
  }>;
  DeviceLiveLayout: React.ComponentType<{
    deviceSn: string;
    autoStart?: boolean;
    onError?: (message: string) => void;
  }>;
  OpenAPIIntegration: new (config: Record<string, string>) => unknown;
  subscribeMediaChannelFrames: (
    sn: string,
    callback: (frame: Frame) => void,
    options: {
      intervalMs: number;
      mimeType: "image/jpeg";
      onError: (error: Error) => void;
    },
  ) => () => void;
};
declare global {
  interface Window {
    WebSDK?: SDK;
    React: typeof React;
    ReactDOM: typeof ReactDOM;
  }
}
let loading: Promise<SDK> | null = null;
function loadSDK() {
  if (window.WebSDK) return Promise.resolve(window.WebSDK);
  if (!loading)
    loading = new Promise<SDK>((resolve, reject) => {
      window.React = React;
      window.ReactDOM = ReactDOM;
      const script = document.createElement("script");
      script.src = "/sdk/index.js";
      script.onload = () => {
        if (window.WebSDK?.Provider && window.WebSDK?.OpenAPIIntegration)
          resolve(window.WebSDK);
        else {
          script.remove();
          loading = null;
          reject(new Error("官方 SDK 未正确初始化"));
        }
      };
      script.onerror = () => {
        script.remove();
        loading = null;
        reject(
          new Error(
            "SDK 文件缺失，请先运行 scripts/import_sdk.py 恢复资料包。",
          ),
        );
      };
      document.head.append(script);
    });
  return loading;
}
function FrameSample({
  sdk,
  sn,
  interval,
}: {
  sdk: SDK;
  sn: string;
  interval: number;
}) {
  const [preview, setPreview] = useState("");
  const [info, setInfo] = useState("尚未采样");
  const [error, setError] = useState("");
  const [active, setActive] = useState(false);
  const stop = useRef<(() => void) | null>(null);
  const url = useRef("");
  const enabled = useRef(false);
  function stopSampling() {
    enabled.current = false;
    stop.current?.();
    stop.current = null;
    setActive(false);
  }
  useEffect(
    () => () => {
      enabled.current = false;
      stop.current?.();
      if (url.current) URL.revokeObjectURL(url.current);
    },
    [],
  );
  function start() {
    setError("");
    enabled.current = true;
    try {
      if (!sdk.subscribeMediaChannelFrames)
        throw new Error("当前 SDK 没有裸帧订阅接口，请核对资料包版本。");
      stop.current = sdk.subscribeMediaChannelFrames(
        sn,
        (frame) => {
          if (!enabled.current) return;
          if (url.current) URL.revokeObjectURL(url.current);
          url.current = URL.createObjectURL(frame.blob);
          setPreview(url.current);
          setInfo(
            `${frame.width} × ${frame.height} · 本机接收 ${new Date(frame.capturedAt).toLocaleTimeString()} · 媒体时间 ${(frame.timestamp / 1_000_000).toFixed(3)} s`,
          );
        },
        {
          intervalMs: Math.max(3, interval) * 1000,
          mimeType: "image/jpeg",
          onError: (e) => {
            stopSampling();
            setError(e.message);
          },
        },
      );
      setActive(true);
    } catch (e) {
      enabled.current = false;
      setError((e as Error).message);
    }
  }
  return (
    <div className="sample">
      <h3>按秒抽帧联调</h3>
      <button onClick={active ? stopSampling : start}>
        {active ? "停止采样" : `开始采样 · Every ${interval} s`}
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {preview && <img src={preview} alt="SDK 最新采样画面" />}
      <p className="muted">{info}</p>
      <p className="muted">
        接收时刻不等于摄像头拍摄时间。当前仅验证取图，尚未上传 harness
        或启用守护。
      </p>
    </div>
  );
}
export function SDKPreview() {
  const [config, setConfig] = useState({
    stationSn: "",
    apiDomain: "https://openapi-us.eufylife.com",
    userId: "",
    presetKey: "",
    authorization: "",
    appName: "",
    clientId: "",
  });
  const [session, setSession] = useState<{
    sdk: SDK;
    sn: string;
    integration: unknown;
  } | null>(null);
  const [interval, setIntervalSeconds] = useState(3);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const release = useRef<(() => void) | null>(null);
  const generation = useRef(0);
  function disconnect() {
    generation.current++;
    setSession(null);
    release.current?.();
    release.current = null;
    setBusy(false);
  }
  useEffect(
    () => () => {
      generation.current++;
      release.current?.();
    },
    [],
  );
  async function connect() {
    const sn = config.stationSn.trim();
    if (!["T8171", "T8214"].some((prefix) => sn.startsWith(prefix))) {
      setError("请输入 T8171 / T8214 的实际设备 SN。");
      return;
    }
    setBusy(true);
    setError("");
    const current = ++generation.current;
    try {
      const domain = new URL(config.apiDomain);
      if (
        domain.protocol !== "https:" ||
        domain.username ||
        domain.password ||
        domain.pathname !== "/" ||
        domain.search ||
        domain.hash ||
        !domain.hostname.endsWith(".eufylife.com")
      )
        throw new Error(
          "API Domain 必须是主办方指定的 eufylife.com HTTPS 域名。",
        );
      if (!navigator.locks)
        throw new Error(
          "请在 localhost 或 HTTPS 下使用支持 Web Locks 的 Chrome / Edge。",
        );
      const sdk = await loadSDK();
      if (current !== generation.current) return;
      let notify!: (held: boolean) => void;
      const acquired = new Promise<boolean>((resolve) => {
        notify = resolve;
      });
      const hold = navigator.locks.request(
        `evidenceguard-sdk:${sn}`,
        { ifAvailable: true },
        async (lock) => {
          if (!lock) {
            notify(false);
            return;
          }
          await new Promise<void>((resolve) => {
            release.current = resolve;
            notify(true);
          });
        },
      );
      void hold.catch(() => notify(false));
      if (!(await acquired))
        throw new Error("此浏览器已有页面使用该摄像头，请先断开另一页面。");
      if (current !== generation.current) {
        release.current?.();
        return;
      }
      const { stationSn: _, ...credentials } = config;
      const integration = new sdk.OpenAPIIntegration(
        Object.fromEntries(
          Object.entries(credentials).map(([k, v]) => [k, v.trim()]),
        ),
      );
      setSession({ sdk, sn, integration });
      setConfig((value) => ({ ...value, authorization: "", presetKey: "" }));
    } catch (e) {
      release.current?.();
      release.current = null;
      if (current === generation.current) setError((e as Error).message);
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>官方摄像头联调</h1>
          <p>T8171 屋檐摄像头 · T8214 门铃摄像头</p>
        </div>
      </div>
      <div className="notice">
        这里使用官方 Web SDK 做直播和取图测试。App
        继续负责录像、事件与设备控制。Web 与 App
        的跨端设备占用还待接入验证，当前不开放真实 Skill 发布。
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {!session ? (
        <div className="card">
          <h2>建立 SDK 会话</h2>
          <p className="muted">
            填写官方 Web OpenAPI 可用的用户 Token 和配置。App Token
            是否可复用需要主办方确认。配置仅保留在本页面内存，模型 API Key
            不填在这里。
          </p>
          <div className="sdk-form">
            {Object.entries(config).map(([key, value]) => (
              <label key={key}>
                {
                  {
                    stationSn: "设备 SN",
                    apiDomain: "API Domain",
                    userId: "User ID",
                    presetKey: "Preset Key",
                    authorization: "用户 Token",
                    appName: "App Name",
                    clientId: "Client ID",
                  }[key]
                }
                <input
                  type={
                    ["authorization", "presetKey"].includes(key)
                      ? "password"
                      : "text"
                  }
                  autoComplete="off"
                  spellCheck={false}
                  value={value}
                  onChange={(e) =>
                    setConfig({ ...config, [key]: e.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            已停止 App 和其他客户端对这台设备的任务，当前只做联调预览
          </label>
          <button
            className="primary"
            disabled={
              busy || !ack || Object.values(config).some((v) => !v.trim())
            }
            onClick={() => void connect()}
          >
            {busy ? "准备连接…" : "连接官方摄像头"}
          </button>
        </div>
      ) : (
        <div className="card">
          <div className="toolbar">
            <h2>{session.sn}</h2>
            <button onClick={disconnect}>断开会话</button>
          </div>
          <session.sdk.Provider
            config={{ stationSn: session.sn, integration: session.integration }}
            loadingComponent={<div className="empty">正在连接设备…</div>}
          >
            <session.sdk.DeviceLiveLayout
              deviceSn={session.sn}
              autoStart
              onError={(message) => {
                setError(message);
                disconnect();
              }}
            />
          </session.sdk.Provider>
          <label>
            采样间隔（s）
            <input
              type="number"
              min="3"
              max="300"
              value={interval}
              onChange={(e) =>
                setIntervalSeconds(
                  Math.max(
                    3,
                    Math.min(300, Math.trunc(Number(e.target.value)) || 3),
                  ),
                )
              }
            />
          </label>
          <FrameSample
            key={interval}
            sdk={session.sdk}
            sn={session.sn}
            interval={interval}
          />
        </div>
      )}
    </>
  );
}
