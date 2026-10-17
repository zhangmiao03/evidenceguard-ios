import { action, operationDetails, operationStatus, chatError } from "./chat-presentation.mjs";
import { useEffect, useState } from "react";
import { hardware, type HardwareReference, type HardwareDevice, type HardwareOperation, type HardwareSnapshot } from "./hardware-tools";
import { newID } from "./browser-support";

const noReferences: HardwareReference[] = [];
const terminal = (op: HardwareOperation) => ["completed", "failed", "cancelled"].includes(op.executionState) || op.leaseReleasedByHuman;

export function HardwareOperationCard({ operation, poll = true, deviceName, references = noReferences }: { operation: HardwareOperation; poll?: boolean; deviceName?: string; references?: HardwareReference[] }) {
  const [op, setOp] = useState(operation), [error, setError] = useState(""), [busy, setBusy] = useState(false), [note, setNote] = useState("");
  const [knownReferences, setKnownReferences] = useState<HardwareReference[]>(references);
  useEffect(() => { setKnownReferences(references); }, [references]);
  useEffect(() => { setOp(operation); }, [operation]);
  useEffect(() => {
    if (!poll || terminal(op)) return;
    let active = true, loading = false;
    const id = setInterval(async () => {
      if (loading || document.hidden) return; loading = true;
      try { const s = await hardware<HardwareSnapshot>("snapshot"); const next = s.operations.find(v => v.id === op.id); if (active && next) { setOp(next); setKnownReferences(s.operations.flatMap(o => o.result?.references || [])); } }
      catch { /* Keep the last receipt; never show success on a poll failure. */ }
      finally { loading = false; }
    }, 2000);
    return () => { active = false; clearInterval(id); };
  }, [op.id, op.executionState, poll]);
  async function act(path: string, body: unknown) {
    setBusy(true); setError("");
    try { setOp(await hardware<HardwareOperation>(path, body)); } catch (e) { setError(String(e instanceof Error ? e.message : e)); } finally { setBusy(false); }
  }
  return <article className="hardware-operation" aria-label="硬件操作回执">
    <strong>{action(op.tool)}</strong><p>{operationDetails(op, deviceName, knownReferences)}</p>
    <p role="status">{operationStatus(op)}</p>
    {op.executionState === "awaitingApproval" && <div className="actions">
      <button disabled={busy} className="primary" onClick={() => void act("confirmations", { operationId: op.id, requestHash: op.requestHash, decision: "approve" })}>确认这次操作</button>
      <button disabled={busy} onClick={() => void act("confirmations", { operationId: op.id, requestHash: op.requestHash, decision: "reject" })}>拒绝</button>
    </div>}
    {!terminal(op) && op.executionState !== "awaitingApproval" && <button disabled={busy} onClick={() => void act("call", { name: "camera_stop", arguments: { operationId: op.id }, idempotencyKey: newID(), platform: "web", taskId: op.taskId })}>取消 / 请求停止</button>}
    {op.executionState === "unknown" && !op.leaseReleasedByHuman && <div>
      <label>人工核对记录<input value={note} onChange={e => setNote(e.target.value)} placeholder="已检查实际设备状态（至少 10 字）" /></label>
      <button disabled={busy || note.trim().length < 10} onClick={() => void act("reconcile", { operationId: op.id, requestHash: op.requestHash, decision: "release_after_manual_check", evidence: note })}>已核对设备，解除操作占用</button>
    </div>}
    {op.leaseReleasedByHuman && <p>已人工释放；原物理结果仍为未知。</p>}
    {error && <p role="alert" className="error">{chatError(error)}</p>}
  </article>;
}

function template(snapshot: HardwareSnapshot, device: HardwareDevice | undefined, name: string) {
  const spec = snapshot.tools.find(t => t.name === name), args: Record<string, unknown> = {};
  if (!device || !spec) return "{}";
  const refs = snapshot.operations.filter(o => o.deviceId === device.id && o.taskId === `device:${device.id}`).flatMap(o => o.result?.references || []).filter(r => r.validUntil * 1000 > Date.now());
  const kinds: Record<string, string> = { referenceObservationId: "observation", eventRef: "event", presetRef: "preset", optionRef: "option", channelRef: "light", modeRef: "mode", replyRef: "reply" };
  for (const key of spec.inputSchema.required) {
    const property = spec.inputSchema.properties[key];
    args[key] = key === "deviceId" ? device.id : key === "expectedViewRevision" ? device.viewRevision : key === "expectedSettingsRevision" ? device.settingsRevision :
      kinds[key] ? refs.find(r => r.kind === kinds[key] && (!r.allowedTools?.length || r.allowedTools.includes(name)))?.id || "" :
      property.const ?? (Array.isArray(property.enum) ? property.enum[0] : property.type === "integer" || property.type === "number" ? property.minimum ?? 0 : property.type === "boolean" ? false : "");
  }
  return JSON.stringify(args, null, 2);
}

export function HardwarePanel({ deviceID }: { deviceID: string }) {
  const [snapshot, setSnapshot] = useState<HardwareSnapshot>({ devices: [], operations: [], tools: [] });
  const [selected, setSelected] = useState("camera_observe"), [args, setArgs] = useState("{}"), [diagnostic, setDiagnostic] = useState(false);
  const [note, setNote] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const device = snapshot.devices.find(d => d.id === deviceID);
  const refresh = async () => setSnapshot(await hardware<HardwareSnapshot>("snapshot"));
  useEffect(() => {
    let active = true, loading = false;
    const load = async () => { if (loading || document.hidden) return; loading = true; try { const s = await hardware<HardwareSnapshot>("snapshot"); if (active) { setSnapshot(s); setError(""); } } catch (e) { if (active) setError(e instanceof Error ? e.message : "工具服务不可用"); } finally { loading = false; } };
    void load(); const timer = setInterval(() => void load(), 3000);
    return () => { active = false; clearInterval(timer); };
  }, [deviceID]);
  useEffect(() => { setArgs(template(snapshot, device, selected)); }, [selected, deviceID, device?.capabilityRevision, device?.viewRevision, device?.settingsRevision]);
  async function action(run: () => Promise<unknown>) { setBusy(true); setError(""); try { await run(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "操作未完成"); } finally { setBusy(false); } }
  return <section className="card hardware-panel">
    <h2>硬件工具与执行回执</h2>
    <p className="hint">Web 直接接入提供直播与新帧。云台等控制需由前台在线的 iOS 原生 SDK 执行；网页按钮本身不具备设备控制通道。</p>
    {!device ? <p>尚未登记前台执行器。iOS 连接官方设备后登记；Web 打开当前设备直播后登记。</p> : <>
      <p>执行端 {device.executorPlatform} · {device.executorOnline ? "前台在线" : "已离线"} · 隐私 {device.privacy === "off" ? "关闭" : device.privacy === "on" ? "开启" : "待核对"}</p>
      <p className="hint">只登记已有执行路线。真机通过记录与 SDK 构件、设备型号和适配版本绑定；控制仍需逐次确认。</p>
      <details><summary>开发者工具检查</summary>
        <label>工具<select value={selected} onChange={e => setSelected(e.target.value)}>{Object.entries(device.routes).map(([name, r]) => <option key={name} value={name}>{name}{!r.ready ? "（未就绪）" : ""}</option>)}</select></label>
        <label><input type="checkbox" checked={diagnostic} onChange={e => setDiagnostic(e.target.checked)} />人工诊断（不跳过控制确认）</label>
        <label>请求参数<textarea aria-label="硬件请求参数" value={args} onChange={e => setArgs(e.target.value)} rows={6} spellCheck={false} /></label>
        <button onClick={() => setArgs(template(snapshot, device, selected))}>填入当前引用与版本</button>
        <button className="primary" disabled={busy || !device.executorOnline || !device.routes[selected]?.ready} onClick={() => void action(() => hardware("call", { name: selected, arguments: JSON.parse(args), idempotencyKey: newID(), platform: "web", diagnostic }))}>提交工具请求</button>
        <label>真机核验记录<input value={note} onChange={e => setNote(e.target.value)} placeholder="操作、现象与证据（至少 10 字）" /></label>
        <div className="actions">
          <button disabled={busy || note.trim().length < 10} onClick={() => void action(() => hardware("validations", { deviceId: deviceID, tool: selected, capabilityRevision: device.capabilityRevision, status: "passed", evidence: note }))}>记录此工具真机通过</button>
          <button disabled={busy || note.trim().length < 10} onClick={() => void action(() => hardware("validations", { deviceId: deviceID, tool: selected, capabilityRevision: device.capabilityRevision, status: "failed", evidence: note }))}>记录未通过</button>
        </div>
        {device.executorPlatform === "Web" && <><p>Web SDK 没有已接入的隐私回读。请先在官方界面核对隐私已关闭，再授权本会话 5 分钟人工诊断取样；这不会开启 Agent 自动工具权限。</p>
          <button disabled={busy || note.trim().length < 10} onClick={() => void action(() => hardware(`devices/${deviceID}/privacy-check`, { evidence: note }))}>已核对隐私关闭，仅授权诊断取样</button></>}
        <p>当前验证：{device.validationResults.filter(v => v.tool === selected).map(v => v.status).join(", ") || "尚未验证"}</p>
        <button disabled={busy} onClick={() => void action(() => hardware(`devices/${deviceID}/release`, {}))}>已停止原直播，释放执行端供另一端接入</button>
      </details>
    </>}
    {error && <p role="alert" className="error">{error}</p>}
    {snapshot.operations.filter(o => o.deviceId === deviceID).slice(0, 10).map(o => <HardwareOperationCard key={o.id} operation={o} poll={false} deviceName={device?.label} references={snapshot.operations.flatMap(o => o.result?.references || [])} />)}
  </section>;
}
