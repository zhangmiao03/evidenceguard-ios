import { Status } from "./JudgePanels";
type Item = Record<string, any>;
const number = (n: unknown, unit = "") =>
  typeof n === "number" ? `${n.toFixed(1)}${unit}` : "—";
const bytes = (n: unknown) =>
  typeof n !== "number"
    ? "—"
    : n > 1024 ** 3
      ? `${(n / 1024 ** 3).toFixed(2)} GB`
      : n > 1024 ** 2
        ? `${(n / 1024 ** 2).toFixed(1)} MB`
        : `${(n / 1024).toFixed(1)} KB`;
const time = (at: number) =>
  at
    ? new Date(at * 1000).toLocaleString("zh-CN", { hour12: false })
    : "尚未采集";

export function CloudStatus({ coverage }: { coverage?: Item }) {
  const s = coverage?.server || {};
  return (
    <div className="eg-ops-cloud-status">
      <span
        className={`eg-ops-dot ${coverage?.stale || coverage?.observability !== "connected" ? "bad" : ""}`}
      />
      <strong>
        {coverage?.stale
          ? "采样已过期"
          : coverage?.observability === "connected"
            ? "真实服务已连接"
            : "采集状态待确认"}
      </strong>
      <span>CPU {number(s.cpuPercent, "%")}</span>
      <span>
        内存 {bytes(s.memoryUsedBytes)} / {bytes(s.memoryTotalBytes)}
      </span>
      <span>每 5 秒采样 · {time(coverage?.sampledAt)}</span>
    </div>
  );
}

function History({
  rows,
  field,
  total,
  label,
}: {
  rows: Item[];
  field: string;
  total?: number;
  label: string;
}) {
  const valid = rows.filter((r) => typeof r[field] === "number");
  if (valid.length < 2)
    return <p className="eg-ops-note">等待两个有效采样点</p>;
  const first = valid[0].at,
    span = Math.max(1, valid[valid.length - 1].at - first);
  const ceiling = total || Math.max(1, ...valid.map((r) => r[field]));
  const points = valid
    .map(
      (r) =>
        `${8 + ((r.at - first) / span) * 584},${112 - Math.min(1, r[field] / ceiling) * 100}`,
    )
    .join(" ");
  return (
    <>
      <svg
        className="eg-ops-spark"
        viewBox="0 0 600 124"
        role="img"
        aria-label={label}
      >
        {[12, 62, 112].map((y) => (
          <line key={y} x1="8" y1={y} x2="592" y2={y} stroke="#26374c" />
        ))}
        <polyline
          points={points}
          fill="none"
          stroke="#62c9ee"
          strokeWidth="2.5"
        />
        {valid.map((r, i) => (
          <circle
            key={i}
            cx={8 + ((r.at - first) / span) * 584}
            cy={112 - Math.min(1, r[field] / ceiling) * 100}
            r="2"
            fill="#62c9ee"
          >
            <title>
              {time(r.at)} ·{" "}
              {number(
                total ? (r[field] / total) * 100 : r[field],
                total ? "%" : "",
              )}
            </title>
          </circle>
        ))}
      </svg>
      <div className="eg-ops-axis">
        <span>{time(first)}</span>
        <span>{time(valid[valid.length - 1].at)}</span>
      </div>
    </>
  );
}

const environmentName = (id: string) =>
  ({ demo: "手机演示后端", team: "团队开发后端", review: "检索验证后端" })[
    id
  ] || id;
export function ServerResources({ server }: { server?: Item }) {
  if (!server || server.errorType)
    return (
      <section className="eg-ops-panel">
        <h2>服务器采样不可用</h2>
        <p className="eg-ops-note">尚未取得有效的主机数据，缺失值不记为 0。</p>
      </section>
    );
  const mem = server.memoryTotalBytes
    ? (server.memoryUsedBytes / server.memoryTotalBytes) * 100
    : null;
  const disk = server.diskTotalBytes
    ? (server.diskUsedBytes / server.diskTotalBytes) * 100
    : null;
  return (
    <>
      <section className="eg-ops-panel">
        <div className="judge-section-head">
          <small>LIVE INFRASTRUCTURE</small>
          <h2>支撑 Agent 的主机，当前负载如何？</h2>
          <p>
            约每 5 秒采样 · {time(server.at)}
            。下方是同一主机上的各后端进程，网页不会执行重启或控制操作。
          </p>
        </div>
        <div className="judge-stats">
          {[
            [
              "CPU",
              server.cpuPercent,
              `${server.cpuCount} 个逻辑 CPU · 主机总容量`,
            ],
            [
              "内存",
              mem,
              `${bytes(server.memoryUsedBytes)} / ${bytes(server.memoryTotalBytes)}`,
            ],
            ["系统盘", disk, `剩余 ${bytes(server.diskFreeBytes)}`],
          ].map(([label, value, hint]) => (
            <div className="judge-stat" key={String(label)}>
              <span>{label}</span>
              <strong>{number(value, "%")}</strong>
              <small>{hint}</small>
              <div
                className={`judge-meter ${typeof value === "number" && value > 85 ? "warn" : ""}`}
              >
                <span
                  style={{
                    width:
                      typeof value === "number"
                        ? `${Math.max(0, Math.min(100, value))}%`
                        : "0%",
                  }}
                />
              </div>
            </div>
          ))}
          <div className="judge-stat">
            <span>网络接收 / 发送</span>
            <strong style={{ fontSize: 18 }}>
              {bytes(server.networkReceiveBytesPerSecond)}
              <br /> / {bytes(server.networkSendBytesPerSecond)}
            </strong>
            <small>每秒 · 不含回环接口</small>
          </div>
        </div>
      </section>
      <div className="eg-ops-grid">
        <section className="eg-ops-panel">
          <div className="eg-ops-panel-head">
            <h2>CPU 近期趋势</h2>
            <small>0–100%</small>
          </div>
          <History
            rows={server.history || []}
            field="cpuPercent"
            total={100}
            label="服务器 CPU 使用率时间序列"
          />
        </section>
        <section className="eg-ops-panel">
          <div className="eg-ops-panel-head">
            <h2>内存近期趋势</h2>
            <small>MemTotal − MemAvailable</small>
          </div>
          <History
            rows={server.history || []}
            field="memoryUsedBytes"
            total={server.memoryTotalBytes}
            label="服务器内存使用率时间序列"
          />
        </section>
      </div>
      <div className="judge-service-grid">
        {(server.services || []).map((s: Item) => (
          <article key={s.environment}>
            <h3>{environmentName(s.environment)}</h3>
            <Status
              value={s.state === "active" ? "active" : s.state || "unknown"}
            />
            <div className="judge-fact">
              <span>进程 CPU</span>
              <strong>{number(s.cpuPercent, "%")}</strong>
            </div>
            <div className="judge-fact">
              <span>常驻内存</span>
              <strong>{bytes(s.rssBytes)}</strong>
            </div>
            <div className="judge-fact">
              <span>重启次数</span>
              <strong>{s.restarts ?? "未采集"}</strong>
            </div>
            <details className="judge-caption">
              <summary>进程技术详情</summary>
              <p>
                {s.service} · PID {s.pid || "未知"} · {s.subState}
              </p>
            </details>
          </article>
        ))}
      </div>
      <p className="judge-caption">
        主机已运行 {number(server.uptimeSeconds / 3600)} 小时。进程 CPU 的 100%
        表示一个逻辑 CPU；首次采样不计算速率。负载（1 / 5 / 15 分钟）：
        {(server.loadAverage || [])
          .map((v: number) => v.toFixed(2))
          .join(" / ")}
        。
      </p>
    </>
  );
}

export function DeploymentPanel({ deployment }: { deployment?: Item }) {
  if (!deployment)
    return (
      <section className="eg-ops-panel">
        <h2>部署版本尚未采集</h2>
        <p className="eg-ops-note">
          云端采集开启后显示进程启动时和当前磁盘的源码指纹。
        </p>
      </section>
    );
  const d = deployment,
    known = Array.isArray(d.diskVsRunning),
    repo = Array.isArray(d.diskVsRepository);
  return (
    <>
      <section className="eg-ops-panel">
        <div className="judge-section-head">
          <small>DEPLOYMENT VERIFICATION</small>
          <h2>页面展示的是哪一份后端？</h2>
          <p>
            从进程身份、启动源码、仓库基准三个层面核对。此页面只读取，不覆盖团队正在部署的代码。
          </p>
        </div>
        <div className="judge-deploy-checks">
          <div>
            <small>01 / 进程身份</small>
            <strong>
              {d.processMatchesObserver ? "已对应当前进程" : "待核对"}
            </strong>
            <p>采集器与实际服务 PID 核对；不只依赖页面版本号。</p>
          </div>
          <div>
            <small>02 / 磁盘与启动时源码</small>
            <strong>
              {!known
                ? "未采集"
                : d.diskVsRunning.length
                  ? `${d.diskVsRunning.length} 个文件变化`
                  : "一致"}
            </strong>
            <p>
              启动指纹不等于读取运行中 Python
              字节码；有差异时重启可能加载不同源码。
            </p>
          </div>
          <div>
            <small>03 / 磁盘与仓库基准</small>
            <strong>
              {repo ? `${d.diskVsRepository.length} 个文件差异` : "未采集"}
            </strong>
            <p>
              基准为发布包携带的已提交版本，比较覆盖 {d.fileCount ?? "未知"} 个
              Python 文件。
            </p>
          </div>
        </div>
        <p className="judge-caption">
          应用版本 {d.appVersion || "未知"} · 进程启动 {time(d.startedAt)}
        </p>
      </section>
      <section className="eg-ops-panel">
        <div className="judge-section-head">
          <h2>差异集中在哪些文件</h2>
          <p>差异表示实际服务器与本次核对基准不同，不自动判定为错误。</p>
        </div>
        <div className="judge-file-list">
          {(d.diskVsRepository || []).map((f: Item) => (
            <div key={f.path}>
              <strong>{f.path}</strong>
              <span>
                {(
                  {
                    changed: "内容变化",
                    modified: "内容变化",
                    missing: "服务器缺失",
                    unexpected: "服务器新增",
                    added: "服务器新增",
                  } as Record<string, string>
                )[f.status] || f.status}
              </span>
            </div>
          ))}
        </div>
        {repo && !d.diskVsRepository.length && <p>当前文件与仓库基准一致。</p>}
      </section>
      <details className="judge-advanced">
        <summary>开发者核验：版本编号、SHA-256 与文件指纹</summary>
        <div className="eg-ops-health">
          {[
            ["监控组件版本", d.observerRevision],
            ["仓库比对基准", d.referenceRevision],
            ["源码集合指纹", d.sourceFingerprint],
          ].map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong className="eg-ops-mono">{value || "未知"}</strong>
            </div>
          ))}
        </div>
        <h3>磁盘 / 仓库差异</h3>
        <pre>{JSON.stringify(d.diskVsRepository, null, 2)}</pre>
        <h3>磁盘 / 启动时差异</h3>
        <pre>{JSON.stringify(d.diskVsRunning, null, 2)}</pre>
        <details>
          <summary>所有文件指纹</summary>
          <pre>{JSON.stringify(d.files, null, 2)}</pre>
        </details>
      </details>
    </>
  );
}

const phases = [
  {
    label: "任务开始",
    names: ["agent.started", "run_started", "proactive_started"],
  },
  { label: "组装上下文", names: ["context.prepared"] },
  {
    label: "调用模型",
    names: ["model_started", "request.snapshot", "chat", "codex_step"],
  },
  {
    label: "执行工具",
    names: ["tool.started", "tool.finished", "tool_started", "tool_completed"],
  },
  { label: "模型继续判断", names: ["model.output"] },
  {
    label: "返回最终结果",
    names: [
      "agent.result",
      "response_completed",
      "agent.finished",
      "proactive_finished",
    ],
  },
];

export function AgentCycle({
  records,
  onSelect,
}: {
  records: Item[];
  onSelect: (record: Item) => void;
}) {
  const sorted = [...records].sort((a, b) => a.at - b.at);
  const models = sorted.filter((r) => r.kind === "model");
  const tools = sorted.filter((r) => r.name === "tool.finished");
  const finished = [...sorted]
    .reverse()
    .find((r) => ["agent.finished", "proactive_finished"].includes(r.name));
  const finalResult = [...sorted]
    .reverse()
    .find((r) => r.name === "agent.result");
  return (
    <div className="eg-ops-cycle">
      <div className="eg-ops-panel-head">
        <h3>Agent 执行循环</h3>
        <small>
          {models.filter((r) => r.data.transport !== "codex_app_server").length}{" "}
          次模型 HTTP 请求 ·{" "}
          {models.filter((r) => r.data.transport === "codex_app_server").length}{" "}
          个 Codex 执行步骤 · {tools.length} 次工具执行 ·{" "}
          {finished?.status || "等待结束回执"}
        </small>
      </div>
      <div className="eg-ops-cycle-phases">
        {phases.map((p) => {
          const matches = sorted.filter((r) => p.names.includes(r.name));
          return (
            <button
              key={p.label}
              disabled={!matches.length}
              onClick={() =>
                onSelect(
                  p.label === "返回最终结果" && finalResult
                    ? finalResult
                    : matches[matches.length - 1],
                )
              }
            >
              <span>{matches.length ? "●" : "○"}</span>
              <strong>{p.label}</strong>
              <small>
                {matches.length
                  ? `${matches.length} 条回执`
                  : "未观测到 / 不适用"}
              </small>
            </button>
          );
        })}
      </div>
      <p className="eg-ops-note">
        工具结果可再次进入模型，循环次数以实际回执为准。Codex
        步骤记录主程序与执行器的往返，底层 HTTP
        和执行器内置提示词不可见。协议记录展示实际指令与回执；Token
        更新是快照，不重复求和。不展示模型内部推理。
      </p>
      {finalResult && (
        <button
          className="eg-ops-final-result"
          onClick={() => onSelect(finalResult)}
        >
          <strong>查看最终回复</strong>
          <span>
            {typeof finalResult.data.content?.answer === "string"
              ? finalResult.data.content.answer.slice(0, 180)
              : "旧记录仅有摘要，无法恢复正文"}
          </span>
        </button>
      )}
      <div className="eg-ops-span-list">
        {sorted
          .filter(
            (r) =>
              r.kind === "model" ||
              r.name === "tool.finished" ||
              ["agent.finished", "proactive_finished"].includes(r.name),
          )
          .map((r) => (
            <button key={r.id} onClick={() => onSelect(r)}>
              <span
                className={`eg-ops-badge ${["failed", "http_error", "cancelled"].includes(r.status) ? "bad" : ""}`}
              >
                {r.kind === "model"
                  ? "MODEL"
                  : r.name === "tool.finished"
                    ? "TOOL"
                    : "AGENT"}
              </span>
              <strong>{r.data.tool || r.data.model || r.name}</strong>
              <span>
                {r.durationMs == null
                  ? "耗时未采集"
                  : `${(r.durationMs / 1000).toFixed(2)} s`}
              </span>
            </button>
          ))}
      </div>
    </div>
  );
}
