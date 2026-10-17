import { useEffect, useMemo, useRef, useState } from "react";
import {
  SCHEMA,
  MAX_BYTES,
  validateBundle,
  sanitizeBundle,
  selectRecords,
  metrics,
  exportBundle,
  emptyBundle,
  sampleBundle,
} from "./data.mjs";
import "./dashboard.css";
import { AgentCycle, DeploymentPanel, ServerResources } from "./CloudPanels";
import { RecordContent } from "./RecordContent";
import { cloudJSON } from "./cloud.mjs";
import { ImageAnalysis, VideoIndex } from "./MediaPanels";
import {ImageMemory} from "./ImageMemory";
import { ArchivePanel } from "./ArchivePanel";
import { Showcase } from "./Showcase";
import {JudgeOverview,TaskReplay,DeviceStory,PromptStory,TaskBoard,EvidenceStory,QualityStory,UsageStory,DataStory,FlowStrip} from "./JudgePanels";
import {SkillStudio} from './SkillStudio';
import {deviceLabel,eventLabel,recordLabel,traceLabel} from './labels';

type Row = {
  id: string;
  kind: string;
  name: string;
  at: number;
  traceId: string;
  spanId: string;
  parentSpanId?: string | null;
  platform: string;
  source: string;
  status: string;
  durationMs: number | null;
  data: Record<string, any>;
};
type Bundle = {
  schemaVersion: string;
  dataset: { id: string; title: string; source: string; exportedAt: number };
  records: Row[];
  coverage?: Record<string, any>;
};
const pages = [
  "运行总览",
  "设备与取流",
  "对话与 Trace",
  "Agent 与模型",
  "提示词与上下文",
  "自定义 Skill",
  "证据与录像",
  "质量与试跑",
  "用量与覆盖",
  "数据与版本",
  "服务器资源",
  "部署代码核对",
  "作品演示",
  "图像记忆与分析",
  "视频向量库",
];
const glyphs = ["◈", "▣", "≋", "◇", "⌘", "☷", "▤", "◎", "▥", "⇄", "▧", "⌁", "▶", "▧", "⌗"];
const pageKeys = ["overview","devices","traces","agent","prompts","tasks","evidence","quality","usage","data","server","deployment","showcase","images","vectors"];
const fmtTime = (at: number) =>
  at
    ? new Date(at * 1000).toLocaleString("zh-CN", { hour12: false })
    : "尚未采集";
const fmtDuration = (n: number | null) =>
  n == null
    ? "—"
    : n < 1000
      ? `${Math.round(n)} ms`
      : `${(n / 1000).toFixed(2)} s`;
const json = (v: unknown) => JSON.stringify(v, null, 2);
const failure = (status: string) =>
  ["failed", "http_error", "cancelled", "unsupported", "interrupted"].includes(
    status,
  );
const initialFilters = {
  hours: "",
  platform: "",
  source: "",
  device: "",
  query: "",
};

export default function Dashboard() {
  const [bundle, setBundle] = useState<Bundle>(emptyBundle());
  const [imageView,setImageView]=useState("memory");
  const [page, setPage] = useState(() => Math.max(0, pageKeys.indexOf(new URLSearchParams(location.search).get("view") || "overview")));
  const [mode, setMode] = useState("offline");
  const [cloud, setCloud] = useState(false);
  const [environment, setEnvironment] = useState(() => {
    const requested=new URLSearchParams(location.search).get("environment")||"demo";
    return ["demo","team","review"].includes(requested)?requested:"demo";
  });
  const [environments, setEnvironments] = useState<Array<{id:string;title:string}>>([]);
  const [refreshNumber, setRefreshNumber] = useState(0);
  const [liveAt, setLiveAt] = useState(0);
  const [cloudFailed, setCloudFailed] = useState(false);
  const [discovery, setDiscovery] = useState("正在连接云端采集服务…");
  const [discoveryNumber, setDiscoveryNumber] = useState(0);
  const [filters, setFilters] = useState(initialFilters);
  const [selected, setSelected] = useState<Row | null>(null);
  const [archiveContext, setArchiveContext] = useState<Row[]>([]);
  const detailRecords = useMemo(() => [...new Map([...bundle.records,...archiveContext].map(r=>[r.id,r])).values()], [bundle.records,archiveContext]);
  function selectArchived(record: Row, context: Row[] = []) { setArchiveContext(context); setSelected(record); }
  const [trace, setTrace] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [teamToken, setTeamToken] = useState("");
  const [opsToken, setOpsToken] = useState("");
  const [archives, setArchives] = useState<
    Array<{ id: string; title: string }>
  >([]);
  const input = useRef<HTMLInputElement>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController>();
  const rows = useMemo(
    () => selectRecords(bundle, filters) as Row[],
    [bundle, filters],
  );
  const stats = metrics(rows);
  const calls = rows.filter((r) => r.kind === "model");
  const resources = (names: string[]) =>
    rows.filter((r) => r.kind === "resource" && names.includes(r.name));
  const traces = [
    ...new Set(rows.filter((r) => r.kind !== "resource").map((r) => r.traceId)),
  ];
  const sources = [...new Set(bundle.records.map((r) => r.source))];
  const devices = [
    ...new Set(
      bundle.records
        .flatMap((r) => [
          r.data.deviceId,
          r.data.cameraId,
          r.name === "live_devices" ? r.data.id : null,
        ])
        .filter(Boolean),
    ),
  ] as string[];
  const problems = rows.filter((r) => failure(r.status));
  const synthetic = bundle.dataset.source === "synthetic";
  const filtered = Object.values(filters).some(Boolean);
  function openPage(index: number) {
    setPage(index);
    window.scrollTo({top:0,behavior:"instant"});
    const url=new URL(location.href);
    url.searchParams.set("view",pageKeys[index]);
    if(cloud)url.searchParams.set("environment",environment);
    history.replaceState(null,"",url);
  }
  useEffect(() => {
    setSelected(null);
    setTrace(null);
    setArchiveContext([]);
  }, [filters, page, bundle.dataset.id]);
  useEffect(() => {
    const c = new AbortController(); let active = true; let timer: number | undefined; let attempts = 0;
    async function discover() {
      try {
        const info = await cloudJSON("/dashboard/api/info", { signal: c.signal });
        if (info.mode !== "competition" || !Array.isArray(info.environments) || !info.environments.length) throw Error("此入口没有提供云端采集配置，可先使用离线演示。");
        if (!active) return;
        setCloud(true); setEnvironments(info.environments);
        setEnvironment(old => info.environments.some((e: {id:string}) => e.id === old) ? old : info.defaultEnvironment || "demo"); setDiscovery("");
        setMode(old => old === "offline" ? "cloud" : old);
      } catch (e) {
        if (!active) return;
        setDiscovery(e instanceof Error ? e.message : "连接失败，将自动重试。");
        timer = window.setTimeout(discover, Math.min(30000, 3000 * 2 ** attempts++));
      }
    }
    void discover();
    const online = () => setDiscoveryNumber(n => n + 1);
    window.addEventListener("online", online);
    return () => { active = false; c.abort(); clearTimeout(timer); window.removeEventListener("online", online); };
  }, [discoveryNumber]);
  useEffect(() => {
    if (!cloud || mode !== "cloud") return;
    const c = new AbortController(); let active = true; let timer: number | undefined;
    async function poll() {
      try {
        const value = sanitizeBundle(validateBundle(await cloudJSON(`/dashboard/api/snapshot?environment=${encodeURIComponent(environment)}`, { signal: c.signal }))) as Bundle;
        if (active) { setBundle(value); setLiveAt(Date.now()); setCloudFailed(false); setError(""); }
      } catch (e) {
        if (active) { setCloudFailed(true); setError(e instanceof Error ? e.message : "云端连接失败"); }
      } finally { if (active) timer = window.setTimeout(poll, 5000); }
    }
    void poll();
    return () => { active=false; c.abort(); clearTimeout(timer); };
  }, [cloud, mode, environment, refreshNumber]);
  useEffect(
    () => () => {
      generation.current++;
      controller.current?.abort();
    },
    [],
  );
  const detailOpen = Boolean(selected || trace);
  useEffect(() => {
    if (!detailOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keys = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelected(null);
        setTrace(null);
      }
      if (e.key !== "Tab") return;
      const buttons = document.querySelectorAll<HTMLElement>(
        ".eg-ops-detail button:not(:disabled), .eg-ops-detail summary, .eg-ops-detail a[href]",
      );
      const first = buttons[0],
        last = buttons[buttons.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keys);
    return () => {
      document.removeEventListener("keydown", keys);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [detailOpen]);

  function accept(value: unknown, nextMode: string) {
    const parsed = sanitizeBundle(validateBundle(value)) as Bundle;
    setBundle(parsed);
    setMode(nextMode);
    setError("");
    setFilters(initialFilters);
    setSelected(null);
    setTrace(null);
  }
  async function request(path: string, method = "GET", body?: unknown) {
    if (
      (teamToken || opsToken) &&
      location.protocol !== "https:" &&
      !["127.0.0.1", "localhost", "[::1]"].includes(location.hostname)
    )
      throw Error("请通过 HTTPS 连接，访问密钥不会发送至不安全的远程地址");
    const c = new AbortController();
    controller.current = c;
    const timeout = window.setTimeout(() => c.abort(), 12000);
    try {
      const r = await fetch(path, {
        method,
        signal: c.signal,
        headers: {
          "Content-Type": "application/json",
          ...(teamToken ? { Authorization: `Bearer ${teamToken}` } : {}),
          ...(opsToken ? { "X-EG-Ops-Token": opsToken } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const value = await r.json().catch(() => null);
      if (!r.ok)
        throw Error(
          typeof value?.detail === "string"
            ? value.detail
            : `连接失败（${r.status}）`,
        );
      return value;
    } finally {
      clearTimeout(timeout);
    }
  }
  async function refresh() {
    const version = ++generation.current;
    controller.current?.abort();
    setBusy(true);
    setError("");
    try {
      const value = await request("/api/ops/snapshot");
      if (version === generation.current) {
        accept(value, "local");
        setConnecting(false);
        setNotice("已读取本地服务；数据不会自动上传到云端。");
      }
    } catch (e) {
      if (version === generation.current)
        setError(e instanceof Error ? e.message : "连接失败");
    } finally {
      if (version === generation.current) setBusy(false);
    }
  }
  async function importFile(file?: File) {
    if (!file) return;
    const version = ++generation.current;
    controller.current?.abort();
    setBusy(false);
    setNotice("");
    try {
      if (file.size > MAX_BYTES) throw Error("请选择不超过 20 MB 的 JSON 文件");
      const value = JSON.parse(await file.text());
      if (version === generation.current) {
        accept(value, "imported");
        setNotice("已在当前浏览器内存中打开。导入数据未经设备或服务端核验。");
      }
    } catch (e) {
      if (version === generation.current)
        setError(e instanceof Error ? e.message : "文件无效");
    }
    if (input.current) input.current.value = "";
  }
  function download() {
    const value = exportBundle(bundle, rows, filters);
    const url = URL.createObjectURL(
      new Blob([json(value)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `evidenceguard-${synthetic ? "SYNTHETIC-" : ""}${value.dataset.id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(
      "已导出当前筛选记录及关联提示词；不包含原始视频、图片或访问密钥。",
    );
  }
  async function archiveImport() {
    setBusy(true);
    setError("");
    try {
      const result = await request("/api/ops/import", "POST", bundle);
      setNotice(
        result.imported
          ? "已存入本地追踪库；业务数据库未被修改。"
          : "同一文件已存在，未重复导入。",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "归档失败");
    } finally {
      setBusy(false);
    }
  }
  async function readArchive(id?: string) {
    const version = ++generation.current;
    controller.current?.abort();
    setBusy(true);
    setError("");
    try {
      const value = await request(
        id
          ? `/api/ops/export?dataset=${encodeURIComponent(id)}`
          : "/api/ops/datasets",
      );
      if (version !== generation.current) return;
      if (id) {
        accept(value, "imported");
        setNotice("已打开本地归档；导入来源仍未经核验。");
      } else {
        setArchives(value);
        setNotice(`本地追踪库有 ${value.length} 个离线归档。`);
      }
    } catch (e) {
      if (version === generation.current)
        setError(e instanceof Error ? e.message : "归档读取失败");
    } finally {
      if (version === generation.current) setBusy(false);
    }
  }
  const badge = (value: string) => (
    <span className={`eg-ops-badge ${failure(value) ? "bad" : ""}`}>
      {value}
    </span>
  );
  function table(items: Row[], title: string, hint = "点击记录查看详情") {
    return (
      <section className="eg-ops-panel">
        <div className="eg-ops-panel-head">
          <h2>{title}</h2>
          <small>
            {items.length} 条 · {hint}
          </small>
        </div>
        {!items.length ? (
          <Empty />
        ) : (
          <div className="eg-ops-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>记录 / 对象</th>
                  <th>来源 / 平台</th>
                  <th>状态</th>
                  <th>耗时</th>
                  <th>接收 / 快照时间</th>
                </tr>
              </thead>
              <tbody>
                {items
                  .slice(-100)
                  .reverse()
                  .map((r) => (
                    <tr key={r.id}>
                      <td>
                        <button
                          className="eg-ops-row-link"
                          onClick={() => {
                            setSelected(r);
                            setTrace(null);
                          }}
                        >
                          {r.data.model || recordLabel(r,bundle.records)}
                          <small>
                            {r.kind === "model"
                              ? eventLabel(r.name)
                              : eventLabel(r.name)}
                          </small>
                        </button>
                      </td>
                      <td>
                        {r.source}
                        <small>{r.platform}</small>
                      </td>
                      <td>{badge(r.status)}</td>
                      <td>{fmtDuration(r.durationMs)}</td>
                      <td>{fmtTime(r.at)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
        {items.length > 100 && (
          <p className="eg-ops-note">
            表格展示最近 100 条；指标与导出覆盖当前筛选的 {items.length}{" "}
            条记录。请使用筛选缩小范围。
          </p>
        )}
      </section>
    );
  }
  function traceList() {
    return (
      <section className="eg-ops-panel">
        <div className="eg-ops-panel-head">
          <h2>请求追踪</h2>
          <small>{traces.length} 组关联 ID</small>
        </div>
        {traces.length ? (
          traces
            .slice(-80)
            .reverse()
            .map((id) => {
              const events = rows.filter((r) => r.traceId === id);
              const bad = events.some((r) => failure(r.status));
              return (
                <button
                  className="eg-ops-trace"
                  key={id}
                  onClick={() => {
                    setTrace(id);
                    setSelected(null);
                  }}
                >
                  <span className={`eg-ops-dot ${bad ? "bad" : ""}`} />
                  <span>
                    <strong>{traceLabel(id,bundle.records)}</strong>
                    <small>
                      {events.length} 条记录 ·{" "}
                      {[...new Set(events.map((r) => r.platform))].join(" / ")}
                    </small>
                  </span>
                  <span>{bad ? "存在失败记录" : "查看链路"} →</span>
                </button>
              );
            })
        ) : (
          <Empty />
        )}
        {traces.length > 80 && (
          <p className="eg-ops-note">
            展示最近 80 组；使用筛选或导出检查其他追踪。
          </p>
        )}
      </section>
    );
  }
  function coverage() {
    return (
      <section className="eg-ops-panel">
        <div className="eg-ops-panel-head">
          <h2>采集边界与数据质量</h2>
          <small>缺失不等于 0</small>
        </div>
        <div className="eg-ops-health">
          {[
            [
              "模型 Usage",
              `${stats.usageCalls} / ${stats.calls} 次返回 total_tokens`,
            ],
            ["客户端埋点", `${stats.clientEvents} 条（客户端自述）`],
            [
              "数据新鲜度",
              mode === "cloud" ? "云端只读 · 5 秒自动刷新" : mode === "local"
                ? "手动刷新 · 本地服务快照"
                : "离线快照 · 不代表当前运行",
            ],
            ["设备拍摄时间", "未核验；客户端取样时间单独记录"],
            ["正文采集", bundle.coverage?.contentCapture ? `已启用 · 当前 ${bundle.coverage?.contentRecords ?? "—"} 条脱敏正文` : "按记录标记查看 · 历史摘要无法恢复"],
            ["费用 / 首字延迟", "未采集价格版本 / 非流式调用"],
            [
              "队列丢弃 / 写入失败",
              `${bundle.coverage?.dropped ?? "未知"} / ${bundle.coverage?.writeErrors ?? "未知"}`,
            ],
            [
              "截断 / 保留上限淘汰",
              `${bundle.coverage?.truncated || bundle.coverage?.resourcesTruncated ? "有截断" : "未报告截断"} / ${bundle.coverage?.evictedSinceStart ?? "未知"}`,
            ],
          ].map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
        <p className="eg-ops-note">
          HTTP 成功只表示服务返回成功；Agent、工具和输出校验请查看同一
          Trace。队列与淘汰计数从本次进程启动累计。业务资源是读取时的快照，不是状态变化历史。
        </p>
      </section>
    );
  }
  function content() {
    if (page === 12) return <Showcase onMonitor={() => openPage(2)} onPage={openPage} />;
    if (page === 13) return <><div className="eg-media-tabs eg-image-views">{[['memory','图像记忆与理解'],['archive','完整图片台账'],['analysis','调用与事件核验']].map(([id,label])=><button key={id} aria-pressed={imageView===id} onClick={()=>setImageView(id)}>{label}</button>)}</div>{imageView==='memory'?<ImageMemory rows={rows} onSelect={setSelected} onPage={openPage}/>:imageView==='archive'?<ArchivePanel key={'images'+environment+JSON.stringify(filters)} section="images" environment={environment} online={cloud&&mode==='cloud'} filters={filters} rows={rows} onSelect={selectArchived}/>:<ImageAnalysis rows={rows} coverage={bundle.coverage?.mediaIndex} onSelect={setSelected}/>}</>;
    if (page === 14) return <VideoIndex rows={rows} coverage={bundle.coverage?.mediaIndex} onSelect={setSelected} />;
    if (page === 10) return <ServerResources server={bundle.coverage?.server} />;
    if (page === 11) return <DeploymentPanel deployment={bundle.coverage?.deployment} />;
    const props={rows,allRows:bundle.records,coverage:bundle.coverage,onSelect:setSelected,onPage:openPage};
    if(page===0)return <JudgeOverview {...props}/>;
    if(page===1)return <DeviceStory {...props}/>;
    if(page===2)return <><ArchivePanel key={'replies'+environment+JSON.stringify(filters)} section="replies" environment={environment} online={cloud&&mode==='cloud'} filters={filters} rows={rows} onSelect={selectArchived}/><TaskReplay {...props}/><details className="judge-advanced"><summary>开发者记录：所有关联追踪（含接口轮询）</summary>{traceList()}</details></>;
    if(page===3)return <><TaskReplay {...props} architecture/><details className="judge-advanced"><summary>模型配置与全部调用记录</summary>{table(calls,"模型与执行器调用","HTTP 请求与 Codex 步骤分别标明；点击查看实际输入输出")}{table(rows.filter(r=>r.name.startsWith("codex.")),"Codex 协议记录","实际下发指令与工具回执；不含内部推理")}{table(resources(["model_configuration"]),"服务模型配置","配置值不代表实际调用")}</details></>;
    if(page===4)return <PromptStory {...props}/>;
    if(page===5)return <><SkillStudio {...props}/><details className="judge-advanced"><summary>已采集的任务与旧版 Skill 记录</summary><TaskBoard {...props}/></details></>;
    if(page===6)return <EvidenceStory {...props}/>;
    if(page===7)return <><QualityStory {...props}/><details className="judge-advanced"><summary>采集覆盖与原始失败记录</summary>{coverage()}{table(problems,"失败 / 不支持 / 取消记录")}</details></>;
    if(page===8)return <UsageStory {...props}/>;
    return (
      <>
        <DataStory rows={rows} coverage={bundle.coverage} onSelect={setSelected}/>
        {!cloud && <section className="eg-ops-panel">
          <div className="eg-ops-panel-head">
            <h2>本地离线归档</h2>
            <button disabled={busy} onClick={() => readArchive()}>
              读取归档列表
            </button>
          </div>
          <div className="eg-ops-actions">
            {archives.map((item) => (
              <button
                key={item.id}
                disabled={busy}
                onClick={() => readArchive(item.id)}
              >
                {item.title} · {item.id.slice(-8)}
              </button>
            ))}
          </div>
          <p className="eg-ops-note">
            通过同源 API 读取已归档数据；访问密钥使用顶部连接设置。
          </p>
        </section>}
        <section className="eg-ops-panel">
          <div className="eg-ops-panel-head">
            <h2>{cloud ? "云端快照与离线导出" : "本地与离线工作区"}</h2>
            <small>{SCHEMA}</small>
          </div>
          <div className="eg-ops-source-info">
            <h3>{bundle.dataset.title}</h3>
            <details><summary>数据集编号与格式</summary><p>{bundle.dataset.id} · {SCHEMA}</p></details>
            <p>快照时间：{fmtTime(bundle.dataset.exportedAt)}</p>
            <p>
              {bundle.records.length} 条记录 · 当前筛选 {rows.length} 条
            </p>
            <p>
              {cloud ? "导入只在当前浏览器中查看，不写入云端；点击“刷新云端数据”恢复实时视图。导出包含当前筛选的记录和采样时间。" : "离线文件只进入浏览器内存。刷新页面将清除数据与访问密钥；请导出保存。归档到本地服务需要独立 Dashboard 授权。"}
            </p>
            <div className="eg-ops-actions">
              <button onClick={() => input.current?.click()}>导入 JSON</button>
              <button onClick={download} disabled={!bundle.records.length}>
                导出当前筛选
              </button>
              {!cloud && <button
                disabled={busy || mode !== "imported"}
                onClick={archiveImport}
              >
                归档到本地追踪库
              </button>}
              <button
                onClick={() => {
                  generation.current++;
                  controller.current?.abort();
                  setBusy(false);
                  accept(sampleBundle(), "sample");
                  setNotice("当前为模拟样例，不代表真实运行结果。");
                }}
              >
                载入模拟样例
              </button>
              <button
                onClick={() => {
                  generation.current++;
                  controller.current?.abort();
                  setBusy(false);
                  accept(emptyBundle(), "offline");
                  setTeamToken("");
                  setOpsToken("");
                  setNotice("当前内存数据与密钥已清除。");
                }}
              >
                清除当前会话
              </button>
            </div>
          </div>
        </section>
        <details className="judge-advanced"><summary>详细采集覆盖声明</summary>{coverage()}<pre>{json(bundle.coverage || {})}</pre></details>
      </>
    );
  }
  return (
    <div className={`eg-ops ${page!==12?"eg-judge":""}`}>
      <aside className="eg-ops-sidebar">
        <a className="eg-ops-brand" href="/dashboard">
          <b>EG</b>
          <span>
            EvidenceGuard<small>OBSERVABILITY CONSOLE</small>
          </span>
        </a>
        <div className="eg-ops-workspace">
          <span className="eg-ops-dot" />
          <strong>{cloud ? "比赛云端工作区" : "本地开发工作区"}</strong>
          <small>{cloud ? "Singapore / Live telemetry" : "研发追踪 / Offline ready"}</small>
        </div>
        <nav aria-label="Dashboard 页面">
          <p className="eg-ops-nav-label">作品与真实效果</p>
          {[12,5,14,13,0,3,2].map(i=><button key={i} aria-current={page===i?"page":undefined} className={page===i?"active":""} onClick={()=>openPage(i)}><span>{glyphs[i]}</span>{pages[i]}</button>)}
          <details className="eg-nav-more" open={[1,4,6,7,8,9,10,11].includes(page)||undefined}><summary>开发诊断 · 8 个页面</summary>
            {[6,7,1,4,8,9,10,11].map(i=><button key={i} aria-current={page===i?"page":undefined} className={page===i?"active":""} onClick={()=>openPage(i)}><span>{glyphs[i]}</span>{pages[i]}</button>)}
          </details>
        </nav>
        <div className="eg-ops-sidebar-bottom">
          <span>{mode === "cloud" ? "CLOUD / READ ONLY" : mode === "local" ? "LOCAL API" : "OFFLINE WORKSPACE"}</span>
          <p>
            只读追踪与诊断
            <br />
            {cloud ? "真实服务 · 提示词 · 执行链路" : "无需服务器 root 权限"}
          </p>
          {!cloud && <a href="/">返回 EvidenceGuard App ↗</a>}
        </div>
      </aside>
      <main className="eg-ops-main">
        <header className="eg-ops-topbar">
          <span>
            EvidenceGuard <i>/</i> 作品与运行 <i>/</i> {pages[page]}
          </span>
          <span className="eg-ops-badge">
            {page === 12 ? "浏览器演示 · 示例数据" : synthetic
              ? "模拟样例"
              : mode === "cloud" ? "云端实时 · 免登录只读" : mode === "local"
                ? "本地服务"
                : mode === "imported"
                  ? "导入数据 · 未核验"
                  : "等待数据"}
          </span>
        </header>
        {page !== 12 && <div className="eg-ops-heading">
          <div>
            <p>READ THE RESULT · FOLLOW THE EVIDENCE</p>
            <h1>{pages[page]}</h1>
            <span>{[
              "从一条真实任务开始，快速读懂 Agent 如何工作、结果如何产生。",
              "手机通过官方 SDK 连接硬件；这里核对画面如何进入云端。",
              "逐步回放需求、模型调用、工具执行与最终交付。",
              "Agent Loop：上下文 → 模型 ⇄ 工具 → 证据核验 → 最终回复。",
              "系统指令、对话上下文与工具定义，都关联到具体一次调用。",
              "从自然语言生成规则，配合实拍画面理解框选、修改与确认。",
              "回到图片与录像本身，核对结论依据和来源边界。",
              "分开阅读已观测结果、无法确认和仍待真机验收的能力。",
              "哪些模型实际被调用、花了多久、记录了多少用量。",
              "数据来源、采集范围与离线导入导出。",
              "主机是否健康，三个后端环境是否仍在运行。",
              "实际运行进程、磁盘源码与仓库基准是否一致。",
              "", "把图片、模型理解与可见事实放在同一处查看。",
              "从查询文字到候选片段，再到视频复核与播放证据。"
            ][page]}</span>
          </div>
          <div className="eg-ops-actions">
            <button onClick={() => input.current?.click()}>
              ↑ 导入离线数据
            </button>
            <button onClick={download} disabled={!rows.length}>
              ↓ 导出
            </button>
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                cloud ? (setMode("cloud"),setRefreshNumber(n=>n+1)) : mode === "local" ? refresh() : setConnecting(!connecting)
              }
            >
              {busy
                ? "正在读取…"
                : cloud ? "刷新云端数据" : mode === "local"
                  ? "刷新本地数据"
                  : "连接本地服务"}
            </button>
          </div>
        </div>}
        {cloud && page !== 12 && <div className="eg-ops-cloud-controls">
          <label>后端环境<select value={environment} onChange={e=>{setEnvironment(e.target.value);const url=new URL(location.href);url.searchParams.set("environment",e.target.value);history.replaceState({},"",url);setMode("cloud");setLiveAt(0);setBundle(emptyBundle());setFilters(initialFilters);}}>{environments.map(e=><option key={e.id} value={e.id}>{e.title}</option>)}</select></label>
          <span className={`eg-ops-dot ${cloudFailed||bundle.coverage?.stale?"bad":""}`}/><strong>{cloudFailed||bundle.coverage?.stale?"采集连接过期 · 以下为上次快照":mode!=="cloud"?"当前浏览离线数据":bundle.coverage?.observability==="connected"?"真实服务已连接":"采集状态待确认"}</strong>
          <span>{liveAt ? `最近读取 ${new Date(liveAt).toLocaleTimeString("zh-CN",{hour12:false})}` : "连接采集服务…"}</span>
        </div>}
        {!cloud && page !== 12 && <div className="eg-ops-notice" role="status"><span><strong>云端连接：</strong>{discovery} 当前网址：{location.host}。离线演示可以独立使用。</span><button onClick={() => setDiscoveryNumber(n => n + 1)}>重新连接云端</button></div>}
        <input
          ref={input}
          type="file"
          accept=".json,application/json"
          aria-label="导入追踪 JSON"
          hidden
          onChange={(e) => void importFile(e.target.files?.[0])}
        />
        {connecting && (
          <form
            className="eg-ops-connect"
            onSubmit={(e) => {
              e.preventDefault();
              void refresh();
            }}
          >
            <label>
              团队访问令牌（如已配置）
              <input
                type="password"
                autoComplete="off"
                value={teamToken}
                onChange={(e) => setTeamToken(e.target.value)}
              />
            </label>
            <label>
              Dashboard 独立密钥（如已配置）
              <input
                type="password"
                autoComplete="off"
                value={opsToken}
                onChange={(e) => setOpsToken(e.target.value)}
              />
            </label>
            <button type="submit" disabled={busy}>
              读取同源本地 API
            </button>
            <small>密钥仅存于当前页面内存。后端需启用 EG_OPS_ENABLED=1。</small>
          </form>
        )}
        {error && (
          <div className="eg-ops-alert" role="alert">
            {error}
            <button aria-label="关闭错误" onClick={() => setError("")}>
              ×
            </button>
          </div>
        )}
        {notice && (
          <div className="eg-ops-notice" role="status">
            {notice}
            <button aria-label="关闭提示" onClick={() => setNotice("")}>
              ×
            </button>
          </div>
        )}
        {page !== 12 && <div className={`eg-ops-provenance ${synthetic ? "synthetic" : ""}`}>
          <span className="eg-ops-dot" />
          <strong>
            {synthetic ? "模拟数据 · 不用于业务结论" : bundle.dataset.title}
          </strong>
          <span>
            快照 {fmtTime(bundle.dataset.exportedAt)} · {rows.length} /{" "}
            {bundle.records.length} 条
          </span>
          {mode !== "local" && mode !== "cloud" && <span>离线内容不会自动更新</span>}
        </div>}
        {(page < 10 || page > 12) && <details className="judge-filter-fold"><summary>筛选记录 · {filtered?"有生效条件":"全部时间 / 全部来源"}</summary><section className="eg-ops-filters" aria-label="全局筛选">
          <label>
            时间窗口
            <select
              value={filters.hours}
              onChange={(e) =>
                setFilters({ ...filters, hours: e.target.value })
              }
            >
              <option value="">全部时间</option>
              <option value="1">快照前 1 小时</option>
              <option value="24">快照前 24 小时</option>
              <option value="168">快照前 7 天</option>
            </select>
          </label>
          <label>
            平台
            <select
              value={filters.platform}
              onChange={(e) =>
                setFilters({ ...filters, platform: e.target.value })
              }
            >
              <option value="">全部平台</option>
              {["ios", "web", "backend"].map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label>
            记录来源
            <select
              value={filters.source}
              onChange={(e) =>
                setFilters({ ...filters, source: e.target.value })
              }
            >
              <option value="">全部来源</option>
              {sources.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            设备
            <select
              value={filters.device}
              onChange={(e) =>
                setFilters({ ...filters, device: e.target.value })
              }
            >
              <option value="">全部设备</option>
              {devices.map((s) => (
                <option key={s} value={s}>{deviceLabel(s,bundle.records)}</option>
              ))}
            </select>
          </label>
          <label className="eg-ops-search">
            搜索
            <input
              placeholder="Trace / 模型 / 事件 / 状态"
              value={filters.query}
              onChange={(e) =>
                setFilters({ ...filters, query: e.target.value })
              }
            />
          </label>
          <button onClick={() => setFilters(initialFilters)}>重置</button>
        </section></details>}
        {filtered && page !== 12 && <div className="eg-ops-notice" role="status"><span>全局筛选正在生效：当前 {rows.length} / {bundle.records.length} 条记录。搜索“{filters.query || "全部文字"}”与设备、时间条件会影响各数据页面。</span><button onClick={() => setFilters(initialFilters)}>清除全部筛选</button></div>}
        <div className="eg-ops-content">{content()}</div>
        <footer>
          时间为服务端接收或快照时间；客户端来源不等于硬件核验。· {SCHEMA}
        </footer>
      </main>
      {(selected || trace) && (
        <div
          className="eg-ops-detail-overlay"
          onClick={() => {
            setSelected(null);
            setTrace(null);
          }}
        >
          <section
            className="eg-ops-detail"
            role="dialog"
            aria-modal="true"
            aria-label="追踪详情"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setSelected(null);
                setTrace(null);
              }
            }}
          >
            <button
              autoFocus
              className="eg-ops-close"
              onClick={() => {
                setSelected(null);
                setTrace(null);
              }}
            >
              关闭详情 ×
            </button>
            <p className="eg-ops-nav-label">INSPECT / READ ONLY</p>
            <h2>{selected?eventLabel(selected.name):"任务运行时间线"}</h2>
            {trace && (
              <>
                <p className="eg-ops-note">
                  {traceLabel(trace,detailRecords)} · 同一任务
                  的已载入记录（历史分页未载入的步骤不在此处）；仅同一进程内的 duration
                  可直接比较。
                </p>
                <AgentCycle records={detailRecords.filter(r=>r.traceId===trace)} onSelect={r=>{setSelected(r as Row);setTrace(null);}} />
                <div className="eg-ops-timeline">
                  {detailRecords
                    .filter((r) => r.traceId === trace)
                    .sort((a, b) => a.at - b.at)
                    .map((r) => (
                      <button
                        key={r.id}
                        onClick={() => {
                          setSelected(r);
                          setTrace(null);
                        }}
                      >
                        <small>
                          {fmtTime(r.at)} · {r.platform}
                        </small>
                        <strong>
                          {eventLabel(r.name)} {badge(r.status)}
                        </strong>
                        <span>
                          {r.parentSpanId ? '关联到上一步执行' : '任务起点 / 未记录上游'}
                        </span>
                      </button>
                    ))}
                </div>
              </>
            )}
            {selected && (
              <>
                <p>
                  {badge(selected.status)} · {selected.platform} ·{" "}
                  {fmtDuration(selected.durationMs)}
                </p>
                <div className="eg-ops-actions">
                  <button
                    onClick={() => {
                      setTrace(selected.traceId);
                      setSelected(null);
                    }}
                  >
                    查看完整 Trace
                  </button>
                  {selected.data.promptId && (
                    <button
                      onClick={() => {
                        const prompt = detailRecords.find(
                          (r) => r.id === selected.data.promptId,
                        );
                        if (prompt) setSelected(prompt);
                        else setError("此离线包未包含关联提示词快照");
                      }}
                    >
                      查看关联提示词
                    </button>
                  )}
                </div>
                <RecordContent record={selected} records={detailRecords} />
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function Empty() {
  return (
    <div className="eg-ops-empty">
      <span>◌</span>
      <strong>当前范围没有记录</strong>
      <p>
        连接本地服务或导入追踪
        JSON；也可以在“数据与版本”载入明确标注的模拟样例。
      </p>
    </div>
  );
}
