import { useEffect, useRef, useState } from "react";
import { api, type Capture, type Device } from "./api";
import { observe } from "./telemetry";
import { newID } from "./browser-support";
import { authenticate, clearSDKCredentials, emptyAuth, type Auth } from "./sdk";
import { LiveView } from "./LiveView";
import { HardwarePanel } from "./HardwareTools";
import { CameraEvents } from "./CameraEvents";
import { mergeDevices } from "./device-overview.mjs";
import { OfficialWorkspace } from "./OfficialWorkspace";
import {
  Assistant,
  clearChatDrafts,
  type AssistantHandle,
  type AssistantIntent,
} from "./Assistant";
import { MemoryPage, SettingsPage } from "./Personal";
import { RecordingsPanel, TasksPage } from "./Skills";
import { ImageEvidence } from "./ProductUI";
import {
  emptyBootstrap,
  type Bootstrap,
  type Evidence,
  type Personal,
  type Skill,
  type Tab,
} from "./product-types";

const tabs: [Tab, string, string][] = [
  ["assistant", "✧", "助手"],
  ["cameras", "◉", "摄像头 Skill"],
  ["tasks", "☷", "任务"],
  ["memory", "◇", "记忆"],
  ["settings", "⚙", "设置"],
];
const headings: Record<Tab, [string, string]> = {
  assistant: [
    "今天，有什么想关注的？",
    "聊聊任务，回顾记忆，让每个答案都有依据。",
  ],
  cameras: [
    "让看见，成为一种能力。",
    "连接设备，查看现场，教摄像头一个新 Skill。",
  ],
  tasks: ["你关心的事，都在这里。", "查看运行结果、处理提醒，回看每一份证据。"],
  memory: ["记住你在意的。", "只保存你确认的内容，让每次对话更贴近你的需要。"],
  settings: ["按你的方式，安心守护。", "管理连接、提醒和数据使用范围。"],
};
export default function App() {
  const [token, setToken] = useState(""),
    [connected, setConnected] = useState(false),
    [cloudOnline, setCloudOnline] = useState(false);
  const [officialMode, setOfficialMode] = useState(false),
    [switching, setSwitching] = useState(false),
    [stoppingLive, setStoppingLive] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]),
    [selected, setSelected] = useState("");
  const [data, setData] = useState<Bootstrap>(emptyBootstrap),
    [evidence, setEvidence] = useState<Evidence[]>([]);
  const [auth, setAuth] = useState<Auth>(emptyAuth),
    [integration, setIntegration] = useState<unknown>(null),
    [settings, setSettings] = useState(false);
  const [live, setLive] = useState<Device | null>(null),
    [ready, setReady] = useState(false),
    [capture, setCapture] = useState<Capture | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [sn, setSN] = useState(""),
    [name, setName] = useState("");
  const [tab, setTab] = useState<Tab>("assistant"),
    [recordings, setRecordings] = useState(false),
    [selectedSkill, setSelectedSkill] = useState("");
  const [intent, setIntent] = useState<AssistantIntent | null>(null);
  const assistant = useRef<AssistantHandle>(null),
    stopLive = useRef<(() => Promise<void>) | null>(null),
    releaseLive = useRef<Promise<void> | null>(null);
  const connectionEpoch = useRef(0),
    generation = useRef(0),
    refreshSequence = useRef(0);
  const modal = useRef<HTMLElement>(null),
    settingsTrigger = useRef<HTMLElement | null>(null);
  const openSettings = (trigger: HTMLElement) => {
    settingsTrigger.current = trigger;
    setSettings(true);
  };
  const device = devices.find((d) => d.id === selected);
  const refresh = async () => {
    const epoch = connectionEpoch.current,
      sequence = ++refreshSequence.current;
    const [all, bootstrap, captures] = await Promise.all([
      api.request<Device[]>("/api/devices"),
      api.request<Bootstrap>("/api/bootstrap"),
      api.request<(Capture & { deviceName: string })[]>("/api/captures"),
    ]);
    if (
      epoch !== connectionEpoch.current ||
      sequence !== refreshSequence.current
    )
      return;
    const overview = mergeDevices(bootstrap.cameras || [], all);
    setDevices(overview);
    setSelected(old => overview.some(d => d.id === old) ? old : "");
    setData({
      ...emptyBootstrap,
      ...bootstrap,
      cameras: bootstrap.cameras || all,
    });
    setEvidence([...captures, ...(bootstrap.evidence || [])]);
    setCloudOnline(true);
  };
  const onPersonal = (value: Personal) => {
    refreshSequence.current++;
    setData((old) => ({ ...old, personal: value }));
  };
  useEffect(() => {
    if (!connected || officialMode) return;
    let alive = true,
      loading = false;
    const timer = setInterval(async () => {
      if (loading || document.hidden) return;
      loading = true;
      try {
        await refresh();
      } catch {
        if (alive) setCloudOnline(false);
      } finally {
        loading = false;
      }
    }, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [connected, officialMode]);
  useEffect(() => {
    if (!settings) return;
    const previous =
      settingsTrigger.current || (document.activeElement as HTMLElement | null);
    const root = modal.current;
    const controls = () =>
      Array.from(
        root?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input:not(:disabled)",
        ) || [],
      );
    controls()[0]?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setSettings(false);
      }
      if (event.key === "Tab") {
        const all = controls(),
          first = all[0],
          last = all[all.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [settings]);
  const action = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作未完成");
    } finally {
      setBusy(false);
    }
  };
  const enter = () =>
    action(async () => {
      api.token = token;
      await refresh();
      setConnected(true);
    });
  const endLive = (): Promise<void> => {
    if (releaseLive.current) return releaseLive.current;
    setStoppingLive(true);
    generation.current++;
    const stop = stopLive.current;
    const release = (async () => {
      try {
        if (stop) await assistant.current?.cancel();
        await stop?.();
      } finally {
        if (stopLive.current === stop) stopLive.current = null;
        setLive(null);
        setReady(false);
        setStoppingLive(false);
        releaseLive.current = null;
      }
    })();
    if (stop) releaseLive.current = release;
    return release;
  };
  const chooseDevice = async (id: string) => {
    if (id !== selected) {
      await assistant.current?.cancel();
      await endLive();
      setCapture(null);
    }
    setSelected(id);
  };
  const navigate = async (next: Tab) => {
    if (!["assistant", "cameras"].includes(next)) await endLive();
    setTab(next);
  };
  const beginAssistant = (prompt: string, skillId?: string) => {
    setIntent({ nonce: Date.now(), prompt, skillId });
    setTab("assistant");
  };
  const openSkill = (id: string) => {
    void endLive().then(() => {
      setSelectedSkill(id);
      setTab("tasks");
    });
  };
  const login = () =>
    action(async () => {
      if (Object.values(auth).some((v) => !v.trim()))
        throw new Error("请填写完整的官方 Web 账号参数");
      await endLive();
      const epoch = connectionEpoch.current;
      const result = await authenticate(auth);
      if (epoch === connectionEpoch.current) setIntegration(result);
    });
  const add = () =>
    action(async () => {
      if (!integration) throw new Error("请先完成官方 Web 鉴权");
      const serial = sn.trim().toUpperCase();
      if (!/^T(8171|8214)[A-Z0-9]{3,27}$/.test(serial))
        throw new Error("请输入 T8171 或 T8214 的完整设备序列号");
      const all = await api.request<Device[]>("/api/devices/import", {
        accountId: auth.eufyUserId,
        environment: "PR",
        platform: "web",
        devices: [
          {
            sn: serial,
            model: serial.slice(0, 5),
            name: name.trim() || "我的摄像头",
          },
        ],
      });
      await refresh();
      await chooseDevice(all[0].id);
      setSN("");
      setName("");
      setSettings(false);
      setTab("cameras");
    });
  const createDraft = () =>
    action(async () => {
      if (!selected) throw new Error("请先选择摄像头");
      const main = await api.request<{ id: string }>(
        "/api/agent/conversations/main",
        {},
      );
      const draft = await api.request<Skill>("/api/skills/drafts", {
        cameraId: selected,
        conversationId: main.id,
        prompt: "请选择画面中的观察对象并完善提醒条件",
      });
      await refresh();
      await endLive();
      setSelectedSkill(draft.id);
      setTab("tasks");
    });
  const logout = async () => {
    if (switching) return;
    setSwitching(true);
    connectionEpoch.current++;
    generation.current++;
    await assistant.current?.cancel(true);
    await endLive();
    clearChatDrafts();
    setIntegration(null);
    setAuth(emptyAuth);
    clearSDKCredentials();
    setConnected(false);
    setCloudOnline(false);
    setToken("");
    setDevices([]);
    setSelected("");
    setEvidence([]);
    setData(emptyBootstrap);
    setCapture(null);
    setIntent(null);
    setSelectedSkill("");
    setSettings(false);
    setRecordings(false);
    api.token = "";
    setSwitching(false);
  };
  const openOfficial = async () => {
    if (switching) return;
    setSwitching(true);
    setError("");
    try {
      connectionEpoch.current++;
      generation.current++;
      await assistant.current?.cancel(true);
      await endLive();
      setCapture(null);
      setIntegration(null);
      clearSDKCredentials();
      setSettings(false);
      setOfficialMode(true);
      observe({ name: "sdk.mode_changed", traceId: newID(), status: "official" }, api.token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "切换未完成，请重试");
    } finally {
      setSwitching(false);
    }
  };
  if (officialMode)
    return (
      <OfficialWorkspace
        token={api.token || token}
        defaults={{ ...auth, stationSn: device?.sn }}
        onReturn={() => {
          setOfficialMode(false);
          observe({ name: "sdk.mode_changed", traceId: newID(), status: "product" }, api.token);
          setLive(null);
          setReady(false);
          setIntegration(null);
          setIntent(null);
          if (connected) void refresh().catch(() => setCloudOnline(false));
        }}
      />
    );
  return (
    <div className="app-shell product-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="EvidenceGuard 首页">
          <span className="brand-mark">
            e<span />
          </span>
          <span>
            EvidenceGuard<small>让每一次看见，都有依据</small>
          </span>
        </a>
        <div className="workspace-label">家庭工作空间</div>
        <nav aria-label="主导航">
          {tabs.map(([id, icon, label]) => (
            <button
              key={id}
              className={tab === id ? "nav-item active" : "nav-item"}
              aria-current={tab === id ? "page" : undefined}
              disabled={switching || stoppingLive}
              onClick={() => void navigate(id)}
            >
              <span aria-hidden>{icon}</span>
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-icon">◇</div>
          <strong>你的画面，由你决定</strong>
          <p>开启直播后，Agent 仅在请求时获取新画面。</p>
          <button
            className="text-button"
            onClick={(e) => openSettings(e.currentTarget)}
          >
            连接与账号设置 ↗
          </button>
        </div>
        <div className="profile">
          <span className="avatar">EG</span>
          <div>
            团队工作台<small>iOS / Web 共用后端</small>
          </div>
          {connected && (
            <button
              className="text-button"
              disabled={busy || switching || stoppingLive}
              onClick={() => void logout()}
            >
              退出
            </button>
          )}
        </div>
      </aside>
      <main>
        <div className="workspace-switch" aria-label="版本与工作区切换">
          <span>
            <i className="dot" /> EvidenceGuard 工作区
          </span>
          {connected && (
            <button
              className="mobile-logout"
              disabled={busy || switching || stoppingLive}
              onClick={() => void logout()}
            >
              退出
            </button>
          )}
          <button
            disabled={switching || busy || stoppingLive}
            onClick={() => void openOfficial()}
          >
            {switching ? "正在停止直播与采集…" : "切换至官方 SDK ↗"}
          </button>
        </div>
        <header className="page-header">
          <div>
            <span className="eyebrow">EVIDENCE, BEFORE ANSWERS</span>
            <h1>{headings[tab][0]}</h1>
            <p>{headings[tab][1]}</p>
          </div>
          <button
            className="primary"
            onClick={(e) => openSettings(e.currentTarget)}
          >
            ＋ 接入设备
          </button>
        </header>
        {error && (
          <div role="alert" className="notice error">
            {error}
            <button
              className="text-button"
              aria-label="关闭提示"
              onClick={() => setError("")}
            >
              ×
            </button>
          </div>
        )}
        {!connected ? (
          <section className="access-card">
            <div className="large-symbol">◇</div>
            <h2>欢迎来到你的守护工作台</h2>
            <p>连接团队服务，继续对话、管理任务与记忆，或接入真实摄像头。</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void enter();
              }}
            >
              <label>
                团队访问令牌
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="本地未启用鉴权时可留空"
                />
              </label>
              <button className="primary" disabled={busy}>
                {busy ? "正在连接…" : "进入工作台 →"}
              </button>
            </form>
            <small>
              令牌仅在当前页面内存中保存。刷新后需重新连接，已保存的会话与设置仍可恢复。
            </small>
          </section>
        ) : (
          <>
            <div className="overview-bar">
              <span className="connection-state">
                <i className={cloudOnline ? "dot" : "dot muted"} />
                {cloudOnline ? "云端已连接" : "等待云端连接"}
              </span>
              <div>
                <strong>{devices.length}</strong> 已登记设备
              </div>
              <div>
                <strong>
                  {data.skills.filter((s) => s.status === "active").length}
                </strong>{" "}
                运行中 Skill
              </div>
              <span className="overview-note">
                {ready ? "前台会话正在提供新画面" : "未开启前台取样"}
              </span>
            </div>
            <div
              className={
                tab === "assistant" && live
                  ? "content-grid product-content"
                  : "product-content"
              }
              hidden={!["assistant", "cameras"].includes(tab)}
            >
              <section
                className="device-column"
                hidden={tab !== "cameras" && !(tab === "assistant" && !!live)}
              >
                <div className="section-heading">
                  <h2>
                    我的设备 <span className="count">{devices.length}</span>
                  </h2>
                  <button
                    className="text-button"
                    onClick={() => void action(refresh)}
                  >
                    刷新 ↻
                  </button>
                </div>
                <div className="device-tabs">
                  {devices.map((d) => (
                    <button
                      key={d.id}
                      disabled={switching || stoppingLive}
                      onClick={() => void chooseDevice(d.id)}
                      className={
                        d.id === selected
                          ? "device-chip selected"
                          : "device-chip"
                      }
                    >
                      <span className="camera-icon">◉</span>
                      <span>
                        <strong>{d.name}</strong>
                        <small>
                          {d.model} ·{" "}
                          {d.connection === "online"
                            ? "画面输入可用"
                            : d.connection === "event_only" ? "事件已登记" : "待开启直播"}
                        </small>
                      </span>
                    </button>
                  ))}
                </div>
                <div className="card video-card">
                  <div className="section-heading">
                    <div>
                      <h2>{device?.name || "连接你的第一台摄像头"}</h2>
                      <span>
                        {device
                          ? `${device.model} · ${device.sn || "仅事件身份，直播需同步官方账号"}`
                          : "支持 T8171 云台摄像头与 T8214 双摄门铃"}
                      </span>
                    </div>
                    <span className="pill">
                      {live ? "前台直播" : "尚未开流"}
                    </span>
                  </div>
                  {live && integration ? (
                    <LiveView
                      key={live.id}
                      device={live}
                      integration={integration}
                      onClose={() => {
                        void endLive();
                      }}
                      onStatus={setReady}
                      registerStop={(stop) => {
                        stopLive.current = stop;
                      }}
                    />
                  ) : (
                    <div className="video-empty">
                      <div className="lens">
                        <div />
                      </div>
                      <h3>
                        {device ? "现在，看看现场" : "把你的空间连接起来"}
                      </h3>
                      <p>
                        {device
                          ? "实时画面通过官方媒体链路播放。"
                          : "完成官方鉴权，导入账号下的设备，即可开始。"}
                      </p>
                      <button
                        className="primary"
                        disabled={busy || switching || stoppingLive}
                        onClick={async (e) => {
                          if (!device?.sn || !integration) {
                            openSettings(e.currentTarget);
                            return;
                          }
                          await endLive();
                          setCapture(null);
                          setLive(device);
                        }}
                      >
                        {" "}
                        {device?.sn && integration
                          ? "▶ 开始直播"
                          : "连接官方设备 →"}
                      </button>
                    </div>
                  )}
                  <div className="video-actions">
                    <span>◇ 画面不会自动上传</span>
                    <button
                      className="secondary"
                      disabled={!ready || busy}
                      onClick={() =>
                        void action(async () => {
                          const current = generation.current;
                          const c = await api.request<Capture>(
                            `/api/devices/${selected}/capture`,
                            {},
                          );
                          if (current !== generation.current) return;
                          setCapture(c);
                          if (c.status !== "completed")
                            throw new Error(c.reason);
                        })
                      }
                    >
                      获取一张新画面
                    </button>
                  </div>
                </div>
                {capture?.imageUrl && (
                  <div className="card capture-card">
                    <ImageEvidence
                      path={capture.imageUrl}
                      alt="本次请求后的直播取样"
                    />
                    <div>
                      <strong>本次新画面已收到</strong>
                      <p>{capture.reason}</p>
                      <small>
                        设备拍摄时间未知 · 客户端取样{" "}
                        {capture.sampledAt
                          ? new Date(
                              capture.sampledAt * 1000,
                            ).toLocaleTimeString()
                          : "—"}
                      </small>
                    </div>
                  </div>
                )}
                <div className="button-row camera-tools">
                  <button
                    className="primary"
                    disabled={!selected || busy || switching}
                    onClick={() => void createDraft()}
                  >
                    圈选守护 · 创建 Skill
                  </button>
                  <button
                    className="secondary"
                    onClick={() => setRecordings(true)}
                  >
                    录像资料
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      beginAssistant(
                        "请查看当前摄像头的新画面，说明你看到了什么。",
                      )
                    }
                  >
                    让助手看看 →
                  </button>
                </div>
                {tab === "cameras" && <CameraEvents devices={devices} initial={data.cameraEvents} />}
                {tab === "cameras" && device && <HardwarePanel key={device.id} deviceID={device.id} />}
                <div className="context-card">
                  <span>01</span>
                  <div>
                    <strong>从看见，到有依据的回答</strong>
                    <p>
                      选择设备并打开直播。提问后，Agent
                      会请求新画面；没有输入时会说明原因。
                    </p>
                  </div>
                </div>
              </section>
              <Assistant
                ref={assistant}
                active={tab === "assistant"}
                data={data}
                selected={selected}
                ready={ready}
                intent={intent}
                onCamera={chooseDevice}
                onSkill={openSkill}
                onRefresh={refresh}
                onPersonal={onPersonal}
              />
            </div>
            <div hidden={tab !== "tasks"}>
              <TasksPage
                data={data}
                evidence={evidence}
                selectedSkill={selectedSkill}
                onSkill={setSelectedSkill}
                onRefresh={refresh}
                onAssistant={beginAssistant}
                onSettings={() => void navigate("settings")}
              />
            </div>
            <div hidden={tab !== "memory"}>
              <MemoryPage personal={data.personal} onUpdate={onPersonal} />
            </div>
            <div hidden={tab !== "settings"}>
              <SettingsPage
                data={data}
                online={cloudOnline}
                onUpdate={onPersonal}
                onConnection={openSettings}
                onOfficial={() => void openOfficial()}
                onAssistant={() => beginAssistant("")}
                onSkill={openSkill}
              />
            </div>
            {recordings && (
              <RecordingsPanel
                data={data}
                onClose={() => setRecordings(false)}
                onRefresh={refresh}
              />
            )}
          </>
        )}
        <footer>
          EvidenceGuard Web 0.2
          <span>设备原生录像、前台直播与 Agent 观察分别运行。</span>
        </footer>
      </main>
      {settings && (
        <div className="modal-backdrop">
          <section
            ref={modal}
            className="settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
          >
            <div className="section-heading">
              <div>
                <span className="eyebrow">DEVICE CONNECTION</span>
                <h2 id="settings-title">连接你的设备</h2>
              </div>
              <button
                className="text-button"
                onClick={() => setSettings(false)}
                aria-label="关闭设置"
              >
                ✕
              </button>
            </div>
            {!connected ? (
              <p>请先进入工作台连接后端。</p>
            ) : (
              <>
                <p className="subtle-note">
                  使用主办方提供的 Web
                  鉴权参数。参数只保留在页面内存；这是受信任团队的接入工作台。
                </p>
                <div className="form-grid">
                  {Object.keys(emptyAuth).map((k) => (
                    <label key={k}>
                      {
                        {
                          appName: "App Name",
                          clientId: "Client ID",
                          clientSecret: "Client Secret",
                          presetKey: "Preset Key",
                          eufyUserId: "Eufy User ID",
                          accountUuid: "Account UUID",
                        }[k]
                      }
                      <input
                        type={
                          ["clientSecret", "presetKey"].includes(k)
                            ? "password"
                            : "text"
                        }
                        autoComplete="off"
                        disabled={!!integration}
                        value={auth[k as keyof Auth]}
                        onChange={(e) =>
                          setAuth((old) => ({ ...old, [k]: e.target.value }))
                        }
                      />
                    </label>
                  ))}
                </div>
                <button
                  className="primary"
                  disabled={busy || !!integration}
                  onClick={login}
                >
                  {integration
                    ? "✓ 官方鉴权完成"
                    : busy
                      ? "正在连接…"
                      : "连接官方服务"}
                </button>
                <div className="form-divider" />
                <h3>导入已绑定设备</h3>
                <p className="subtle-note">
                  输入账号下已绑定设备的序列号；登记不代表重新绑定，取流成功后才显示画面可用。
                </p>
                <div className="form-grid">
                  <label>
                    设备序列号
                    <input
                      value={sn}
                      onChange={(e) => setSN(e.target.value)}
                      placeholder="T8171… / T8214…"
                    />
                  </label>
                  <label>
                    名称与位置
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="例如：客厅摄像头"
                      maxLength={80}
                    />
                  </label>
                </div>
                <button
                  className="primary"
                  disabled={busy || !integration}
                  onClick={add}
                >
                  导入设备
                </button>
                {integration && (
                  <button
                    className="text-button"
                    disabled={busy || switching || stoppingLive}
                    onClick={async () => {
                      connectionEpoch.current++;
                      await endLive();
                      setIntegration(null);
                      setAuth(emptyAuth);
                      clearSDKCredentials();
                    }}
                  >
                    断开官方账号
                  </button>
                )}
              </>
            )}
            {error && (
              <p role="alert" className="notice error">
                {error}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
