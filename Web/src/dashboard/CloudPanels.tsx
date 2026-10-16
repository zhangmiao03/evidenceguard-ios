type Item = Record<string, any>;
const number = (n: unknown, unit = "") => typeof n === "number" ? `${n.toFixed(1)}${unit}` : "—";
const bytes = (n: unknown) => typeof n !== "number" ? "—" : n > 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GB` : n > 1024 ** 2 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${(n / 1024).toFixed(1)} KB`;
const time = (at: number) => at ? new Date(at * 1000).toLocaleString("zh-CN", { hour12: false }) : "尚未采集";

export function CloudStatus({ coverage }: { coverage?: Item }) {
  const s = coverage?.server || {};
  return <div className="eg-ops-cloud-status">
    <span className={`eg-ops-dot ${coverage?.stale || coverage?.observability !== "connected" ? "bad" : ""}`} />
    <strong>{coverage?.stale ? "采样已过期" : coverage?.observability === "connected" ? "真实服务已连接" : "采集状态待确认"}</strong>
    <span>CPU {number(s.cpuPercent, "%")}</span>
    <span>内存 {bytes(s.memoryUsedBytes)} / {bytes(s.memoryTotalBytes)}</span>
    <span>每 5 秒采样 · {time(coverage?.sampledAt)}</span>
  </div>;
}

function History({ rows, field, total, label }: { rows: Item[]; field: string; total?: number; label: string }) {
  const valid = rows.filter(r => typeof r[field] === "number");
  if (valid.length < 2) return <p className="eg-ops-note">等待两个有效采样点</p>;
  const first = valid[0].at, span = Math.max(1, valid[valid.length - 1].at - first);
  const ceiling = total || Math.max(1, ...valid.map(r => r[field]));
  const points = valid.map(r => `${8 + ((r.at - first) / span) * 584},${112 - Math.min(1, r[field] / ceiling) * 100}`).join(" ");
  return <><svg className="eg-ops-spark" viewBox="0 0 600 124" role="img" aria-label={label}>
    {[12, 62, 112].map(y => <line key={y} x1="8" y1={y} x2="592" y2={y} stroke="#26374c" />)}
    <polyline points={points} fill="none" stroke="#62c9ee" strokeWidth="2.5" />
    {valid.map((r, i) => <circle key={i} cx={8 + ((r.at - first) / span) * 584} cy={112 - Math.min(1, r[field] / ceiling) * 100} r="2" fill="#62c9ee"><title>{time(r.at)} · {number(total ? r[field] / total * 100 : r[field], total ? "%" : "")}</title></circle>)}
  </svg><div className="eg-ops-axis"><span>{time(first)}</span><span>{time(valid[valid.length - 1].at)}</span></div></>;
}

export function ServerResources({ server }: { server?: Item }) {
  if (!server || server.errorType) return <section className="eg-ops-panel"><h2>服务器采样不可用</h2><p className="eg-ops-note">尚未取得有效的主机数据，缺失值不记为 0。</p></section>;
  const mem = server.memoryTotalBytes ? server.memoryUsedBytes / server.memoryTotalBytes * 100 : null;
  const disk = server.diskTotalBytes ? server.diskUsedBytes / server.diskTotalBytes * 100 : null;
  return <>
    <div className="eg-ops-kpis eg-ops-resource-kpis">
      {[["CPU 使用率", number(server.cpuPercent, "%"), `${server.cpuCount} 个逻辑 CPU · 主机总容量`],
        ["内存使用率", number(mem, "%"), `${bytes(server.memoryUsedBytes)} / ${bytes(server.memoryTotalBytes)}`],
        ["系统盘使用率", number(disk, "%"), `剩余 ${bytes(server.diskFreeBytes)}`],
        ["网络接收 / 发送", `${bytes(server.networkReceiveBytesPerSecond)} / ${bytes(server.networkSendBytesPerSecond)}`, "每秒 · 不含回环接口"]].map(([label,value,hint]) => <section className="eg-ops-kpi" key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></section>)}
    </div>
    <div className="eg-ops-grid">
      <section className="eg-ops-panel"><div className="eg-ops-panel-head"><h2>CPU 实时趋势</h2><small>0–100% · 约 5 秒采样</small></div><History rows={server.history || []} field="cpuPercent" total={100} label="服务器 CPU 使用率时间序列" /></section>
      <section className="eg-ops-panel"><div className="eg-ops-panel-head"><h2>内存实时趋势</h2><small>MemTotal − MemAvailable</small></div><History rows={server.history || []} field="memoryUsedBytes" total={server.memoryTotalBytes} label="服务器内存使用率时间序列" /></section>
    </div>
    <section className="eg-ops-panel"><div className="eg-ops-panel-head"><h2>实际后端进程</h2><small>{time(server.at)}</small></div>
      <div className="eg-ops-table-wrap"><table><thead><tr><th>环境 / 服务</th><th>状态</th><th>PID</th><th>进程 CPU</th><th>常驻内存</th><th>重启次数</th></tr></thead><tbody>{(server.services || []).map((s:Item) => <tr key={s.environment}><td><strong>{s.environment}</strong><small>{s.service}</small></td><td><span className={`eg-ops-badge ${s.state !== "active" ? "bad" : ""}`}>{s.state} / {s.subState}</span></td><td>{s.pid || "—"}</td><td>{number(s.cpuPercent, "%")}</td><td>{bytes(s.rssBytes)}</td><td>{s.restarts ?? "—"}</td></tr>)}</tbody></table></div>
      <p className="eg-ops-note">进程 CPU 的 100% 表示占用一个逻辑 CPU；首次采样不计算区间速率。主机已运行 {number(server.uptimeSeconds / 3600)} 小时。负载均值（1 / 5 / 15 分钟）：{(server.loadAverage || []).map((v:number) => v.toFixed(2)).join(" / ")}。</p>
    </section>
  </>;
}

export function DeploymentPanel({ deployment }: { deployment?: Item }) {
  if (!deployment) return <section className="eg-ops-panel"><h2>部署版本尚未采集</h2><p className="eg-ops-note">云端采集开启后显示进程启动时和当前磁盘的源码指纹。</p></section>;
  const d=deployment;
  return <>
    <section className="eg-ops-panel"><div className="eg-ops-panel-head"><h2>实际部署与仓库核对</h2><span className={`eg-ops-badge ${!d.processMatchesObserver || d.diskVsRunning?.length ? "bad" : ""}`}>{!d.processMatchesObserver ? "进程身份待核对" : d.diskVsRunning?.length ? "磁盘源码已变化" : "进程与启动指纹一致"}</span></div>
      <div className="eg-ops-health">{[["应用版本",d.appVersion || "未知"],["进程启动时间",time(d.startedAt)],["监控组件版本",d.observerRevision || "未知"],["仓库比对基准",d.referenceRevision || "未知"],["已核对 Python 文件",String(d.fileCount ?? "未知")],["与仓库基准差异",`${d.diskVsRepository?.length ?? "未知"} 个文件`]].map(([label,value]) => <div key={label}><span>{label}</span><strong className="eg-ops-mono">{value}</strong></div>)}</div>
      <p className="eg-ops-note">仓库基准是部署包携带的已提交版本。差异按 SHA-256 核对，不把版本号相同当成源码相同；启动指纹不等于重新读取运行中 Python 字节码。磁盘与启动指纹不同表示后续重启可能加载不同代码。</p>
    </section>
    <section className="eg-ops-panel"><div className="eg-ops-panel-head"><h2>仓库差异文件</h2><small>仅核对，不会在此覆盖部署</small></div><div className="eg-ops-table-wrap"><table><thead><tr><th>文件</th><th>差异</th><th>当前磁盘 SHA-256</th><th>仓库 SHA-256</th></tr></thead><tbody>{(d.diskVsRepository || []).map((f:Item) => <tr key={f.path}><td>{f.path}</td><td>{f.status}</td><td className="eg-ops-hash" title={f.actual}>{f.actual || "缺失"}</td><td className="eg-ops-hash" title={f.expected}>{f.expected || "仓库无此文件"}</td></tr>)}</tbody></table></div>{!d.diskVsRepository?.length && <p className="eg-ops-note">当前文件与仓库基准一致。</p>}</section>
    <section className="eg-ops-panel"><h2>源码集合指纹</h2><pre>{d.sourceFingerprint}</pre><details><summary>查看所有文件指纹</summary><pre>{JSON.stringify(d.files,null,2)}</pre></details></section>
  </>;
}

const phases = [
  {label:"任务开始",names:["agent.started","run_started","proactive_started"]},
  {label:"组装上下文",names:["context.prepared"]},
  {label:"调用模型",names:["model_started","request.snapshot","chat"]},
  {label:"执行工具",names:["tool.started","tool.finished","tool_started","tool_completed"]},
  {label:"模型继续判断",names:["model.output"]},
  {label:"返回最终结果",names:["agent.result","response_completed","agent.finished","proactive_finished"]},
];

export function AgentCycle({ records, onSelect }: { records:Item[]; onSelect:(record:Item)=>void }) {
  const sorted=[...records].sort((a,b)=>a.at-b.at);
  const models=sorted.filter(r=>r.kind==="model");
  const tools=sorted.filter(r=>r.name==="tool.finished");
  const finished=[...sorted].reverse().find(r=>["agent.finished","proactive_finished"].includes(r.name));
  const finalResult=[...sorted].reverse().find(r=>r.name==="agent.result");
  return <div className="eg-ops-cycle">
    <div className="eg-ops-panel-head"><h3>Agent 执行循环</h3><small>{models.length} 次真实模型 HTTP 调用 · {tools.length} 次工具执行 · {finished?.status || "等待结束回执"}</small></div>
    <div className="eg-ops-cycle-phases">{phases.map(p=>{
      const matches=sorted.filter(r=>p.names.includes(r.name));
      return <button key={p.label} disabled={!matches.length} onClick={()=>onSelect(p.label==="返回最终结果" && finalResult ? finalResult : matches[matches.length-1])}><span>{matches.length ? "●" : "○"}</span><strong>{p.label}</strong><small>{matches.length ? `${matches.length} 条回执` : "未观测到 / 不适用"}</small></button>;
    })}</div>
    <p className="eg-ops-note">工具结果可再次进入模型，循环次数以实际回执为准。工具无调用时可以直接回答；“未观测到”不代表通过。本视图展示可核对的执行轨迹，不包含模型内部推理。</p>
    {finalResult && <button className="eg-ops-final-result" onClick={()=>onSelect(finalResult)}><strong>查看最终回复</strong><span>{typeof finalResult.data.content?.answer==="string" ? finalResult.data.content.answer.slice(0,180) : "旧记录仅有摘要，无法恢复正文"}</span></button>}
    <div className="eg-ops-span-list">{sorted.filter(r=>r.kind==="model" || r.name==="tool.finished" || ["agent.finished","proactive_finished"].includes(r.name)).map(r=><button key={r.id} onClick={()=>onSelect(r)}><span className={`eg-ops-badge ${["failed","http_error","cancelled"].includes(r.status)?"bad":""}`}>{r.kind==="model"?"MODEL":r.name==="tool.finished"?"TOOL":"AGENT"}</span><strong>{r.data.tool || r.data.model || r.name}</strong><span>{r.durationMs == null ? "耗时未采集" : `${(r.durationMs/1000).toFixed(2)} s`}</span></button>)}</div>
  </div>;
}
