import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ErrorNotice, Modal } from "./ProductUI";
import {
  timeLabel,
  type Bootstrap,
  type Memory,
  type Personal,
  type Preferences,
} from "./product-types";

export function MemoryPage({
  personal,
  onUpdate,
}: {
  personal?: Personal;
  onUpdate: (value: Personal) => void;
}) {
  const [filter, setFilter] = useState("all"),
    [content, setContent] = useState("");
  const [temporary, setTemporary] = useState(false),
    [adding, setAdding] = useState(false);
  const [remove, setRemove] = useState<Memory | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  const items = (personal?.memories || []).filter(
    (m) =>
      (!m.expiresAt || m.expiresAt > Date.now() / 1000) &&
      (filter === "all" ||
        (filter === "temporary" ? !!m.expiresAt : !m.expiresAt)),
  );
  const perform = async (operation: () => Promise<Personal>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const value = await operation();
      if (mounted.current) {
        onUpdate(value);
        setAdding(false);
        setRemove(null);
        setContent("");
        setTemporary(false);
      }
    } catch (e) {
      if (mounted.current)
        setError(e instanceof Error ? e.message : "保存未完成");
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <div className="page-stack">
      <section className="feature-banner">
        <span className="feature-symbol">✧</span>
        <div>
          <h2>让助手更了解你</h2>
          <p>保存你确认的关注点与回复偏好，后续对话继续使用。</p>
          <button
            className="primary"
            disabled={!personal}
            onClick={() => {
              setError("");
              setAdding(true);
            }}
          >
            添加记忆
          </button>
        </div>
      </section>
      <div className="section-heading">
        <h2>已确认的记忆 · {personal?.memories.length || 0}</h2>
        <label>
          记忆类型
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">全部</option>
            <option value="longterm">长期</option>
            <option value="temporary">24 小时</option>
          </select>
        </label>
      </div>
      <div className="memory-grid">
        {items.map((m) => (
          <article className="card product-card" key={m.id}>
            <span className="pill blue">
              {m.expiresAt ? "临时记忆" : "长期记忆"}
            </span>
            <p className="memory-content">{m.content}</p>
            <small>
              {m.expiresAt
                ? "有效至 " + timeLabel(m.expiresAt)
                : "保存于 " + timeLabel(m.createdAt)}
            </small>
            <button
              className="text-button danger"
              aria-label={`移除记忆：${m.content}`}
              onClick={() => {
                setError("");
                setRemove(m);
              }}
            >
              移除
            </button>
          </article>
        ))}
      </div>
      {!items.length && (
        <p className="empty-inline">
          这里还没有记忆。可以先告诉助手你最关心什么。
        </p>
      )}
      <p className="subtle-note">
        每个客户端最多保存 20
        条。记忆与提醒偏好属于当前浏览器，摄像头和任务在团队空间共享；记忆不会自动授权或启用设备操作。
      </p>
      {adding && (
        <Modal title="添加记忆" busy={busy} onClose={() => setAdding(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void perform(() =>
                api.request<Personal>("/api/personal/memories", {
                  content: content.trim(),
                  temporary,
                }),
              );
            }}
          >
            <label>
              希望助手记住什么
              <textarea
                value={content}
                maxLength={500}
                rows={5}
                onChange={(e) => setContent(e.target.value)}
                placeholder="例如：回复简洁一些，先说明需要我做什么"
                disabled={busy}
              />
            </label>
            <small>{content.length}/500</small>
            <label className="check-label">
              <input
                type="checkbox"
                checked={temporary}
                disabled={busy}
                onChange={(e) => setTemporary(e.target.checked)}
              />
              仅保留 24 小时
            </label>
            <p>确认后才会保存到当前团队服务。</p>
            <ErrorNotice error={error} />
            <button className="primary" disabled={busy || !content.trim()}>
              确认记住
            </button>
          </form>
        </Modal>
      )}
      {remove && (
        <Modal
          title="移除这条记忆？"
          busy={busy}
          onClose={() => setRemove(null)}
        >
          <p>{remove.content}</p>
          <ErrorNotice error={error} />
          <button
            className="primary danger-button"
            disabled={busy}
            onClick={() =>
              void perform(() =>
                api.request<Personal>(
                  `/api/personal/memories/${remove.id}`,
                  undefined,
                  undefined,
                  "DELETE",
                ),
              )
            }
          >
            确认移除
          </button>
        </Modal>
      )}
    </div>
  );
}

export function SettingsPage({
  data,
  online,
  onUpdate,
  onConnection,
  onOfficial,
  onAssistant,
  onSkill,
}: {
  data: Bootstrap;
  online: boolean;
  onUpdate: (value: Personal) => void;
  onConnection: (target: HTMLElement) => void;
  onOfficial: () => void;
  onAssistant: () => void;
  onSkill: (id: string) => void;
}) {
  const [draft, setDraft] = useState<Preferences | null>(
    data.personal?.preferences || null,
  );
  const [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState("");
  const mounted = useRef(true);
  const [inbox, setInbox] = useState(false);
  const [inboxError, setInboxError] = useState("");
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  useEffect(() => {
    if (!dirty && !busy && data.personal) setDraft(data.personal.preferences);
  }, [data.personal?.revision, dirty, busy]);
  const change = <K extends keyof Preferences>(
    key: K,
    value: Preferences[K],
  ) => {
    setDraft((old) => (old ? { ...old, [key]: value } : old));
    setDirty(true);
    setSaved("");
  };
  const save = async () => {
    if (!draft || busy) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const result = await api.request<Personal>(
        "/api/personal/preferences",
        draft,
        undefined,
        "PUT",
      );
      if (mounted.current) {
        onUpdate(result);
        setDraft(result.preferences);
        setDirty(false);
        setSaved("提醒设置已保存");
      }
    } catch (e) {
      if (mounted.current)
        setError(
          (e instanceof Error ? e.message : "保存失败") +
            "，修改已保留，可以重试。",
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <div className="page-stack">
      <section className="feature-banner">
        <span className="feature-symbol">EG</span>
        <div>
          <h2>你的 EvidenceGuard</h2>
          <p>
            {online ? "云端已连接" : "连接暂时中断"} · {data.cameras.length}{" "}
            台设备 · {data.skills.length} 项任务
          </p>
          <small>
            当前为团队演示空间，摄像头任务共享，个人对话与偏好按客户端区分。
          </small>
        </div>
      </section>
      <div className="settings-grid">
        <section className="card product-card">
          <h2>通知与提醒</h2>
          <p>主动提醒和每日概况会出现在助手主对话。</p>
          {draft ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
            >
              <fieldset disabled={busy}>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(e) => change("enabled", e.target.checked)}
                  />
                  应用内主动提醒
                </label>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={draft.dailySummary}
                    onChange={(e) => change("dailySummary", e.target.checked)}
                  />
                  每日守护概况
                </label>
                <div className="form-grid">
                  <label>
                    每日概况时间
                    <select
                      value={draft.summaryHour}
                      onChange={(e) =>
                        change("summaryHour", Number(e.target.value))
                      }
                    >
                      {hours()}
                    </select>
                  </label>
                  <label>
                    时区
                    <input
                      list="timezones"
                      value={draft.timezone}
                      required
                      maxLength={80}
                      onChange={(e) => change("timezone", e.target.value)}
                    />
                  </label>
                  <datalist id="timezones">
                    {[
                      Intl.DateTimeFormat().resolvedOptions().timeZone,
                      "Asia/Shanghai",
                      "Asia/Singapore",
                      "UTC",
                      "America/Los_Angeles",
                      "Europe/London",
                    ]
                      .filter((v, i, a) => a.indexOf(v) === i)
                      .map((t) => (
                        <option value={t} key={t} />
                      ))}
                  </datalist>
                  <label>
                    免打扰开始
                    <select
                      value={draft.quietStart}
                      onChange={(e) =>
                        change("quietStart", Number(e.target.value))
                      }
                    >
                      {hours()}
                    </select>
                  </label>
                  <label>
                    免打扰结束
                    <select
                      value={draft.quietEnd}
                      onChange={(e) =>
                        change("quietEnd", Number(e.target.value))
                      }
                    >
                      {hours()}
                    </select>
                  </label>
                </div>
                <small>
                  开始与结束相同表示不设置免打扰。主动提醒关闭时，每日概况也暂停。
                </small>
                <ErrorNotice error={error} />
                <p role="status">{saved}</p>
                <button className="primary" disabled={!dirty || busy}>
                  {busy ? "正在保存…" : "保存提醒设置"}
                </button>
              </fieldset>
            </form>
          ) : (
            <p>提醒设置尚未加载。</p>
          )}
          <p className="subtle-note">
            Web 当前提供应用内提醒；关闭网页后不会发送浏览器系统推送。iOS 的
            APNs 使用独立的设备通知通道。
          </p>
          <button className="text-button" onClick={onAssistant}>
            查看助手提醒 →
          </button>
          <button className="text-button" onClick={() => setInbox(true)}>
            提醒记录
          </button>
        </section>
        <div className="page-stack">
          <section className="card product-card">
            <h2>连接与设备</h2>
            <p>
              Agent：{data.agent.ready ? "已就绪" : "尚未就绪"} ·{" "}
              {data.agent.provider || "未知"}
            </p>
            <div className="settings-links">
              <button onClick={(e) => onConnection(e.currentTarget)}>
                官方账号与设备接入 <span>↗</span>
              </button>
              <button onClick={onOfficial}>
                官方 SDK 硬件工作区 <span>↗</span>
              </button>
              <a href="/dashboard" target="_blank" rel="noreferrer">本地研发 Dashboard ↗</a>
            </div>
          </section>
          <section className="card product-card">
            <h2>隐私与数据</h2>
            <p>
              实时视频通过官方媒体链路播放。Agent
              按请求取样，不会因保存记忆自动上传画面。
            </p>
            <p>
              关闭直播或切换官方工作区会停止取样并释放当前媒体会话。设备存储卡中的原始录像由官方功能管理。
            </p>
            <p>
              账号密钥只保留在页面内存；退出会清除本机聊天草稿。服务中的已保存对话、证据和记忆保留。
            </p>
          </section>
          <section className="card product-card">
            <h2>帮助与版本</h2>
            <p>Web 0.2 · 助手、摄像头 Skill、任务、记忆与设置。</p>
            <p>
              硬件绑定与配网按官方 SDK
              的实际支持范围操作；没有可用画面时显示无法确认。
            </p>
            <p>语音输入可使用系统键盘听写。Web 未启用持续麦克风或后台录音。</p>
          </section>
        </div>
      </div>
      {!!data.personal?.activity?.length && (
        <details className="card product-card">
          <summary>最近主动提醒处理记录</summary>
          {data.personal.activity.slice(0, 12).map((a) => (
            <p key={a.id}>
              {a.reason} · {a.status} · {timeLabel(a.createdAt)}
            </p>
          ))}
        </details>
      )}
      {inbox && (
        <Modal title="提醒记录" busy={busy} onClose={() => setInbox(false)}>
          <ErrorNotice error={inboxError} />
          {!data.personal?.inbox.length && (
            <p>还没有提醒。新的任务事件和每日概况会保留在这里。</p>
          )}
          <div className="page-stack">
            {data.personal?.inbox.map((item) => (
              <article className="card product-card" key={item.id}>
                <h3>
                  {item.title}
                  {item.read ? " · 已读" : " · 未读"}
                </h3>
                <p>{item.body}</p>
                <small>{timeLabel(item.createdAt)}</small>
                <div className="button-row">
                  {item.skillId && (
                    <button
                      className="secondary"
                      onClick={() => {
                        setInbox(false);
                        onSkill(item.skillId!);
                      }}
                    >
                      查看任务和证据
                    </button>
                  )}
                  {!item.read && (
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        setInboxError("");
                        try {
                          const value = await api.request<Personal>(
                            `/api/personal/inbox/${item.id}/read`,
                            {},
                          );
                          if (mounted.current) onUpdate(value);
                        } catch (e) {
                          if (mounted.current)
                            setInboxError(
                              e instanceof Error ? e.message : "未能标记已读",
                            );
                        } finally {
                          if (mounted.current) setBusy(false);
                        }
                      }}
                    >
                      标记已读
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
function hours() {
  return Array.from({ length: 24 }, (_, i) => (
    <option value={i} key={i}>
      {String(i).padStart(2, "0")}:00
    </option>
  ));
}
