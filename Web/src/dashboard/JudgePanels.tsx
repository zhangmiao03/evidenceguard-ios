import { useMemo, useState } from "react";
import {
  taskGroups,
  taskMetrics,
  replaySteps,
  taskTitle,
  short,
  readable,
  modelText,
  toolTitle,
  phaseRecords,
} from "./judge.mjs";
import { deviceLabel, eventLabel, statusLabel } from "./labels";
import { MediaPreview } from "./MediaPreview";
import { RecordContent } from "./RecordContent";
import "./judge.css";
type Row = any;
type Props = {
  rows: Row[];
  allRows?: Row[];
  coverage?: any;
  onSelect: (r: Row) => void;
  onPage?: (n: number) => void;
};
const time = (n: number) =>
  n
    ? new Date(n * 1000).toLocaleString("zh-CN", { hour12: false })
    : "时间未采集";
const duration = (n: any) =>
  typeof n === "number" ? `${(n / 1000).toFixed(2)} 秒` : "耗时未采集";
const failed = (s: string) =>
  ["failed", "cancelled", "interrupted", "http_error", "unsupported"].includes(
    s,
  );
export function Status({ value }: { value: string }) {
  return (
    <span
      className={`judge-status ${failed(value) ? "error" : ["unknown", "uncertain", "unobserved"].includes(value) ? "unknown" : ""}`}
    >
      {value === "unobserved" ? "结束状态未采集" : statusLabel(value)}
    </span>
  );
}
function Empty({
  text = "当前范围未采集到这类记录。可切换后端环境或导入已有追踪。",
}: {
  text?: string;
}) {
  return (
    <div className="judge-empty">
      <span>◌</span>
      <h3>等待可核对的记录</h3>
      <p>{text}</p>
    </div>
  );
}
function Head({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="judge-section-head">
      {eyebrow && <small>{eyebrow}</small>}
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
  );
}
export function FlowStrip({ steps }: { steps: string[] }) {
  return (
    <ol className="judge-flow-strip">
      {steps.map((s, i) => (
        <li key={s}>
          <span>{String(i + 1).padStart(2, "0")}</span>
          {s}
          {i < steps.length - 1 && <b aria-hidden="true">→</b>}
        </li>
      ))}
    </ol>
  );
}
function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: any;
  note: string;
}) {
  return (
    <div className="judge-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
const phases = [
  ["需求与来源", "手机 App 提交问题；设备画面由官方 SDK 获取并上传。"],
  ["组装上下文", "系统提示词、对话、任务事实与允许使用的工具进入本轮。"],
  ["模型选择下一步", "模型返回回复或工具请求；记录输入、输出与调用边界。"],
  ["执行工具", "程序校验工具参数与权限，查询任务、图片、录像或记忆。"],
  ["核验证据", "视觉核验与任务规则约束结论；遮挡、来源或时间不足时保留未知。"],
  ["交付结果", "运行时返回最终回复与证据；结果可能与原始模型输出不同。"],
];
export function LoopDiagram({
  records = [],
  onSelect,
}: {
  records?: Row[];
  onSelect: (r: Row) => void;
}) {
  const [phase, setPhase] = useState(2);
  const matches = phaseRecords(records, phase);
  return (
    <section className="eg-ops-panel judge-loop" aria-label="Agent Loop 结构">
      <Head eyebrow="HOW THE AGENT WORKS" title="一次回答，背后是可核对的循环">
        结构示意 · 下方数量来自所选任务的实际记录。点击节点查看它做了什么。
      </Head>
      <div className="judge-loop-grid">
        {phases.map(([title], i) => (
          <button
            key={title}
            aria-pressed={phase === i}
            onClick={() => setPhase(i)}
          >
            <span className="judge-node-number">0{i + 1}</span>
            <strong>{title}</strong>
            <small>{phaseRecords(records, i).length} 条相关记录</small>
            {i !== 5 && <b aria-hidden="true">→</b>}
          </button>
        ))}
      </div>
      <div className="judge-loop-return">
        <span aria-hidden="true">↰</span>{" "}
        工具结果返回模型，继续判断或再次调用工具{" "}
        <span aria-hidden="true">↲</span>
      </div>
      <div className="judge-phase-info">
        <div>
          <small>
            0{phase + 1} / {phases[phase][0]}
          </small>
          <p>{phases[phase][1]}</p>
          <span>
            {phase === 3
              ? "硬件执行只在手机 SDK；网页不提供云台、对讲、配网控制。"
              : phase === 4
                ? "此节点是实现职责，不表示每次任务都调用了独立核验模型。"
                : "只有留存的回执才计入记录；空白节点不补造执行。"}
          </span>
        </div>
        <div className="judge-phase-records">
          {matches.slice(-4).map((r: Row) => (
            <button key={r.id} onClick={() => onSelect(r)}>
              {r.data.tool ? toolTitle(r.data.tool) : eventLabel(r.name)}{" "}
              <span>查看正文 ↗</span>
            </button>
          ))}
          {!matches.length && <p>所选任务未观测到此节点的回执</p>}
          {matches.length > 4 && (
            <small>显示最近 4 条；全部记录见任务回放</small>
          )}
        </div>
      </div>
    </section>
  );
}
function TaskResult({
  task,
  onSelect,
}: {
  task: any;
  onSelect: (r: Row) => void;
}) {
  return (
    <div className="judge-result">
      <div className="judge-result-top">
        <span>最终交付给 App</span>
        <Status value={task.uncertain ? "uncertain" : task.status} />
      </div>
      <p>
        {task.answer
          ? readable(task.answer)
          : "此任务未保留最终回复正文。模型调用成功不能代替任务完成回执。"}
      </p>
      {task.final && (
        <button onClick={() => onSelect(task.final)}>
          查看最终回复原文 ↗
        </button>
      )}
    </div>
  );
}
export function JudgeOverview({ rows, onSelect, onPage }: Props) {
  const tasks = useMemo(() => taskGroups(rows), [rows]),
    m = taskMetrics(tasks);
  const [chosen, setChosen] = useState("");
  const task =
    tasks.find((t) => t.id === chosen) ||
    tasks.find((t) => t.answer) ||
    tasks[0];
  const media =
    task?.records
      .flatMap((r: Row) => r.data.inputMedia || [])
      .filter((m: any) => m.previewUrl)
      ?.slice(0, 1) || [];
  return (
    <>
      <section className="judge-intro">
        <div>
          <span className="judge-eyebrow">
            EVIDENCEGUARD / 从画面到行动依据
          </span>
          <h2>
            先看结果，再看 Agent
            <br />
            如何得到这个结果。
          </h2>
          <p>
            手机连接摄像头，云端理解需求、调用工具、核验证据。这里用实际运行记录，展开每一次任务。
          </p>
          <div className="eg-ops-actions">
            <button className="primary" onClick={() => onPage?.(3)}>
              阅读 Agent Loop →
            </button>
            <button onClick={() => onPage?.(2)}>逐步回放任务</button>
          </div>
        </div>
        <div className="judge-stack" aria-label="产品链路">
          <div>
            <span>01 / 设备侧</span>
            <strong>手机 App + 官方 SDK</strong>
            <small>绑定 · 取流 · 硬件控制</small>
          </div>
          <div>
            <span>02 / 智能侧</span>
            <strong>云端 Agent Loop</strong>
            <small>上下文 → 模型 ⇄ 工具 → 结果</small>
          </div>
          <div>
            <span>03 / 可核对结果</span>
            <strong>回复 + 图片 / 录像证据</strong>
            <small>已知事实与无法确认分开呈现</small>
          </div>
        </div>
      </section>
      <div className="judge-stats">
        <Stat
          label="可回放的 Agent 任务"
          value={m.agents}
          note="按任务去重，排除接口轮询"
        />
        <Stat label="留有最终回复" value={m.finals} note="仅计实际返回的正文" />
        <Stat
          label="明确保留无法确认"
          value={m.unknown}
          note="按最终回复文字识别，非准确率"
        />
        <Stat
          label="来源图片与录像"
          value={
            rows.filter((r) =>
              ["media_evidence", "media_recordings"].includes(r.name),
            ).length
          }
          note="当前证据与录像资源条数"
        />
      </div>
      <section className="eg-ops-panel judge-feature">
        <div className="judge-section-line">
          <Head eyebrow="A RECORDED TASK" title="用一条任务读懂实际效果" />
          <button onClick={() => onPage?.(2)}>全部任务 →</button>
        </div>
        {task ? (
          <>
            <label className="judge-run-select">
              选择已记录任务
              <select
                value={task.id}
                onChange={(e) => setChosen(e.target.value)}
              >
                {tasks.slice(0, 60).map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {time(t.at)} · {t.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="judge-feature-grid">
              <div>
                <small>需求 / {time(task.at)}</small>
                <h3>{task.title}</h3>
                <FlowStrip
                  steps={[
                    `${task.http} 次模型 HTTP`,
                    `${task.codex} 个执行器步骤`,
                    `${task.tools.length} 次工具返回`,
                  ]}
                />
                {media.length > 0 && (
                  <MediaPreview items={media} title="本任务的实际输入副本" />
                )}
                <p className="judge-caption">
                  这是留存任务的回放，时间为运行记录时间。Codex 步骤不等于底层
                  HTTP 请求数。
                </p>
              </div>
              <TaskResult task={task} onSelect={onSelect} />
            </div>
          </>
        ) : (
          <Empty text="当前环境的采集窗口里没有模型或 Agent 执行。切换其他环境查看已运行任务；不会把 API 轮询当作 Agent 演示。" />
        )}
      </section>
      <div className="judge-next-grid">
        {[
          [13, "01", "看图片如何被理解", "原始图片 → 模型输入 → 可见事实"],
          [14, "02", "看录像如何被找到", "文字查询 → 向量候选 → 视频复核"],
          [7, "03", "看效果与能力边界", "完成回执、未知结果与待验收项目"],
        ].map(([page, n, title, desc]) => (
          <button key={String(page)} onClick={() => onPage?.(Number(page))}>
            <small>{n}</small>
            <strong>{title}</strong>
            <span>{desc} ↗</span>
          </button>
        ))}
      </div>
      <p className="judge-caption">
        Codex 执行步骤：{m.codex}
        。当前筛选内的任务与资源快照，不代表全部历史或全天覆盖。
      </p>
    </>
  );
}
function stepTitle(r: Row) {
  return r.kind === "model"
    ? `${eventLabel(r.name)} · ${r.data.transport === "codex_app_server" ? "执行器往返" : "模型 HTTP"}`
    : r.data.tool
      ? `${r.name === "tool.started" ? "请求" : "返回"}：${toolTitle(r.data.tool)}`
      : eventLabel(r.name);
}
function stepDescription(r: Row) {
  return r.name === "agent.started"
    ? "运行时接受本次任务，后续操作关联到同一追踪。"
    : r.name === "context.prepared"
      ? "对话、系统指令和可用工具在这里组成模型输入。"
      : r.name === "tool.started"
        ? "程序收到工具请求，开始校验与执行。"
        : r.name === "tool.finished"
          ? "工具返回给运行时的实际结果，可继续进入模型。"
          : r.name === "agent.result"
            ? "运行时最终交付；以此核对用户真正收到的答案。"
            : r.kind === "model"
              ? short(modelText(r), 250) ||
                "模型返回结构化内容或工具请求，展开正文查看。"
              : "本步骤的实际采集记录。";
}
export function TaskReplay({
  rows,
  allRows = rows,
  onSelect,
  architecture = false,
}: Props & { architecture?: boolean }) {
  const tasks = useMemo(() => taskGroups(rows), [rows]);
  const [chosen, setChosen] = useState("");
  const [chosenStep, setChosenStep] = useState("");
  const task =
    tasks.find((t) => t.id === chosen) ||
    tasks.find((t) => t.answer) ||
    tasks[0];
  // Selection respects the filter; full trace context is restored for a truthful replay.
  const fullTask = task
    ? taskGroups(allRows.filter((r) => r.traceId === task.id))[0] || task
    : undefined;
  const steps = replaySteps(fullTask);
  const active = steps.find((r: Row) => r.id === chosenStep) || steps[0];
  return (
    <>
      <section className="eg-ops-panel">
        <div className="judge-section-line">
          <Head
            eyebrow="RECORDED RUNS / 真实任务回放"
            title={
              architecture ? "从结构走进一次实际执行" : "按顺序检查一次任务"
            }
          >
            只展示 Agent
            或模型任务。接口轮询不会出现在任务列表；历史任务回放不触发新模型调用。
          </Head>
          <span className="judge-count">
            {tasks.length}
            <small>组任务 / 模型追踪</small>
          </span>
        </div>
        {tasks.length > 0 && (
          <label className="judge-run-select">
            选择已记录任务
            <select
              value={task?.id}
              onChange={(e) => {
                setChosen(e.target.value);
                setChosenStep("");
              }}
            >
              {tasks.slice(0, 100).map((t: any) => (
                <option key={t.id} value={t.id}>
                  {time(t.at)} · {t.title}
                </option>
              ))}
            </select>
          </label>
        )}
        {tasks.length > 100 && (
          <small>选择器显示最近 100 组；使用筛选缩小范围。</small>
        )}
      </section>
      {architecture && (
        <LoopDiagram records={fullTask?.records} onSelect={onSelect} />
      )}
      {fullTask ? (
        <>
          <section className="eg-ops-panel">
            <div className="judge-section-line">
              <div>
                <small>
                  {time(fullTask.at)} ·
                  同一任务的全部已保留记录（含筛选外上下文）
                </small>
                <h2>{fullTask.title}</h2>
              </div>
              <Status
                value={fullTask.uncertain ? "uncertain" : fullTask.status}
              />
            </div>
            <div className="judge-replay-metrics">
              <span>
                <b>{fullTask.http}</b> 次模型 HTTP
              </span>
              <span>
                <b>{fullTask.codex}</b> 个执行器步骤
              </span>
              <span>
                <b>{fullTask.tools.length}</b> 次工具返回
              </span>
              <span>
                <b>{steps.length}</b> 个可展开步骤
              </span>
            </div>
            <div className="judge-replay">
              <ol aria-label="任务步骤">
                {steps.map((r: Row, i: number) => (
                  <li key={r.id}>
                    <button
                      aria-pressed={active?.id === r.id}
                      onClick={() => setChosenStep(r.id)}
                    >
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      <div>
                        <strong>{stepTitle(r)}</strong>
                        <small>
                          {new Date(r.at * 1000).toLocaleTimeString("zh-CN", {
                            hour12: false,
                          })}{" "}
                          · {statusLabel(r.status)}
                        </small>
                      </div>
                    </button>
                  </li>
                ))}
              </ol>
              {active && (
                <div className="judge-step-detail">
                  <small>
                    步骤 {steps.indexOf(active) + 1} / {steps.length} ·{" "}
                    {duration(active.durationMs)}
                  </small>
                  <h3>{stepTitle(active)}</h3>
                  <p>{stepDescription(active)}</p>
                  <div className="eg-ops-actions">
                    <button
                      disabled={steps.indexOf(active) === 0}
                      onClick={() =>
                        setChosenStep(steps[steps.indexOf(active) - 1].id)
                      }
                    >
                      ← 上一步
                    </button>
                    <button
                      disabled={steps.indexOf(active) === steps.length - 1}
                      onClick={() =>
                        setChosenStep(steps[steps.indexOf(active) + 1].id)
                      }
                    >
                      下一步 →
                    </button>
                    <button onClick={() => onSelect(active)}>
                      独立打开详情 ↗
                    </button>
                  </div>
                  <details className="judge-body" key={active.id}>
                    <summary>展开本步完整输入、输出与参数</summary>
                    <RecordContent record={active} records={allRows} />
                  </details>
                </div>
              )}
            </div>
            <TaskResult task={fullTask} onSelect={onSelect} />
          </section>
          <p className="judge-caption">
            模型输入、工具参数和返回正文按实际采集展示；密钥已隐藏。Codex 底层
            HTTP、执行器内置提示词和模型内部推理不可见。
          </p>
        </>
      ) : (
        <Empty />
      )}
    </>
  );
}
export function DeviceStory({ rows, onSelect }: Props) {
  const devices = rows.filter((r) => r.name === "live_devices");
  const receipts = rows.filter((r) =>
    /^(session\.|live\.|capture\.|camera_)/.test(r.name),
  );
  return (
    <>
      <section className="eg-ops-panel">
        <Head
          eyebrow="PHONE → CLOUD → EVIDENCE"
          title="手机负责连接，云端负责理解"
        >
          所有摄像头与门铃控制只能通过手机 App 的官方
          SDK。网页读取上传后留下的画面与任务回执。
        </Head>
        <FlowStrip
          steps={[
            "手机绑定 / 配网",
            "SDK 取流 / 控制",
            "App 上传画面",
            "Agent 读取并分析",
          ]}
        />
      </section>
      <div className="judge-card-grid">
        {devices.map((r, i) => {
          const related = receipts.filter((x) =>
            [x.data.cameraId, x.data.deviceId].includes(r.data.id),
          );
          return (
            <article className="eg-ops-panel judge-device" key={r.id}>
              <span className="judge-device-icon">▣</span>
              <h2>{deviceLabel(r.data.id, rows)}</h2>
              <p>
                {r.data.model || "型号未采集"} ·{" "}
                {r.data.platform || "客户端平台未采集"}
              </p>
              <div className="judge-fact">
                <span>设备登记</span>
                <strong>已有客户端记录</strong>
              </div>
              <div className="judge-fact">
                <span>官方所有权核验</span>
                <strong>
                  {r.data.ownershipVerified === true ? "有核验标记" : "未核验"}
                </strong>
              </div>
              <div className="judge-fact">
                <span>当前可见媒体回执</span>
                <strong>{related.length} 条</strong>
              </div>
              <p className="judge-caption">
                登记不等于在线。取流是否成功以手机 SDK 回调和实际画面为准。
              </p>
              <button onClick={() => onSelect(r)}>查看设备登记详情 →</button>
            </article>
          );
        })}
        {!devices.length && (
          <Empty text="当前快照没有设备登记信息。网页不执行配网或蓝牙连接。" />
        )}
      </div>
      <RecordCards
        title="媒体链路的实际回执"
        rows={receipts.slice(-24).reverse()}
        onSelect={onSelect}
        empty="没有新帧或媒体会话记录，无法确认取流状态。"
      />
    </>
  );
}
export function RecordCards({
  title,
  rows,
  onSelect,
  empty,
}: {
  title: string;
  rows: Row[];
  onSelect: (r: Row) => void;
  empty?: string;
}) {
  return (
    <section className="eg-ops-panel">
      <Head title={title} />
      <div className="judge-record-grid">
        {rows.map((r, i) => (
          <button key={r.id} onClick={() => onSelect(r)}>
            <div>
              <small>
                记录 {i + 1} · {time(r.at)}
              </small>
              <strong>
                {r.data.title ||
                  r.data.name ||
                  (r.data.tool && toolTitle(r.data.tool)) ||
                  eventLabel(r.name)}
              </strong>
              <p>
                {short(
                  r.data.reason ||
                    r.data.resultReason ||
                    modelText(r) ||
                    r.data.query ||
                    "",
                  180,
                )}
              </p>
            </div>
            <Status value={r.data.status || r.status} />
            <span>展开原始回执 ↗</span>
          </button>
        ))}
      </div>
      {!rows.length && <Empty text={empty} />}
    </section>
  );
}
export function PromptStory({ rows, onSelect }: Props) {
  const deployed = rows.find((r) => r.name === "deployed_prompt");
  const prompts = rows
    .filter((r) => r.kind === "prompt")
    .slice(-30)
    .reverse();
  return (
    <>
      <section className="eg-ops-panel">
        <Head eyebrow="CONTEXT, NOT A BLACK BOX" title="看清 AI 收到了哪些信息">
          固定指令定义边界；本轮对话与工具结果提供事实。完整正文按一次实际调用关联。
        </Head>
        <FlowStrip
          steps={[
            "系统角色与约束",
            "当前问题与任务事实",
            "工具定义 / 回执",
            "本次模型输入",
          ]}
        />
        {deployed && (
          <div className="judge-prompt-preview">
            <h3>服务启动时的系统指令</h3>
            <p>{short(deployed.data.systemPrompt, 360)}</p>
            <button onClick={() => onSelect(deployed)}>
              阅读完整系统提示词与工具定义 →
            </button>
          </div>
        )}
      </section>
      <section className="eg-ops-panel">
        <Head title="每次调用的独立输入快照">
          选择一条查看用户问题、系统消息、工具参数与关联模型输出；缺失的历史输入无法恢复。
        </Head>
        <div className="judge-record-grid">
          {prompts.map((r, i) => {
            const model = rows.find((x) => x.data.promptId === r.id);
            return (
              <button key={r.id} onClick={() => onSelect(model || r)}>
                <small>
                  {time(r.at)} · {model ? eventLabel(model.name) : "输入快照"}
                </small>
                <strong>{taskTitle([r])}</strong>
                <span>
                  {r.data.request?.model || model?.data.model || "模型未记录"}
                </span>
                <small>
                  {r.data.request?.messages?.length ?? "未知"} 条消息 ·{" "}
                  {r.data.capture?.truncated ? "正文有截断" : "以采集标记为准"}
                </small>
                <b>查看本次输入与输出 ↗</b>
              </button>
            );
          })}
        </div>
        {!prompts.length && <Empty />}
      </section>
    </>
  );
}
export function TaskBoard({ rows, onSelect }: Props) {
  const skills = rows.filter((r) => r.name === "skills");
  const runs = rows.filter((r) => r.name === "runs");
  const columns = [
    ["draft", "草案 / 待确认"],
    ["running", "执行中"],
    ["completed", "已结束"],
    ["other", "其他 / 未知"],
  ];
  const group = (s: string) =>
    ["draft", "pending", "awaiting_confirmation"].includes(s)
      ? "draft"
      : ["active", "running", "queued"].includes(s)
        ? "running"
        : ["completed", "stopped", "cancelled"].includes(s)
          ? "completed"
          : "other";
  return (
    <>
      <section className="eg-ops-panel">
        <Head
          eyebrow="TEACH → CONFIRM → RUN"
          title="把一次需求变成可持续的任务"
        >
          保存草案后仍需在 App
          确认与启用。看板显示当前数据库状态，不将快照拼成历史进度。
        </Head>
        <FlowStrip
          steps={[
            "自然语言描述",
            "生成并编辑 Skill",
            "App 确认 / 试跑",
            "持续执行与证据",
          ]}
        />
      </section>
      <div className="judge-kanban">
        {columns.map(([id, label]) => (
          <section key={id}>
            <h3>
              {label}
              <span>
                {skills.filter((r) => group(r.data.status) === id).length}
              </span>
            </h3>
            {skills
              .filter((r) => group(r.data.status) === id)
              .map((r) => (
                <button key={r.id} onClick={() => onSelect(r)}>
                  <strong>{readable(r.data.name) || "未命名 Skill"}</strong>
                  <p>
                    {r.data.executionMode === "history"
                      ? "已入库录像"
                      : r.data.executionMode === "live"
                        ? "实时任务配置"
                        : "执行模式未采集"}
                  </p>
                  <Status value={r.data.status || "unknown"} />
                  <small>查看规则与详情 →</small>
                </button>
              ))}
            {!skills.some((r) => group(r.data.status) === id) && (
              <p>当前无此状态 Skill</p>
            )}
          </section>
        ))}
      </div>
      <RecordCards
        title="最近任务执行快照"
        rows={runs
          .slice(-16)
          .reverse()
          .map((r) => ({
            ...r,
            data: {
              ...r.data,
              title:
                skills.find((s) => s.data.id === r.data.skillId)?.data.name ||
                "助手任务",
            },
          }))}
        onSelect={(r) => onSelect(rows.find((x) => x.id === r.id) || r)}
        empty="当前没有任务运行快照。"
      />
    </>
  );
}
export function EvidenceStory({ rows, onSelect, onPage }: Props) {
  const media = rows.filter((r) =>
    ["media_evidence", "media_recordings"].includes(r.name),
  );
  return (
    <>
      <section className="eg-ops-panel">
        <Head eyebrow="SEE THE SOURCE" title="每个结论，都能回到来源">
          图片保留可见事实，录像保留可播放片段。来源类型与时间含义始终随证据展示。
        </Head>
        <div className="eg-ops-actions">
          <button onClick={() => onPage?.(13)}>图片分析 →</button>
          <button onClick={() => onPage?.(14)}>录像检索 →</button>
        </div>
      </section>
      <div className="judge-evidence-grid">
        {media.slice(0, 36).map((r, i) => (
          <article className="eg-ops-panel" key={r.id}>
            <MediaPreview
              items={r.data.media}
              title={r.data.title || `证据 ${i + 1}`}
            />
            <small>
              {r.data.sourceType === "official_sdk"
                ? "手机官方 SDK 来源"
                : r.data.sourceType === "synthetic_review"
                  ? "合成测试素材 · 已入库"
                  : "业务库保存记录"}{" "}
              · {deviceLabel(r.data.cameraId, rows)}
            </small>
            <h3>{r.data.title || `图片证据 ${i + 1}`}</h3>
            <p>
              {short(
                r.data.reason ||
                  r.data.review?.visible ||
                  r.data.visualReview?.review?.visible ||
                  "查看来源与保存的核验结果",
                240,
              )}
            </p>
            <button onClick={() => onSelect(r)}>查看证据与完整结论 →</button>
          </article>
        ))}
      </div>
      {!media.length && (
        <Empty text="当前没有可展示的媒体资源。历史元数据或离线包不一定包含图片、录像。" />
      )}
    </>
  );
}
export function QualityStory({ rows, onSelect }: Props) {
  const tasks = taskGroups(rows),
    m = taskMetrics(tasks),
    trials = rows.filter((r) => r.name === "skill_trials");
  return (
    <>
      <section className="eg-ops-panel">
        <Head eyebrow="RESULTS & LIMITS" title="有完成回执，也要说明无法确认">
          运行成功、判断正确与硬件验收是三个问题。这里仅汇总当前记录支持的结论。
        </Head>
      </section>
      <div className="judge-stats">
        <Stat
          label="已留下最终回复"
          value={m.finals}
          note={`当前 ${m.agents} 个 Agent 任务`}
        />
        <Stat
          label="回复中保留未知"
          value={m.unknown}
          note="由最终回复文字识别"
        />
        <Stat
          label="失败 / 取消 / 中断"
          value={m.failed}
          note="任务结束状态，按任务去重"
        />
        <Stat
          label="未保留最终正文"
          value={m.incomplete}
          note="无法据此断言成功或失败"
        />
      </div>
      <div className="judge-quality-grid">
        <section className="eg-ops-panel">
          <span className="judge-eyebrow">可核对</span>
          <h2>从记录验证行为</h2>
          <ul>
            <li>输入来自哪张图片或哪段录像</li>
            <li>模型选择了什么工具，工具返回了什么</li>
            <li>最终回复是否保留来源、时间和未知项</li>
          </ul>
        </section>
        <section className="eg-ops-panel">
          <span className="judge-eyebrow">待独立验收</span>
          <h2>不从 HTTP 成功推导效果</h2>
          <ul>
            <li>缺少人工标注集，识别准确率未计算</li>
            <li>硬件绑定、取流、云台与对讲需手机真机测试</li>
            <li>已入库片段不等于摄像头全天覆盖</li>
          </ul>
        </section>
      </div>
      <RecordCards
        title="保留未知或出现异常的任务"
        rows={tasks
          .filter((t) => t.uncertain || failed(t.status))
          .slice(0, 12)
          .map((t) => t.final || t.records[t.records.length - 1])}
        onSelect={onSelect}
      />
      <RecordCards
        title="已保存的 Skill 试跑结果"
        rows={trials}
        onSelect={onSelect}
        empty="当前无独立试跑结果，不能据此声称通过真机验收。"
      />
    </>
  );
}
export function UsageStory({ rows, onSelect }: Props) {
  const calls = rows.filter((r) => r.kind === "model"),
    http = calls.filter((r) => r.data.transport !== "codex_app_server"),
    codex = calls.filter((r) => r.data.transport === "codex_app_server");
  const known = http.filter((r) => Number.isFinite(r.data.usage?.total_tokens)),
    tokens = known.reduce((s, r) => s + r.data.usage.total_tokens, 0);
  const groups = [
    ...new Set(calls.map((r) => r.data.model || "模型未采集")),
  ].map((model) => {
    const rs = calls.filter((r) => (r.data.model || "模型未采集") === model);
    return { model, rs };
  });
  return (
    <>
      <div className="judge-stats">
        <Stat
          label="模型 HTTP 尝试"
          value={http.length}
          note="直接观测到的实际请求"
        />
        <Stat
          label="Codex 执行器步骤"
          value={codex.length}
          note="底层 HTTP 次数不可见"
        />
        <Stat
          label="已知 Token 用量"
          value={known.length ? tokens.toLocaleString() : "未采集"}
          note={`${known.length} / ${http.length} 次 HTTP 返回用量`}
        />
        <Stat label="调用费用" value="未计算" note="缺少有效的价格版本" />
      </div>
      <section className="eg-ops-panel">
        <Head eyebrow="OBSERVED MODEL USAGE" title="哪些模型实际参与了运行">
          按已采集请求分组。配置了模型不代表本次用过；执行器 Token
          更新是快照，不累加到 HTTP 用量。
        </Head>
        <div className="judge-model-bars">
          {groups.map((g) => (
            <div key={g.model}>
              <strong>{g.model}</strong>
              <div>
                <span
                  style={{
                    width: `${(g.rs.length / Math.max(1, calls.length)) * 100}%`,
                  }}
                />
              </div>
              <b>{g.rs.length} 条</b>
              <small>
                {
                  g.rs.filter((r) => r.data.transport === "codex_app_server")
                    .length
                }{" "}
                个执行器步骤 ·{" "}
                {
                  g.rs.filter((r) => r.data.transport !== "codex_app_server")
                    .length
                }{" "}
                次 HTTP
              </small>
            </div>
          ))}
        </div>
        {!groups.length && <Empty />}
      </section>
      <section className="eg-ops-panel">
        <Head title="最近调用耗时">
          完整调用耗时，不等于首字延迟。点击每一行检查输入、输出与用量。
        </Head>
        <div className="judge-latencies">
          {calls
            .slice(-24)
            .reverse()
            .map((r) => (
              <button key={r.id} onClick={() => onSelect(r)}>
                <span>{eventLabel(r.name)}</span>
                <div>
                  <b
                    style={{
                      width:
                        r.durationMs == null
                          ? "0%"
                          : `${Math.max(1, (r.durationMs / Math.max(1, ...calls.map((x) => x.durationMs || 0))) * 100)}%`,
                    }}
                  />
                </div>
                <strong>{duration(r.durationMs)}</strong>
                <Status value={r.status} />
              </button>
            ))}
        </div>
      </section>
    </>
  );
}
export function DataStory({ coverage, rows }: Props) {
  return (
    <section className="eg-ops-panel">
      <Head eyebrow="DATA PROVENANCE" title="展示内容从哪里来">
        业务状态、执行记录和媒体副本分别采集，通过同一任务关联；网页仅提供只读查看。
      </Head>
      <div className="judge-data-sources">
        {[
          [
            "业务数据库",
            "设备、Skill、任务与证据的当前快照",
            rows.filter((r) => r.kind === "resource").length,
          ],
          [
            "追踪数据库",
            "实际提示词、模型与工具调用回执",
            rows.filter((r) => r.kind !== "resource").length,
          ],
          [
            "媒体副本",
            "采集时保存并校验的图片 / 视频",
            rows.filter((r) => r.data.media || r.data.inputMedia).length,
          ],
        ].map(([title, desc, n]) => (
          <div key={title}>
            <span>{n}</span>
            <h3>{title}</h3>
            <p>{desc}</p>
          </div>
        ))}
      </div>
      <p className="judge-caption">
        {coverage?.truncated || coverage?.resourcesTruncated
          ? "当前快照存在采样上限，不能当作全部历史。"
          : "是否完整以采集覆盖声明为准。"}{" "}
        导入数据仅在当前浏览器查看；导出保留筛选范围和来源标记。
      </p>
    </section>
  );
}
