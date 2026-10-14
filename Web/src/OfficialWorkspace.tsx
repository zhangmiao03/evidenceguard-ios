import { useEffect, useRef, useState } from "react";
import type { Auth } from "./sdk";
import { acceptsOfficialMessage } from "./official-protocol.mjs";
import { newID, requireSecureConnection } from "./browser-support";

type Manifest = {
  protocol: number;
  source: string;
  sdkSha256: string;
  builtAt: string;
};
const checks = [
  [
    "auth",
    "账号鉴权与设备唤醒",
    "原版配置表单 → 连接；记录同一账号、SN 和当前网络。",
  ],
  [
    "live",
    "直播、声音与断流重连",
    "检查首帧、静音/声音、全屏、主动断流和重新连接。以 SDK 实际工具栏为准。",
  ],
  [
    "frames",
    "原始帧与视觉分析",
    "原版 AI 裸帧面板：点击开始后采集 10 帧，自动提交官方 AI 网关；需要服务端配置赛事模型密钥。",
  ],
  [
    "ptz",
    "云台与其他设备控制",
    "T8171 检查工具栏实际露出的控制；未露出的项目在原生官方 Demo 继续核验。T8214 不按云台验收。",
  ],
  [
    "network",
    "局域网 / 跨网 / 断网恢复",
    "用同一设备分别验证；跨网可用不能由一次局域网成功推断。",
  ],
  [
    "native",
    "首次配网、绑定与完整设置",
    "转 iOS 官方工作区：添加设备 → 按型号配网/绑定 → 设置。此版官方 Web Demo 没有这些页面。",
  ],
  [
    "return",
    "返回本项目后的设备同步",
    "返回 EvidenceGuard，重新鉴权/查询设备，再验证直播与 Agent 新画面。",
  ],
] as const;

export function OfficialWorkspace({
  token: initialToken,
  defaults,
  onReturn,
}: {
  token: string;
  defaults: Auth & { stationSn?: string };
  onReturn: () => void;
}) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState("");
  const [model, setModel] = useState(
    defaults.stationSn?.startsWith("T8214") ? "T8214" : "T8171",
  );
  const [serial, setSerial] = useState(defaults.stationSn || "");
  const [token, setToken] = useState(initialToken);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const frame = useRef<HTMLIFrameElement>(null);
  const channel = useRef(newID());
  const stopping = useRef<Promise<void> | null>(null);
  const stopReply = useRef<(() => void) | null>(null);
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const stateKey = `${model}:${serial.trim().toUpperCase()}`;
  useEffect(() => {
    let disposed = false;
    fetch("/official-demo/manifest.json", { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error("尚未恢复官方 Demo");
        const data = await r.json();
        if (data.protocol !== 1 || !/^[a-f0-9]{64}$/.test(data.sdkSha256))
          throw new Error("官方 Demo 版本不匹配，请重新构建");
        if (!disposed) setManifest(data);
      })
      .catch(() => {
        if (!disposed)
          setError("尚未恢复官方 Demo。按下方命令导入主办方资料后刷新。");
      });
    return () => {
      disposed = true;
    };
  }, []);
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (
        !acceptsOfficialMessage(
          event,
          frame.current?.contentWindow,
          location.origin,
          channel.current,
        )
      )
        return;
      if (event.data.type === "eg:official:ready") {
        frame.current?.contentWindow?.postMessage(
          {
            type: "eg:official:init",
            channel: channel.current,
            token: tokenRef.current,
            defaults: { ...defaults, stationSn: serial.trim().toUpperCase() },
          },
          location.origin,
        );
      }
      if (event.data.type === "eg:official:mounted")
        setVersion(String(event.data.version));
      if (event.data.type === "eg:official:error")
        setError("官方 SDK 加载失败，请恢复 SDK 后重新进入。");
      if (event.data.type === "eg:official:stopped") stopReply.current?.();
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [defaults, serial]);
  useEffect(() => {
    frame.current?.contentWindow?.postMessage(
      { type: "eg:official:token", channel: channel.current, token },
      location.origin,
    );
  }, [token]);
  const stop = (): Promise<void> => {
    if (stopping.current) return stopping.current;
    if (!running) return Promise.resolve();
    const operation = (async () => {
      setBusy(true);
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 2500);
        stopReply.current = () => {
          clearTimeout(timer);
          resolve();
        };
        frame.current?.contentWindow?.postMessage(
          { type: "eg:official:stop", channel: channel.current },
          location.origin,
        );
      });
      // Removing the browsing context also terminates WebRTC if the child failed
      // before it could answer. Always remove it before the product can remount.
      stopReply.current = null;
      setRunning(false);
      setVersion("");
      await new Promise((resolve) => setTimeout(resolve, 350));
      setBusy(false);
      stopping.current = null;
    })();
    stopping.current = operation;
    return operation;
  };
  useEffect(() => {
    const hidden = () => {
      if (document.hidden) void stop();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => document.removeEventListener("visibilitychange", hidden);
  }, [running]);
  const download = () => {
    const report = {
      schema: 1,
      mode: "official-web-demo",
      model,
      serial: serial.trim().toUpperCase(),
      createdAt: new Date().toISOString(),
      sdkVersion: version || null,
      sdkSha256: manifest?.sdkSha256,
      checks: checks.map(([id, title]) => ({
        id,
        title,
        result: results[`${stateKey}:${id}`] || "未测试",
      })),
      notes,
      resultSource: "manual-team-checklist",
      credentialsIncluded: false,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `EvidenceGuard-${model}-hardware-check.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="official-workspace">
      <header className="official-header">
        <div>
          <span className="eyebrow">EVIDENCEGUARD · 硬件实验室</span>
          <h1>官方 SDK 工作区</h1>
          <p>原版 Demo 直连设备，逐项确认真实硬件边界。</p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            await stop();
            onReturn();
          }}
        >
          {busy ? "正在结束会话…" : "← 返回 EvidenceGuard"}
        </button>
      </header>
      <div className="official-mode-strip">
        <span className="mode-tag">当前：官方原版界面</span>
        <span>
          本项目 Agent 不接收此处画面。原版 AI 面板点击开始后，会采集 10
          帧并提交官方模型网关。
        </span>
      </div>
      <div className="official-grid">
        <section className="official-preview">
          <div className="official-preview-heading">
            <div>
              <h2>官方 Web Demo</h2>
              <span className="muted">
                {version
                  ? `SDK ${version}`
                  : manifest
                    ? "原始界面已恢复 · 等待打开"
                    : "等待导入主办方文件"}
              </span>
            </div>
            {running && (
              <button disabled={busy} onClick={() => void stop()}>
                结束官方会话
              </button>
            )}
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {running ? (
            <iframe
              ref={frame}
              className="official-frame"
              title="主办方官方 Web SDK Demo"
              src="/official-demo/index.html"
              allow="microphone; fullscreen"
            />
          ) : (
            <div className="official-launch">
              <div className="official-symbol" aria-hidden="true">
                ⌘
              </div>
              <h2>从官方原始流程开始验证</h2>
              <p>
                鉴权配置、直播播放器、断流重连与 AI
                裸帧面板直接来自本次赛事资料包。
              </p>
              <label>
                团队访问令牌（本地未启用鉴权可留空）
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  autoComplete="off"
                />
              </label>
              <button
                className="primary"
                disabled={!manifest || busy}
                onClick={() => {
                  try {
                    requireSecureConnection();
                  } catch (e) {
                    setError((e as Error).message);
                    return;
                  }
                  channel.current = newID();
                  setError("");
                  setRunning(true);
                }}
              >
                打开官方原版 Demo →
              </button>
              {!manifest && (
                <pre>
                  python scripts/import_official_web_demo.py "资料包/WebSDKDemo"
                  {"\n"}cd Web{"\n"}npm run build:official
                </pre>
              )}
              <p className="subtle-note">
                账号参数只在本次页面内保留；刷新后重新填写。首次绑定与完整设置请打开
                iOS 的“官方 SDK”。
              </p>
            </div>
          )}
          <details className="official-provenance">
            <summary>来源与版本记录</summary>
            <p>
              界面：{manifest?.source || "待导入"}
              。本项目仅增加工作区外壳、代理和凭证存储适配。
            </p>
            <code>SDK SHA-256：{manifest?.sdkSha256 || "待校验"}</code>
            <p>
              构建：{manifest?.builtAt || "未构建"}。SDK
              的实际按钮随型号、设备能力表与固件变化。
            </p>
          </details>
        </section>
        <aside className="official-checks">
          <span className="eyebrow">团队手动验收</span>
          <h2>按设备记录检查结果</h2>
          <div className="model-tabs" role="group" aria-label="检查设备型号">
            {["T8171", "T8214"].map((m) => (
              <button
                key={m}
                aria-pressed={model === m}
                onClick={() => setModel(m)}
              >
                {m}
                <small>{m === "T8171" ? "云台摄像头" : "门铃"}</small>
              </button>
            ))}
          </div>
          <label>
            本次检查设备 SN
            <input
              value={serial}
              placeholder={`${model}…`}
              onChange={(e) => setSerial(e.target.value)}
            />
          </label>
          {checks.map(([id, title, detail], index) => (
            <details key={id} className="hardware-check">
              <summary>
                <span>
                  {String(index + 1).padStart(2, "0")} · {title}
                </span>
                <small>{results[`${stateKey}:${id}`] || "未测试"}</small>
              </summary>
              <p>{detail}</p>
              <select
                aria-label={`${title}检查结果`}
                value={results[`${stateKey}:${id}`] || "未测试"}
                onChange={(e) =>
                  setResults({
                    ...results,
                    [`${stateKey}:${id}`]: e.target.value,
                  })
                }
              >
                {["未测试", "通过", "失败", "设备不支持", "转原生检查"].map(
                  (v) => (
                    <option key={v}>{v}</option>
                  ),
                )}
              </select>
            </details>
          ))}
          <label>
            测试环境与现象
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="网络、固件、失败现象；请勿填写 Token 或 Wi-Fi 密码"
            />
          </label>
          <button onClick={download}>下载本设备检查记录</button>
          <p className="subtle-note">
            检查结果由测试人员填写，切换工作区前可导出；没有自动判定硬件通过。
          </p>
        </aside>
      </div>
    </div>
  );
}
