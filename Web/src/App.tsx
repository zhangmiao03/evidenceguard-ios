import { useCallback, useEffect, useRef, useState } from "react";
import {
  Home,
  Layers,
  Sparkles,
  FileVideo,
  Settings,
  Camera as CameraIcon,
  ArrowUp,
  ArrowLeft,
  Plus,
  RefreshCw,
} from "lucide-react";
import { api, running, statusLabel } from "./api";
import { SkillEditor } from "./SkillEditor";
import { SDKPreview } from "./SDKPreview";
import type { Bootstrap, Run, Skill } from "./types";
const tabs = [
  { id: "home", label: "首页", icon: Home },
  { id: "skills", label: "Skill", icon: Layers },
  { id: "ai", label: "AI 助手", icon: Sparkles },
  { id: "evidence", label: "录像与证据", icon: FileVideo },
  { id: "settings", label: "接入与设置", icon: Settings },
];
function conversationID(mode: string) {
  const key = `evidenceguard.web.conversation.${mode}`;
  let value = localStorage.getItem(key);
  if (!value) {
    value = `web-${mode}-${crypto.randomUUID()}`;
    localStorage.setItem(key, value);
  }
  return value;
}
function Video({ url, seek = 0 }: { url: string; seek?: number }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current?.readyState) ref.current.currentTime = seek;
  }, [seek]);
  return (
    <video
      ref={ref}
      controls
      preload="metadata"
      src={url}
      onLoadedMetadata={(e) => {
        e.currentTarget.currentTime = Math.max(0, seek);
      }}
    />
  );
}
export function App() {
  const [tab, setTab] = useState("home");
  const [data, setData] = useState<Bootstrap | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<Skill | null>(null);
  const [sdk, setSDK] = useState(false);
  const [cameraID, setCameraID] = useState("cam-a");
  const [mode, setMode] = useState("live");
  const [skillContext, setSkillContext] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [message, setMessage] = useState("");
  const [period, setPeriod] = useState("all");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [uploadTime, setUploadTime] = useState("");
  const [uploading, setUploading] = useState(false);
  const conv = skillContext
    ? `web-skill-${skillContext}`
    : conversationID(mode);
  const draftKey = `evidenceguard.web.draft.${conv}`;
  const currentRun = runs.find((r) => running(r.status));
  const selectedCamera = data?.cameras.find((c) => c.id === cameraID);
  const conversationDrafts =
    data?.skills.filter(
      (s) => s.status === "draft" && s.originConversationId === conv,
    ) || [];
  const bottom = useRef<HTMLDivElement>(null);
  const refresh = useCallback(async () => {
    try {
      setData(await api<Bootstrap>("/api/bootstrap"));
      setConnected(true);
    } catch {
      setConnected(false);
    }
  }, []);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const value = await api<Bootstrap>("/api/bootstrap");
        if (!cancelled) {
          setData(value);
          setConnected(true);
        }
      } catch {
        if (!cancelled) setConnected(false);
      }
    };
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    setMessage(localStorage.getItem(draftKey) || "");
  }, [draftKey]);
  useEffect(() => {
    let cancelled = false;
    setRuns([]);
    const load = async () => {
      try {
        const value = await api<Run[]>(`/api/agent/conversations/${conv}`);
        if (!cancelled) setRuns(value);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [conv]);
  useEffect(() => {
    if (tab === "ai") {
      const messages = bottom.current?.parentElement;
      messages?.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
    }
  }, [runs.length, currentRun?.status, tab]);
  function write(text: string) {
    setMessage(text);
    localStorage.setItem(draftKey, text);
  }
  function navigate(next: string) {
    setEditor(null);
    setSDK(false);
    setTab(next);
    setError("");
  }
  async function act(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function openAI(skill?: Skill) {
    setEditor(null);
    setTab("ai");
    setSDK(false);
    setMode("live");
    setSkillContext(skill?.id || null);
    if (skill) setCameraID(skill.target.cameraId);
  }
  async function createDraft() {
    await act(async () => {
      const value = await api<Skill>("/api/skills/drafts", "POST", {
        cameraId: cameraID,
        conversationId: conv,
        prompt: message.trim() || "请选择画面中的观察对象并完善提醒条件",
      });
      setEditor(value);
    });
  }
  async function send() {
    if (!message.trim() || busy || currentRun) return;
    const text = message.trim();
    await act(async () => {
      const historyFilter =
        mode === "history"
          ? {
              period,
              ...(period === "custom"
                ? {
                    startAt: new Date(customStart).getTime() / 1000,
                    endAt: new Date(customEnd).getTime() / 1000,
                  }
                : {}),
            }
          : undefined;
      if (
        period === "custom" &&
        mode === "history" &&
        (!customStart ||
          !customEnd ||
          new Date(customEnd) <= new Date(customStart))
      )
        throw new Error("请选择有效的历史录像起止时间。");
      const value = await api<Run>("/api/agent/runs", "POST", {
        message: text,
        conversationId: conv,
        requestId: `run-${crypto.randomUUID()}`,
        skillId: skillContext,
        cameraId: cameraID,
        executionMode: mode,
        historyFilter,
      });
      setRuns((previous) => [...previous, value]);
      write("");
    });
  }
  async function upload(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      if (file.size > 150_000_000 || !file.size)
        throw new Error("请选择不超过 150 MB 的录像。");
      const params = new URLSearchParams({
        cameraId: cameraID,
        title: file.name,
      });
      if (uploadTime)
        params.set("recordedAt", String(new Date(uploadTime).getTime() / 1000));
      const response = await fetch(`/api/recordings?${params}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      if (!response.ok) {
        const value = await response.json();
        throw new Error(
          typeof value.detail === "string" ? value.detail : "上传失败",
        );
      }
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  const skillCards = (skills: Skill[]) =>
    skills.length ? (
      skills.map((s) => (
        <article className="skill-row" key={s.id}>
          <div className="skill-symbol">
            <Layers />
          </div>
          <div className="grow">
            <h3>{s.name}</h3>
            <p>{s.capability?.label || s.resultReason}</p>
            <span className={`badge ${s.status === "active" ? "green" : ""}`}>
              {statusLabel(s.status)}
            </span>
          </div>
          <button onClick={() => setEditor(structuredClone(s))}>
            {s.status === "draft" ? "编辑草案" : "查看"}
          </button>
          <button className="subtle" onClick={() => openAI(s)}>
            问 AI
          </button>
          {s.status === "active" && (
            <button
              disabled={busy || !connected}
              onClick={() =>
                void act(async () => {
                  await api(`/api/skills/${s.id}/lifecycle`, "POST", {
                    action: "pause",
                  });
                })
              }
            >
              暂停
            </button>
          )}
          {s.status === "paused" && (
            <button
              disabled={busy || !connected}
              onClick={() =>
                void act(async () => {
                  await api(`/api/skills/${s.id}/lifecycle`, "POST", {
                    action: "resume",
                  });
                })
              }
            >
              恢复
            </button>
          )}
        </article>
      ))
    ) : (
      <div className="empty">
        还没有守护任务。先和 AI 说明需求，再检查草案。
      </div>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("home");
          }}
        >
          <div className="brand-mark">
            <Layers />
          </div>
          <span>
            EvidenceGuard<small>Visual Skill</small>
          </span>
        </a>
        <nav>
          {tabs.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? "active" : ""}
              onClick={() => navigate(t.id)}
            >
              <t.icon size={20} />
              {t.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className={`dot ${connected ? "online" : ""}`} />
          {connected ? "云端已连接" : "等待云端连接"}
          <small>每台摄像头 · 一个实时任务</small>
        </div>
      </aside>
      <main>
        {!connected && (
          <div className="notice error" role="status">
            云端未连接，已有记录不代表当前状态。请启动 Cloud 服务或检查 /api
            代理。<button onClick={() => void refresh()}>重新检查</button>
          </div>
        )}
        {error && (
          <div className="notice error" role="alert">
            {error}
            <button className="subtle" onClick={() => setError("")}>
              关闭
            </button>
          </div>
        )}
        {editor && data ? (
          <SkillEditor
            key={editor.id}
            initial={editor}
            data={data}
            close={() => setEditor(null)}
            changed={refresh}
          />
        ) : sdk ? (
          <>
            <button className="back" onClick={() => setSDK(false)}>
              <ArrowLeft size={18} />
              返回设置
            </button>
            <SDKPreview />
          </>
        ) : (
          <>
            {tab === "home" && (
              <>
                <header className="home-hero">
                  <div>
                    <span className="eyebrow">用 AI 守护你在乎的每一刻</span>
                    <h1>EvidenceGuard</h1>
                    <p>从看见，到安心。</p>
                  </div>
                  <img src="/home-hero.jpg" alt="明亮的居家场景" />
                </header>
                <section className="card overview">
                  <div className="toolbar">
                    <h2>我关心的事</h2>
                    <span className="muted">
                      {connected ? "连接状态来自云端" : "等待连接"}
                    </span>
                  </div>
                  <div className="health">
                    <div className="health-orb" />
                    <div>
                      <h2>
                        {!connected
                          ? "等待云端连接"
                          : data?.summary.openAlerts
                            ? "有事项需要关注"
                            : data?.summary.activeSkills
                              ? "守护运行中"
                              : "还没有运行任务"}
                      </h2>
                      <p>
                        {!connected
                          ? "连接后查看任务和设备"
                          : data?.summary.unknownSkills
                            ? `${data.summary.unknownSkills} 个任务暂时无法确认`
                            : "查看任务状态，保留每次判断的依据"}
                      </p>
                    </div>
                  </div>
                  <div className="stats">
                    <button onClick={() => navigate("settings")}>
                      <CameraIcon />
                      <strong>
                        {connected
                          ? data?.cameras.filter(
                              (c) => c.connection === "online",
                            ).length
                          : "—"}
                      </strong>
                      <span>在线设备</span>
                    </button>
                    <button onClick={() => navigate("skills")}>
                      <Layers />
                      <strong>
                        {connected ? data?.summary.activeSkills : "—"}
                      </strong>
                      <span>运行中 Skill</span>
                    </button>
                    <button onClick={() => navigate("evidence")}>
                      <FileVideo />
                      <strong>
                        {connected ? data?.summary.openAlerts : "—"}
                      </strong>
                      <span>待关注</span>
                    </button>
                  </div>
                </section>
                <div className="toolbar section-title">
                  <h2>正在守护的 Skill</h2>
                  <button className="subtle" onClick={() => navigate("skills")}>
                    查看全部 →
                  </button>
                </div>
                {skillCards(
                  data?.skills.filter((s) => s.status === "active") || [],
                )}
                <button className="teach-card" onClick={() => openAI()}>
                  <Sparkles />
                  <span>
                    <strong>教 AI 新技能</strong>
                    <small>告诉 AI 你关心的场景，检查能力后再启用</small>
                  </span>
                  <ArrowUp />
                </button>
              </>
            )}
            {tab === "skills" && (
              <>
                <div className="page-title">
                  <div>
                    <h1>我的 Skill</h1>
                    <p>草案、试跑和运行状态</p>
                  </div>
                  <button className="primary" onClick={() => openAI()}>
                    <Plus size={18} />
                    创建新技能
                  </button>
                </div>
                {skillCards(data?.skills || [])}
              </>
            )}
            {tab === "ai" && (
              <>
                <div className="page-title">
                  <div>
                    <h1>AI 助手</h1>
                    <p>
                      {skillContext
                        ? `当前任务：${data?.skills.find((s) => s.id === skillContext)?.name || skillContext}`
                        : "告诉我你关心什么"}
                    </p>
                  </div>
                  {skillContext && (
                    <button onClick={() => setSkillContext(null)}>
                      返回通用对话
                    </button>
                  )}
                </div>
                <div className="chat-shell">
                  <div className="chat-messages">
                    {runs.length === 0 && (
                      <div className="chat-welcome">
                        <div className="ai-symbol">
                          <Sparkles />
                        </div>
                        <h2>
                          {mode === "history"
                            ? "看看过去发生了什么"
                            : "让摄像头理解你的关注"}
                        </h2>
                        <p>
                          {mode === "history"
                            ? "从已入库录像检索，播放原片核验。"
                            : "描述场景后生成草案，圈选、试跑、确认。"}
                        </p>
                        <button
                          onClick={() =>
                            write(
                              mode === "history"
                                ? "包裹什么时候被拿走？"
                                : "包裹离开门廊区域时提醒我",
                            )
                          }
                        >
                          {mode === "history"
                            ? "查找包裹拿取录像"
                            : "看住门口的包裹"}
                        </button>
                      </div>
                    )}
                    {runs.map((r) => (
                      <div className="exchange" key={r.id}>
                        <div className="bubble user">{r.message}</div>
                        <div className="bubble assistant">
                          <span className="muted">
                            {running(r.status)
                              ? "AI 正在处理…"
                              : "EvidenceGuard"}
                          </span>
                          <p>{r.text || r.error || statusLabel(r.status)}</p>
                          {r.captures?.map((c) => (
                            <div key={c.id} className="capture">
                              {c.imageUrl && (
                                <img
                                  src={c.imageUrl}
                                  alt={`${c.cameraId} 本次观察画面`}
                                />
                              )}
                              <p className="muted">{c.reason}</p>
                            </div>
                          ))}
                          {r.draft && (
                            <button
                              className="draft-card"
                              disabled={!connected}
                              onClick={() => {
                                const latest = data?.skills.find(
                                  (s) => s.id === r.draft!.id,
                                );
                                if (latest) setEditor(structuredClone(latest));
                                else
                                  setError("草案当前不可读取，请刷新后重试。");
                              }}
                            >
                              <Layers />
                              <span>
                                <strong>
                                  {data?.skills.find(
                                    (s) => s.id === r.draft!.id,
                                  )?.name || r.draft.name}
                                </strong>
                                <small>打开草案 · 圈选与验收 →</small>
                              </span>
                            </button>
                          )}
                          {r.videos?.map((v) => (
                            <div className="video-hit" key={v.id}>
                              <strong>{v.title}</strong>
                              <Video url={v.playbackUrl} seek={v.seekSeconds} />
                              <p>{v.summary}</p>
                              <p className="muted">
                                {v.limitation} · 定位 {v.seekSeconds.toFixed(1)}{" "}
                                s
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                    <div ref={bottom} />
                  </div>
                  {mode === "live" && conversationDrafts.length > 0 && (
                    <div className="conversation-drafts">
                      {conversationDrafts.map((s) => (
                        <button
                          key={s.id}
                          className="draft-card"
                          onClick={() => setEditor(structuredClone(s))}
                        >
                          <Layers size={18} />
                          <span>
                            <strong>{s.name}</strong>
                            <small>当前对话草案 · 继续圈选编辑 →</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="composer">
                    <div className="toolbar">
                      <div className="segmented">
                        <button
                          disabled={!!currentRun || busy || !!skillContext}
                          className={mode === "live" ? "selected" : ""}
                          onClick={() => setMode("live")}
                        >
                          实时守护
                        </button>
                        <button
                          disabled={!!currentRun || busy || !!skillContext}
                          className={mode === "history" ? "selected" : ""}
                          onClick={() => setMode("history")}
                        >
                          历史回顾
                        </button>
                      </div>
                      <label className="inline-label">
                        <CameraIcon size={16} />
                        <select
                          aria-label="选择摄像头"
                          disabled={!!currentRun || busy || !!skillContext}
                          value={cameraID}
                          onChange={(e) => setCameraID(e.target.value)}
                        >
                          {data?.cameras.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {mode === "history" && (
                      <div className="history-filter">
                        <select
                          aria-label="历史时间范围"
                          value={period}
                          onChange={(e) => setPeriod(e.target.value)}
                        >
                          {[
                            ["all", "全部日期"],
                            ["today", "今天"],
                            ["yesterday", "昨天"],
                            ["last_24_hours", "过去 24 小时"],
                            ["custom", "自定义时间"],
                          ].map(([v, l]) => (
                            <option key={v} value={v}>
                              {l}
                            </option>
                          ))}
                        </select>
                        {period === "custom" && (
                          <>
                            <input
                              aria-label="起始时间"
                              type="datetime-local"
                              value={customStart}
                              onChange={(e) => setCustomStart(e.target.value)}
                            />
                            <input
                              aria-label="结束时间"
                              type="datetime-local"
                              value={customEnd}
                              onChange={(e) => setCustomEnd(e.target.value)}
                            />
                          </>
                        )}
                      </div>
                    )}
                    <div className="input-row">
                      <textarea
                        aria-label="和 AI 沟通"
                        placeholder="输入消息，和 AI 沟通…"
                        value={message}
                        maxLength={2000}
                        onChange={(e) => write(e.target.value)}
                        onKeyDown={(e) => {
                          if (
                            e.key === "Enter" &&
                            !e.shiftKey &&
                            !e.nativeEvent.isComposing
                          ) {
                            e.preventDefault();
                            void send();
                          }
                        }}
                      />
                      {currentRun ? (
                        <button
                          onClick={() =>
                            void act(async () => {
                              const cancelled = await api<Run>(
                                `/api/runs/${currentRun.id}/cancel`,
                                "POST",
                                {},
                              );
                              setRuns((prev) =>
                                prev.map((r) =>
                                  r.id === cancelled.id ? cancelled : r,
                                ),
                              );
                            })
                          }
                        >
                          停止
                        </button>
                      ) : (
                        <button
                          className="send"
                          aria-label="发送"
                          disabled={
                            busy ||
                            !connected ||
                            !data?.agent.ready ||
                            !message.trim()
                          }
                          onClick={() => void send()}
                        >
                          <ArrowUp />
                        </button>
                      )}
                    </div>
                    <div className="toolbar">
                      <small className="muted">
                        {mode === "history"
                          ? "只分析已存媒体，可与实时任务并行"
                          : "每台摄像头一个实时任务；启用前需验收"}
                      </small>
                      {mode === "live" && (
                        <button
                          className="subtle"
                          disabled={busy || !connected || !selectedCamera}
                          onClick={() => void createDraft()}
                        >
                          直接创建并圈选草案
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}
            {tab === "evidence" && (
              <>
                <div className="page-title">
                  <div>
                    <h1>录像与证据</h1>
                    <p>保留原片，核验 AI 的判断</p>
                  </div>
                  <button
                    className="subtle"
                    onClick={() => {
                      setMode("history");
                      setSkillContext(null);
                      setTab("ai");
                    }}
                  >
                    问 AI 查录像 →
                  </button>
                </div>
                <div className="card">
                  <h2>导入录像</h2>
                  <div className="upload-row">
                    <label>
                      录像所属摄像头
                      <select
                        value={cameraID}
                        onChange={(e) => setCameraID(e.target.value)}
                      >
                        {data?.cameras.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      实际拍摄起始时间（可空）
                      <input
                        type="datetime-local"
                        value={uploadTime}
                        onChange={(e) => setUploadTime(e.target.value)}
                      />
                    </label>
                    <label className="upload-button">
                      {uploading ? "正在上传…" : "选择视频 · 最大 150 MB"}
                      <input
                        type="file"
                        accept="video/*"
                        disabled={uploading || !connected || !selectedCamera}
                        onChange={(e) => {
                          void upload(e.target.files?.[0]);
                          e.target.value = "";
                        }}
                      />
                    </label>
                  </div>
                  <p className="muted">
                    未知拍摄时间留空，不用上传时刻替代。导入完成后由云端分段和建立索引。
                  </p>
                </div>
                <div className="media-grid">
                  {data?.recordings.map((r) => (
                    <article className="card" key={r.id}>
                      <div className="toolbar">
                        <h3>{r.title}</h3>
                        <span className="badge">{statusLabel(r.status)}</span>
                      </div>
                      <Video url={r.playbackUrl} />
                      <p className="muted">
                        {r.cameraId} · {r.duration?.toFixed(1) ?? "未知"} s ·{" "}
                        {r.recordedAt
                          ? new Date(r.recordedAt * 1000).toLocaleString()
                          : "拍摄时间未知"}
                      </p>
                      {r.error && <p className="error">{r.error}</p>}
                      {["failed", "stale", "interrupted"].includes(
                        r.status,
                      ) && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act(async () => {
                              await api(
                                `/api/recordings/${r.id}/index`,
                                "POST",
                                {},
                              );
                            })
                          }
                        >
                          重建索引
                        </button>
                      )}
                    </article>
                  ))}
                </div>
                {!data?.recordings.length && (
                  <div className="empty">还没有导入录像。</div>
                )}
                <h2 className="section-title">观察证据</h2>
                <div className="media-grid">
                  {data?.evidence.map((e) => (
                    <article className="card" key={e.id}>
                      {e.videoUrl ? (
                        <Video url={e.videoUrl} seek={e.seekSeconds} />
                      ) : e.imageUrl ? (
                        <img
                          className="evidence-image"
                          src={e.imageUrl}
                          alt="观察证据"
                        />
                      ) : null}
                      <p>{e.reason}</p>
                      <span className="badge">{e.sourceType}</span>
                    </article>
                  ))}
                </div>
              </>
            )}
            {tab === "settings" && (
              <>
                <div className="page-title">
                  <div>
                    <h1>接入与设置</h1>
                    <p>共用云端服务，分别验证 SDK 能力</p>
                  </div>
                  <button onClick={() => void refresh()}>
                    <RefreshCw size={16} />
                    刷新
                  </button>
                </div>
                <div className="card">
                  <h2>云端 Agent</h2>
                  <dl className="contract">
                    <div>
                      <dt>模型</dt>
                      <dd>
                        {data?.agent.provider || "待连接"} ·{" "}
                        {data?.agent.ready ? "已配置" : "未就绪"}
                      </dd>
                    </div>
                    <div>
                      <dt>接口</dt>
                      <dd>/api → 共用 Cloud 服务</dd>
                    </div>
                    <div>
                      <dt>真实设备</dt>
                      <dd>
                        {data?.integration.physicalDevicesValidated
                          ? "已验证"
                          : "待现场验收"}
                      </dd>
                    </div>
                  </dl>
                </div>
                <div className="card">
                  <h2>官方 Web SDK</h2>
                  <p>
                    直播预览和 Every N s 抽帧（N ≥ 3）。官方 SDK
                    文件通过资料包恢复，Token 只留在当前会话。
                  </p>
                  <button className="primary" onClick={() => setSDK(true)}>
                    进入摄像头联调
                  </button>
                </div>
                <div className="media-grid">
                  {data?.cameras.map((c) => (
                    <article className="card" key={c.id}>
                      <h3>{c.name}</h3>
                      <p>
                        {c.model} · {c.connection}
                      </p>
                      {c.lastFrameUrl && (
                        <img
                          className="evidence-image"
                          src={c.lastFrameUrl}
                          alt={`${c.name} 最近画面`}
                        />
                      )}
                      <p className="muted">{c.adapter}</p>
                      <p>{c.evidence}</p>
                    </article>
                  ))}
                </div>
                <div className="card">
                  <h2>iOS App / TestFlight</h2>
                  <p>
                    App 保留原生交互，并接 App SDK
                    的录像、事件和设备控制。先完成真机验证与签名，再提交外部
                    TestFlight 审核；Web 开发可同时推进。
                  </p>
                </div>
              </>
            )}
          </>
        )}
      </main>
      <nav className="mobile-nav">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => navigate(t.id)}
          >
            <t.icon size={20} />
            <span>{t.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
