import { useRef, useState } from "react";
import { normalizedBox } from "./geometry.mjs";
import type { ROI } from "./types";
export function RegionEditor({
  url,
  box,
  region,
  mode,
  onChange,
}: {
  url?: string;
  box: ROI;
  region: ROI;
  mode: "target" | "region";
  onChange: (box: ROI) => void;
}) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const [pending, setPending] = useState<ROI | null>(null);
  const point = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height,
    };
  };
  const overlay = (value: ROI, kind: string) => (
    <span
      className={`roi ${kind}`}
      style={{
        left: `${value.x * 100}%`,
        top: `${value.y * 100}%`,
        width: `${value.width * 100}%`,
        height: `${value.height * 100}%`,
      }}
    >
      {kind === "target" ? "目标" : "关注区域"}
    </span>
  );
  if (!url)
    return (
      <div className="empty">
        暂无可用画面。连接摄像头或为回放选择录像后再圈选。
      </div>
    );
  return (
    <div
      className="region-editor"
      aria-label={`拖动圈选${mode === "target" ? "目标" : "关注区域"}`}
      onPointerDown={(e) => {
        start.current = point(e);
        setPending(null);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (start.current) setPending(normalizedBox(start.current, point(e)));
      }}
      onPointerUp={(e) => {
        if (start.current) {
          const result = normalizedBox(start.current, point(e));
          if (result) onChange(result);
        }
        start.current = null;
        setPending(null);
      }}
      onPointerCancel={() => {
        start.current = null;
        setPending(null);
      }}
    >
      <img src={url} alt="任务圈选画面" draggable={false} />
      {overlay(mode === "target" && pending ? pending : box, "target")}
      {overlay(mode === "region" && pending ? pending : region, "region")}
    </div>
  );
}
