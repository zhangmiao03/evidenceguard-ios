import { useEffect, useRef, useState } from "react";
import { api, type Capture, type Device, type Run } from "./api";
import { authenticate, clearSDKCredentials, emptyAuth, type Auth } from "./sdk";
import { LiveView } from "./LiveView";
import { OfficialWorkspace } from "./OfficialWorkspace";

function ImageEvidence({ path, alt }: { path: string; alt: string }) {
  const [url, setURL] = useState("");
  useEffect(() => {
    setURL("");
    let alive = true,
      resource = "";
    void api
      .media(path)
      .then((value) => {
        resource = value;
        if (alive) setURL(value);
        else URL.revokeObjectURL(value);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (resource) URL.revokeObjectURL(resource);
    };
  }, [path]);
  return url ? (
    <img className="evidence-image" src={url} alt={alt} />
  ) : (
    <div className="image-unavailable">图片待读取</div>
  );
}

export default function App() {
  const [token, setToken] = useState("");
  const [officialMode, setOfficialMode] = useState(false);
  const [switching, setSwitching] = useState(false);
  const stopLive = useRef<(() => Promise<void>) | null>(null);
  const [connected, setConnected] = useState(false);
  const [cloudOnline, setCloudOnline] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selected, setSelected] = useState("");
  const [auth, setAuth] = useState<Auth>(emptyAuth);
  const [integration, setIntegration] = useState<unknown>(null);
  const [settings, setSettings] = useState(false);
  const [live, setLive] = useState<Device | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [sn, setSN] = useState("");
  const [name, setName] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [sending, setSending] = useState(false);
  const [capture, setCapture] = useState<Capture | null>(null);
  const [tab, setTab] = useState("devices");
  const [evidence, setEvidence] = useState<
    { id: string; reason: string; imageUrl?: string; deviceName?: string }[]
  >([]);
  const conversation = useRef("");
  const generation = useRef(0);
  const activeRun = useRef("");
  const modal = useRef<HTMLElement>(null);
  const device = devices.find((d) => d.id === selected);
  const refresh = async () => {
    const all = await api.request<Device[]>("/api/devices");
    setDevices(all);
    setSelected((old) => old || all[0]?.id || "");
    const bootstrap = await api.request<{ evidence: typeof evidence }>(
      "/api/bootstrap",
    );
    const captures =
      await api.request<(Capture & { deviceName: string })[]>("/api/captures");
    setEvidence([...captures, ...bootstrap.evidence]);
    setCloudOnline(true);
  };
  useEffect(() => {
    if (!connected || officialMode) return;
    const timer = setInterval(
      () => void refresh().catch(() => setCloudOnline(false)),
      5000,
    );
    return () => clearInterval(timer);
  }, [connected, officialMode]);
  useEffect(() => {
    if (!settings) return;
    const previous = document.activeElement as HTMLElement | null;
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
  const login = () =>
    action(async () => {
      if (Object.values(auth).some((v) => !v.trim()))
        throw new Error("请填写完整的官方 Web 账号参数");
      setLive(null);
      setIntegration(await authenticate(auth));
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
      chooseDevice(all[0].id);
      setSN("");
      setName("");
      setSettings(false);
    });
  const ask = async (text = message) => {
    if (!text.trim() || sending) return;
    if (!device) {
      setError("请先选择设备");
      return;
    }
    setSending(true);
    setError("");
    setMessage("");
    const current = generation.current;
    try {
      if (!conversation.current) {
        const c = await api.request<{ id: string }>(
          "/api/agent/conversations",
          { requestId: crypto.randomUUID() },
        );
        if (current !== generation.current) return;
        conversation.current = c.id;
      }
      let run = await api.request<Run>("/api/agent/runs", {
        message: text,
        conversationId: conversation.current,
        requestId: crypto.randomUUID(),
        cameraId: device.id,
        executionMode: "live",
      });
      if (current !== generation.current) {
        void api.request(`/api/runs/${run.id}/cancel`, {}).catch(() => {});
        return;
      }
      activeRun.current = run.id;
      setRuns((old) => [...old, run]);
      while (
        ["queued", "running"].includes(run.status) &&
        current === generation.current
      ) {
        await new Promise((r) => setTimeout(r, 1000));
        run = await api.request<Run>(`/api/runs/${run.id}`);
        if (current === generation.current)
          setRuns((old) =>
            old.map((item) => (item.id === run.id ? run : item)),
          );
      }
    } catch (e) {
      if (current === generation.current)
        setError(e instanceof Error ? e.message : "Agent 暂不可用");
    } finally {
      if (current === generation.current) {
        setSending(false);
        activeRun.current = "";
      }
    }
  };
  const chooseDevice = (id: string) => {
    if (id !== selected) {
      if (activeRun.current)
        void api
          .request(`/api/runs/${activeRun.current}/cancel`, {})
          .catch(() => {});
      generation.current++;
      activeRun.current = "";
      conversation.current = "";
      setRuns([]);
      setSending(false);
      setLive(null);
      setReady(false);
      setCapture(null);
      setMessage("");
    }
    setSelected(id);
  };
  const logout = () => {
    if (activeRun.current)
      void api
        .request(`/api/runs/${activeRun.current}/cancel`, {})
        .catch(() => {});
    generation.current++;
    activeRun.current = "";
    setLive(null);
    setReady(false);
    setIntegration(null);
    setAuth(emptyAuth);
    clearSDKCredentials();
    setConnected(false);
    setToken("");
    setDevices([]);
    setSelected("");
    setEvidence([]);
    setRuns([]);
    setCapture(null);
    conversation.current = "";
    setSending(false);
    api.token = "";
  };

  const openOfficial = async () => {
    if (switching) return;
    setSwitching(true);
    setError("");
    try {
      generation.current++;
      if (activeRun.current)
        await api
          .request(`/api/runs/${activeRun.current}/cancel`, {})
          .catch(() => {});
      activeRun.current = "";
      setSending(false);
      await stopLive.current?.();
      stopLive.current = null;
      setLive(null);
      setReady(false);
      setCapture(null);
      setIntegration(null);
      clearSDKCredentials();
      setSettings(false);
      setOfficialMode(true);
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
          setLive(null);
          setReady(false);
          setIntegration(null);
          conversation.current = "";
          setRuns([]);
          if (connected) void refresh().catch(() => setCloudOnline(false));
        }}
      />
    );

  return (
    <div className="app-shell">
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
          {[
            ["devices", "◉", "设备工作台"],
            ["assistant", "✧", "AI 助手"],
            ["evidence", "▤", "证据库"],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              className={tab === id ? "nav-item active" : "nav-item"}
              onClick={() => {
                if (id === "evidence") {
                  setLive(null);
                  setReady(false);
                }
                setTab(id);
              }}
            >
              <span aria-hidden>{icon}</span>
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-icon">◇</div>
          <strong>你的画面，由你决定</strong>
          <p>开启直播后，Agent 仅在请求时获取一张新画面。</p>
          <button className="text-button" onClick={() => setSettings(true)}>
            连接与账号设置 ↗
          </button>
        </div>
        <div className="profile">
          <span className="avatar">EG</span>
          <div>
            团队工作台<small>iOS / Web 共用后端</small>
          </div>
          {connected && (
            <button className="text-button" onClick={logout}>
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
          <button disabled={switching} onClick={() => void openOfficial()}>
            {switching ? "正在停止直播与采集…" : "切换至官方 SDK ↗"}
          </button>
        </div>
        <header className="page-header">
          <div>
            <span className="eyebrow">EVIDENCE, BEFORE ANSWERS</span>
            <h1>
              {tab === "evidence"
                ? "每个结论，都能回看。"
                : tab === "assistant"
                  ? "让 AI 看见，再回答。"
                  : "在意的空间，一眼看清。"}
            </h1>
            <p>连接摄像头，查看现场，把有依据的观察交给你的 Agent。</p>
          </div>
          <button className="primary" onClick={() => setSettings(true)}>
            ＋ 接入设备
          </button>
        </header>
        {error && (
          <div role="alert" className="notice error">
            {error}
            <button
              className="text-button"
              onClick={() => setError("")}
              aria-label="关闭提示"
            >
              ×
            </button>
          </div>
        )}
        {!connected ? (
          <section className="access-card">
            <div className="large-symbol">◈</div>
            <span className="eyebrow">开始连接</span>
            <h2>欢迎来到你的设备工作台</h2>
            <p>输入团队访问令牌连接当前后端。本地未启用鉴权时，可直接进入。</p>
            <label>
              团队访问令牌
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
                placeholder="仅保留在本次页面会话"
              />
            </label>
            <button className="primary" disabled={busy} onClick={enter}>
              {busy ? "正在连接…" : "进入工作台 →"}
            </button>
            <div className="subtle-note">
              摄像头首次配网由原生 SDK 完成；网页连接已绑定且有权访问的设备。
            </div>
          </section>
        ) : (
          <>
            <div className="overview">
              <div>
                <span className={cloudOnline ? "dot" : "dot gray"} />
                {cloudOnline ? "云端已连接" : "云端连接中断"}
              </div>
              <div>
                <strong>{devices.length}</strong> 已登记设备
              </div>
              <div>
                <strong>{ready ? "1" : "0"}</strong> 当前画面输入
              </div>
              <span className="overview-note">
                {ready ? "前台会话正在提供新画面" : "未开启持续守护"}
              </span>
            </div>
            {tab === "evidence" ? (
              <section className="card">
                <div className="section-heading">
                  <h2>已保存的证据</h2>
                  <span>与 App 同步</span>
                </div>
                <div className="evidence-grid">
                  {evidence.length ? (
                    evidence.map((e) => (
                      <article className="evidence-tile" key={e.id}>
                        {e.imageUrl && (
                          <ImageEvidence
                            path={e.imageUrl}
                            alt="已保存的摄像头证据"
                          />
                        )}
                        <strong>{e.deviceName || "观察记录"}</strong>
                        <p>{e.reason}</p>
                      </article>
                    ))
                  ) : (
                    <div className="empty-inline">
                      暂时没有证据。设备事件和完成的观察会保留各自来源。
                    </div>
                  )}
                </div>
              </section>
            ) : (
              <div className="content-grid">
                <section className="device-column">
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
                        onClick={() => chooseDevice(d.id)}
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
                              : "待开启直播"}
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
                            ? `${device.model} · ${device.sn}`
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
                          setLive(null);
                          setReady(false);
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
                          disabled={busy}
                          onClick={() => {
                            if (!device || !integration) {
                              setSettings(true);
                              return;
                            }
                            setCapture(null);
                            setLive(device);
                          }}
                        >
                          {" "}
                          {device && integration
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
                            const c = await api.request<Capture>(
                              `/api/devices/${selected}/capture`,
                              {},
                            );
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
                <section className="card assistant-card">
                  <div className="section-heading">
                    <div className="assistant-title">
                      <span className="agent-icon">✧</span>
                      <div>
                        <h2>你的守护助手</h2>
                        <span>
                          {device
                            ? `当前关注 · ${device.name}`
                            : "选择设备后开始"}
                        </span>
                      </div>
                    </div>
                    <span className="pill blue">Agent</span>
                  </div>
                  <div className="messages" aria-live="polite">
                    {!runs.length ? (
                      <div className="assistant-welcome">
                        <div className="agent-orbit">✧</div>
                        <h3>现场有什么，问问我。</h3>
                        <p>
                          我会从正在播放的摄像头获取一张新画面，再依据实际内容回答。
                        </p>
                        {[
                          "现在画面里有什么？",
                          "门口的包裹还在吗？",
                          "看看客厅有什么活动",
                        ].map((q) => (
                          <button
                            key={q}
                            className="suggestion"
                            disabled={!device || sending}
                            onClick={() => void ask(q)}
                          >
                            {q}
                            <span>↗</span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      runs.map((run) => (
                        <div className="turn" key={run.id}>
                          <p className="user-message">{run.message}</p>
                          <div className="agent-message">
                            <span className="agent-icon small">✧</span>
                            <div>
                              {run.text ||
                                run.error ||
                                "正在获取信息与观察画面…"}
                              {run.captures?.map((c) => (
                                <div className="capture-receipt" key={c.id}>
                                  {c.imageUrl && (
                                    <ImageEvidence
                                      path={c.imageUrl}
                                      alt="Agent 本次观察图片"
                                    />
                                  )}
                                  <small>{c.reason}</small>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  <form
                    className="composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void ask();
                    }}
                  >
                    <label className="sr-only" htmlFor="question">
                      向 Agent 提问
                    </label>
                    <textarea
                      id="question"
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder="告诉我，你想看什么…"
                      rows={2}
                      maxLength={2000}
                    />
                    <div>
                      <small>{ready ? "● 新画面可用" : "○ 尚无实时输入"}</small>
                      <button
                        className="send-button"
                        aria-label="发送问题"
                        disabled={sending || !device || !message.trim()}
                      >
                        {sending ? "…" : "↑"}
                      </button>
                    </div>
                  </form>
                </section>
              </div>
            )}
          </>
        )}
        <footer>
          EvidenceGuard{" "}
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
                    onClick={() => {
                      setLive(null);
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
