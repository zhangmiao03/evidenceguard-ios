import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { api, installation } from "./api";
import { newID } from "./browser-support";
import { ErrorNotice, ImageEvidence, Modal, VideoPlayer } from "./ProductUI";
import {
  running,
  timeLabel,
  type Bootstrap,
  type ChatRun,
  type Conversation,
  type HistoryFilter,
  type Personal,
  type Recording,
} from "./product-types";

const storageKey = `evidenceguard.chat.${installation}`;
type Pending = {
  message: string;
  conversationId: string;
  requestId: string;
  cameraId?: string;
  skillId?: string;
  executionMode: string;
  historyFilter?: HistoryFilter;
  replyToMessageId?: string;
};
type Local = {
  drafts: Record<string, string>;
  pending: Record<string, Pending>;
  active?: string;
  modes: Record<string, string>;
};
function readLocal(): Local {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return {
      drafts: data.drafts || {},
      pending: data.pending || {},
      modes: data.modes || {},
      active: data.active,
    };
  } catch {
    return { drafts: {}, pending: {}, modes: {} };
  }
}
function persist(value: Local) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(value));
  } catch {
    /* usable without storage */
  }
}
export function clearChatDrafts() {
  try {
    localStorage.removeItem(storageKey);
  } catch {
    /* storage unavailable */
  }
}
export type AssistantHandle = { cancel: (all?: boolean) => Promise<void> };
export type AssistantIntent = {
  nonce: number;
  prompt: string;
  skillId?: string;
};

export const Assistant = forwardRef<
  AssistantHandle,
  {
    data: Bootstrap;
    selected: string;
    ready: boolean;
    active: boolean;
    intent: AssistantIntent | null;
    onCamera: (id: string) => Promise<void>;
    onSkill: (id: string) => void;
    onRefresh: () => Promise<void>;
    onPersonal: (value: Personal) => void;
  }
>(
  (
    {
      data,
      selected,
      ready,
      active,
      intent,
      onCamera,
      onSkill,
      onRefresh,
      onPersonal,
    },
    ref,
  ) => {
    const local = useRef(readLocal());
    const client = useRef(api.scoped());
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [conversation, setConversation] = useState("");
    const [mode, setMode] = useState("live");
    const [input, setInput] = useState("");
    const [runs, setRuns] = useState<ChatRun[]>([]);
    const [error, setError] = useState("");
    const [syncError, setSyncError] = useState("");
    const [sending, setSending] = useState(false);
    const [initializing, setInitializing] = useState(true);
    const [retry, setRetry] = useState(0);
    const [period, setPeriod] = useState("");
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");
    const [reply, setReply] = useState("");
    const [skill, setSkill] = useState<string | undefined>();
    const [rename, setRename] = useState(false);
    const [title, setTitle] = useState("");
    const [video, setVideo] = useState<{
      record: Recording;
      offset: number;
    } | null>(null);
    const [working, setWorking] = useState(false);
    const epoch = useRef(0),
      version = useRef(0),
      mounted = useRef(true),
      sendLock = useRef(false);
    const runRef = useRef<ChatRun | null>(null);
    const pendingNew = useRef<string>();
    const modeRef = useRef(mode);
    modeRef.current = mode;
    const stream = conversation + (mode === "history" ? "-history" : "");
    const streamRef = useRef(stream);
    streamRef.current = stream;
    const main = conversations.find((item) => item.kind === "main");
    const current = conversations.find((item) => item.id === conversation);
    const activeRun = [...runs].reverse().find((item) => running(item.status));
    runRef.current = activeRun || null;
    const messages =
      current?.kind === "main" && mode === "live"
        ? data.personal?.messages || []
        : [];
    const timeline = [
      ...runs.map((run) => ({ at: run.createdAt || 0, run, notice: null })),
      ...messages.map((notice) => ({
        at: notice.createdAt,
        run: null,
        notice,
      })),
    ].sort((a, b) => a.at - b.at);
    const saveInput = (value: string) => {
      setInput(value);
      if (conversation) {
        local.current.drafts[stream] = value;
        persist(local.current);
      }
    };
    const callbacks = useRef({ onRefresh, onPersonal });
    callbacks.current = { onRefresh, onPersonal };

    const cancel = async (all = false) => {
      if (!all && modeRef.current !== "live") return;
      epoch.current++;
      version.current++;
      const run = runRef.current;
      sendLock.current = false;
      setSending(false);
      if (run) {
        try {
          const updated = await client.current.request<ChatRun>(
            `/api/runs/${run.id}/cancel`,
            {},
          );
          if (mounted.current)
            setRuns((old) => old.map((r) => (r.id === run.id ? updated : r)));
        } catch (e) {
          if (mounted.current)
            setError(e instanceof Error ? e.message : "取消未完成");
        }
      }
    };
    useImperativeHandle(ref, () => ({ cancel }));
    useEffect(() => {
      mounted.current = true;
      return () => {
        mounted.current = false;
        epoch.current++;
      };
    }, []);
    useEffect(() => {
      let alive = true;
      setInitializing(true);
      setError("");
      void (async () => {
        const restored = await client.current.request<Conversation>(
          "/api/agent/conversations/main",
          {},
        );
        const list = await client.current.request<Conversation[]>(
          "/api/agent/conversations",
        );
        if (!alive) return;
        setConversations(list);
        const id = list.some((c) => c.id === local.current.active)
          ? local.current.active!
          : restored.id;
        setConversation(id);
        setMode(local.current.modes[id] || "live");
      })()
        .catch((e) => {
          if (alive) setError(e.message);
        })
        .finally(() => {
          if (alive) setInitializing(false);
        });
      return () => {
        alive = false;
      };
    }, [retry]);
    useEffect(() => {
      if (!conversation) return;
      setInput(local.current.drafts[stream] || "");
      setRuns([]);
      setReply("");
      setError("");
      local.current.active = conversation;
      local.current.modes[conversation] = mode;
      persist(local.current);
      let alive = true,
        loading = false;
      const load = async () => {
        if (loading || !alive) return;
        loading = true;
        const v = version.current;
        try {
          const list = await client.current.request<ChatRun[]>(
            `/api/agent/conversations/${stream}`,
          );
          if (!alive || v !== version.current) return;
          setRuns(list);
          setSyncError("");
          const pending = local.current.pending[stream];
          if (pending && list.some((r) => r.id === pending.requestId)) {
            delete local.current.pending[stream];
            if (local.current.drafts[stream]?.trim() === pending.message) {
              local.current.drafts[stream] = "";
              setInput("");
            }
            persist(local.current);
          }
        } catch {
          if (alive) setSyncError("对话暂未同步，输入内容已保留。");
        } finally {
          loading = false;
        }
      };
      void load();
      const timer = setInterval(() => {
        if (!document.hidden) void load();
      }, 1800);
      return () => {
        alive = false;
        clearInterval(timer);
      };
    }, [stream]);
    useEffect(() => {
      if (!intent || !main) return;
      setConversation(main.id);
      setMode("live");
      setSkill(intent.skillId);
      local.current.drafts[main.id] = intent.prompt;
      persist(local.current);
      setInput(intent.prompt);
    }, [intent?.nonce, main?.id]);

    const act = async (fn: () => Promise<void>) => {
      setWorking(true);
      setError("");
      try {
        await fn();
      } catch (e) {
        if (mounted.current)
          setError(e instanceof Error ? e.message : "操作未完成");
      } finally {
        if (mounted.current) setWorking(false);
      }
    };
    const send = async () => {
      if (sendLock.current || activeRun || !conversation || !input.trim())
        return;
      let filter: HistoryFilter | undefined;
      if (mode === "history" && period) {
        filter = { period };
        if (period === "custom") {
          const a = new Date(start).getTime() / 1000,
            b = new Date(end).getTime() / 1000;
          if (!Number.isFinite(a) || !Number.isFinite(b) || a >= b) {
            setError("请选择有效的起止时间，开始时间须早于结束时间。");
            return;
          }
          filter = { period, startAt: a, endAt: b };
        }
      }
      const body = {
        message: input.trim(),
        conversationId: stream,
        cameraId: selected || undefined,
        skillId: skill,
        executionMode: mode,
        historyFilter: filter,
        replyToMessageId: mode === "live" ? reply || undefined : undefined,
      };
      const prior = local.current.pending[stream];
      const comparable = (p: Pending) => {
        const { requestId: _, ...rest } = p;
        return JSON.stringify(rest);
      };
      const pending: Pending = {
        ...body,
        requestId:
          prior && comparable(prior) === JSON.stringify(body)
            ? prior.requestId
            : `run-${newID()}`,
      };
      local.current.pending[stream] = pending;
      persist(local.current);
      const e = epoch.current,
        target = stream;
      sendLock.current = true;
      setSending(true);
      setError("");
      version.current++;
      try {
        const run = await client.current.request<ChatRun>(
          "/api/agent/runs",
          pending,
        );
        if (!mounted.current || e !== epoch.current) {
          await client.current
            .request(`/api/runs/${run.id}/cancel`, {})
            .catch(() => {});
          delete local.current.pending[target];
          if (mounted.current) persist(local.current);
          return;
        }
        delete local.current.pending[target];
        if (local.current.drafts[target]?.trim() === body.message) {
          local.current.drafts[target] = "";
          if (streamRef.current === target) setInput("");
        }
        persist(local.current);
        // A task shortcut can open the main conversation while another topic's
        // POST is still in flight. Persist its receipt without touching this view.
        if (streamRef.current === target) {
          setReply("");
          setRuns((old) => [...old.filter((r) => r.id !== run.id), run]);
        }
        try {
          const list = await client.current.request<Conversation[]>(
            "/api/agent/conversations",
          );
          if (mounted.current && e === epoch.current) setConversations(list);
        } catch {
          if (mounted.current && e === epoch.current)
            setSyncError("消息已接收，对话列表暂未同步。");
        }
        void callbacks.current.onRefresh().catch(() => {});
      } catch (err) {
        if (
          mounted.current &&
          e === epoch.current &&
          streamRef.current === target
        )
          setError(
            (err instanceof Error ? err.message : "发送未完成") +
              " 输入已保留，可重试；重试不会重复创建请求。",
          );
      } finally {
        if (e === epoch.current && mounted.current) {
          sendLock.current = false;
          setSending(false);
        }
      }
    };
    const feedback = (id: string, action: string) =>
      act(async () => {
        const value = await client.current.request<Personal>(
          `/api/personal/messages/${id}/feedback`,
          { action },
        );
        if (mounted.current) callbacks.current.onPersonal(value);
      });
    return (
      <section
        className="card assistant-card product-assistant"
        aria-label="助手对话"
        hidden={!active}
      >
        <div className="section-heading">
          <div>
            <h2>你的守护助手</h2>
            <small>持续对话 · 结论有来源</small>
          </div>
          <span className="pill blue">Agent</span>
        </div>
        <div className="chat-controls">
          <label>
            对话
            <select
              aria-label="选择对话"
              value={conversation}
              disabled={sending || initializing || !!activeRun || working}
              onChange={(e) => {
                setSkill(undefined);
                setConversation(e.target.value);
                setMode(local.current.modes[e.target.value] || "live");
              }}
            >
              {conversations.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                  {c.unreadCount ? ` (${c.unreadCount})` : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            disabled={sending || initializing || !!activeRun || working}
            onClick={() =>
              void act(async () => {
                const requestId = (pendingNew.current ||= newID());
                const topic = await client.current.request<Conversation>(
                  "/api/agent/conversations",
                  { requestId },
                );
                pendingNew.current = undefined;
                if (!mounted.current) return;
                setConversations((old) => [
                  ...old.filter((c) => c.id !== topic.id),
                  topic,
                ]);
                setConversation(topic.id);
                setSkill(undefined);
                setMode("live");
              })
            }
          >
            新对话
          </button>
          {current?.kind === "topic" && (
            <button
              className="text-button"
              onClick={() => {
                setTitle(current.title);
                setRename(true);
              }}
            >
              重命名
            </button>
          )}
        </div>
        <div className="chat-controls">
          <label>
            对话范围
            <select
              aria-label="对话范围"
              value={mode}
              disabled={sending || !!activeRun}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="live">现场与任务</option>
              <option value="history">历史资料（只读）</option>
            </select>
          </label>
          <label>
            摄像头
            <select
              aria-label="助手摄像头"
              value={selected}
              disabled={sending}
              onChange={(e) => void onCamera(e.target.value)}
            >
              <option value="">全部 / 不指定设备</option>
              {data.cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {mode === "history" && (
          <div className="history-range">
            <label>
              查询日期
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                disabled={sending}
              >
                <option value="">按问题判断</option>
                <option value="all">全部资料</option>
                <option value="today">今天（上海时区）</option>
                <option value="yesterday">昨天（上海时区）</option>
                <option value="last_24_hours">最近 24 小时</option>
                <option value="custom">自定义时间</option>
              </select>
            </label>
            {period === "custom" && (
              <div className="form-grid">
                <label>
                  开始时间
                  <input
                    type="datetime-local"
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </label>
                <label>
                  结束时间
                  <input
                    type="datetime-local"
                    value={end}
                    onChange={(e) => setEnd(e.target.value)}
                  />
                </label>
              </div>
            )}
            <small>
              历史查询不会获取新画面或修改摄像头任务。自定义时间使用浏览器时区。
            </small>
          </div>
        )}
        {skill && (
          <div className="context-strip">
            当前任务：{data.skills.find((s) => s.id === skill)?.name || skill}
            <button className="text-button" onClick={() => setSkill(undefined)}>
              取消关联
            </button>
          </div>
        )}
        <ErrorNotice error={error || syncError} />
        {!conversation && !initializing && (
          <button className="secondary" onClick={() => setRetry((n) => n + 1)}>
            重试连接助手
          </button>
        )}
        <div className="messages" aria-live="polite">
          {initializing ? (
            <p role="status">正在恢复对话…</p>
          ) : (
            !timeline.length && (
              <div className="assistant-welcome">
                <div className="agent-orbit">✧</div>
                <h3>今天，有什么想关注的？</h3>
                <p>
                  {mode === "history"
                    ? "查找保存的录像与观察记录，资料缺口会明确说明。"
                    : "聊聊任务，或让我查看一张新画面。持续守护需要先确认规则。"}
                </p>
                {(mode === "history"
                  ? ["查录像：包裹什么时候离开区域？", "回顾最近的观察记录。"]
                  : [
                      "现在画面里有什么？",
                      "我关心的任务现在怎么样？",
                      "看看客厅有什么活动",
                    ]
                ).map((q) => (
                  <button
                    className="suggestion"
                    key={q}
                    onClick={() => saveInput(q)}
                  >
                    {q}
                    <span>↗</span>
                  </button>
                ))}
              </div>
            )
          )}
          {timeline.map(({ run, notice }) =>
            run ? (
              <article className="turn" key={run.id}>
                <p className="user-message">{run.message}</p>
                <div className="agent-message">
                  <span className="agent-icon small">✧</span>
                  <div>
                    <p className="prewrap">
                      {run.text ||
                        run.error ||
                        (running(run.status) ? "正在处理…" : "本次回复已结束")}
                    </p>
                    <small>
                      {timeLabel(run.createdAt)} ·{" "}
                      {run.executionMode === "history"
                        ? "历史资料"
                        : "现场与任务"}
                    </small>
                    {running(run.status) && (
                      <button
                        className="text-button"
                        onClick={() => void cancel(true)}
                      >
                        停止本次回复
                      </button>
                    )}
                    {run.error && (
                      <button
                        className="text-button"
                        onClick={() => saveInput(run.message)}
                      >
                        编辑后重试
                      </button>
                    )}
                    {run.captures?.map((c) => (
                      <div className="capture-receipt" key={c.id}>
                        {c.imageUrl && (
                          <ImageEvidence
                            path={c.imageUrl}
                            alt="Agent 本次观察图片"
                          />
                        )}
                        <small>
                          {c.reason} · {c.historical ? "历史资料" : "本次取样"}{" "}
                          · {timeLabel(c.capturedAt || c.sampledAt)}
                        </small>
                      </div>
                    ))}
                    {run.draft && (
                      <button
                        className="draft-link"
                        onClick={() => onSkill(run.draft!.id)}
                      >
                        <strong>{run.draft.name}</strong>
                        <span>继续设置对象、条件与确认 →</span>
                      </button>
                    )}
                    {run.videos?.map((v) => (
                      <button
                        className="draft-link"
                        key={v.id}
                        onClick={() =>
                          void act(async () => {
                            const record =
                              await client.current.request<Recording>(
                                `/api/recordings/${v.recordingId}`,
                              );
                            if (mounted.current)
                              setVideo({ record, offset: v.seekSeconds });
                          })
                        }
                      >
                        <strong>
                          {v.title} ·{" "}
                          {v.verdict === "matched" ? "已匹配片段" : "候选片段"}
                        </strong>
                        <span>{v.summary}</span>
                        <small>
                          {v.limitation} · 播放 {v.seekSeconds.toFixed(1)} s
                          附近
                        </small>
                      </button>
                    ))}
                    {!!run.toolReceipts?.length && (
                      <details>
                        <summary>本次操作</summary>
                        {run.toolReceipts.map((r, i) => (
                          <p key={i}>
                            {r.tool} · {r.status}
                          </p>
                        ))}
                      </details>
                    )}
                  </div>
                </div>
              </article>
            ) : (
              notice && (
                <article className="proactive-message" key={notice.id}>
                  <span className="pill blue">
                    助手主动提醒{notice.read ? " · 已读" : " · 未读"}
                  </span>
                  <h3>{notice.title}</h3>
                  <p>{notice.body}</p>
                  <small>
                    {notice.why} · {timeLabel(notice.createdAt)}
                  </small>
                  <details>
                    <summary>查看依据</summary>
                    {notice.sources.map((s) => (
                      <p key={s.id}>
                        {s.name || s.type} ·{" "}
                        {s.reason || s.limitation || "相关记录"}
                        {s.skillId && (
                          <button
                            className="text-button"
                            onClick={() => onSkill(s.skillId!)}
                          >
                            查看任务
                          </button>
                        )}
                      </p>
                    ))}
                  </details>
                  <div className="button-row">
                    <button
                      className="secondary"
                      onClick={() => {
                        setReply(notice.id);
                        saveInput(`关于“${notice.title}”，`);
                      }}
                    >
                      继续追问
                    </button>
                    {[
                      ["read", "标记已读"],
                      ["handled", "已处理"],
                      ["snooze", "稍后提醒"],
                      ["dismiss", "不再提醒此项"],
                    ].map(([action, label]) => (
                      <button
                        key={action}
                        disabled={working}
                        className="text-button"
                        onClick={() => void feedback(notice.id, action)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {notice.feedback && (
                    <small>
                      已反馈：
                      {{
                        read: "已读",
                        handled: "已处理",
                        snooze: "稍后提醒",
                        dismiss: "忽略此项",
                      }[notice.feedback] || notice.feedback}
                    </small>
                  )}
                </article>
              )
            ),
          )}
        </div>
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          {reply && (
            <div className="context-strip">
              正在回复助手提醒
              <button
                type="button"
                className="text-button"
                onClick={() => setReply("")}
              >
                取消引用
              </button>
            </div>
          )}
          <label className="sr-only" htmlFor="question">
            向 Agent 提问
          </label>
          <textarea
            id="question"
            value={input}
            onChange={(e) => saveInput(e.target.value)}
            placeholder="告诉我，你想看什么…"
            rows={3}
            maxLength={2000}
          />
          <div>
            <small>
              {mode === "history"
                ? "只读历史资料"
                : ready
                  ? "● 新画面可用"
                  : "○ 尚无实时输入，可继续聊任务"}
            </small>
            <button
              className="send-button"
              aria-label="发送问题"
              disabled={
                sending ||
                !!activeRun ||
                !conversation ||
                !input.trim() ||
                !data.agent.ready
              }
            >
              {sending ? "…" : "↑"}
            </button>
          </div>
          {!data.agent.ready && (
            <small>云端 Agent 尚未就绪，请在设置检查连接。</small>
          )}
        </form>
        {rename && (
          <Modal
            title="重命名对话"
            busy={working}
            onClose={() => setRename(false)}
          >
            <label>
              对话名称
              <input
                value={title}
                maxLength={80}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={working || !title.trim()}
              onClick={() =>
                void act(async () => {
                  const updated = await client.current.request<Conversation>(
                    `/api/agent/conversations/${conversation}`,
                    { title: title.trim() },
                    undefined,
                    "PATCH",
                  );
                  if (mounted.current) {
                    setConversations((old) =>
                      old.map((c) => (c.id === updated.id ? updated : c)),
                    );
                    setRename(false);
                  }
                })
              }
            >
              保存名称
            </button>
            <ErrorNotice error={error} />
          </Modal>
        )}
        {video && (
          <Modal title={video.record.title} onClose={() => setVideo(null)}>
            <VideoPlayer
              path={video.record.playbackUrl}
              offset={video.offset}
            />
            <p>定位为模型估计，请核验原始录像。</p>
          </Modal>
        )}
      </section>
    );
  },
);
