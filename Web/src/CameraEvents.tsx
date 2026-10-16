import { useEffect, useState } from "react";
import { api, type Device } from "./api";
import { ImageEvidence } from "./ProductUI";
import type { CameraEventTimeline } from "./product-types";

export function CameraEvents({ devices, initial }: { devices: Device[]; initial?: CameraEventTimeline | null }) {
  const [camera, setCamera] = useState(""), [data, setData] = useState(initial), [error, setError] = useState("");
  useEffect(() => { if (!camera) setData(initial); }, [initial, camera]);
  useEffect(() => {
    let active = true, loading = false;
    const load = async () => {
      if (loading || document.hidden) return; loading = true;
      try { const result = await api.request<CameraEventTimeline>("/api/sdk/events" + (camera ? `?cameraId=${encodeURIComponent(camera)}` : "")); if (active) { setData(result); setError(""); } }
      catch (e) { if (active) setError(e instanceof Error ? e.message : "事件读取未完成"); } finally { loading = false; }
    };
    void load(); const timer = setInterval(() => void load(), 5000);
    return () => { active = false; clearInterval(timer); };
  }, [camera]);
  const review: Record<string,string> = { saved: "已保存，未视觉核验", pending: "等待视觉核验", running: "视觉核验中", completed: "已完成缩略图核验", metadata_only: "仅设备报告，暂无可核验图片", unavailable: "暂无法视觉核验", failed: "核验失败" };
  return <section className="card camera-events">
    <div className="section-heading"><h2>最近设备事件</h2><label>筛选设备<select value={camera} onChange={e => setCamera(e.target.value)}><option value="">全部设备</option>{devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label></div>
    <p className="hint">来自官方事件同步，仅覆盖已导入记录。锁屏、断网或同步暂停期间不保证连续覆盖。</p>
    {error && <p role="alert" className="error">{error}</p>}
    {!data?.events.length && <p>暂无已导入事件。可在 iOS 官方设备页开启前台事件同步。</p>}
    {data?.events.map(event => <article key={event.id} className="camera-event">
      {event.imageUrl ? <ImageEvidence path={event.imageUrl} alt={`${event.deviceName} 的事件缩略图`} /> : <div className="event-no-image">本条无图片</div>}
      <div><strong>{event.deviceName} · {event.detectionType || "设备事件"}</strong>
        <p>设备事件时间 {new Date(event.startMs).toLocaleString("zh-CN", { hour12: false })}</p>
        <p>{review[event.reviewStatus] || "等待核验"} · {event.hasVideo ? "SDK 标记有录像，尚未下载" : "未标记可用录像"}</p>
        <details><summary>查看记录说明</summary><p>{event.reason}</p><small>设备标签不等于模型确认；事件缩略图也不是实时画面。</small></details>
      </div>
    </article>)}
    {data?.truncated && <p>这里只显示最近 100 条，请筛选设备缩小范围。</p>}
  </section>;
}
