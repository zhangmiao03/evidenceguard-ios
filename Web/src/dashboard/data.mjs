export const SCHEMA = "evidenceguard.ops/v1";
export const MAX_BYTES = 20_000_000;
const id = /^[A-Za-z0-9_.:-]{1,120}$/;
const finite = (v) => typeof v === "number" && Number.isFinite(v);
const object = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/** Validate an inert data file, never evaluate content or fetch its references. */
export function validateBundle(value) {
  if (!object(value) || value.schemaVersion !== SCHEMA)
    throw Error("不支持的追踪文件版本");
  if (new TextEncoder().encode(JSON.stringify(value)).length > MAX_BYTES)
    throw Error("文件超过 20 MB");
  const ds = value.dataset;
  if (
    !object(ds) ||
    typeof ds.id !== "string" ||
    !id.test(ds.id) ||
    typeof ds.title !== "string" ||
    ds.title.length > 200 ||
    !["local", "synthetic", "imported"].includes(ds.source) ||
    !finite(ds.exportedAt)
  )
    throw Error("数据集信息无效");
  if (!Array.isArray(value.records) || value.records.length > 10000)
    throw Error("记录必须为数组且不超过 10000 条");
  const seen = new Set();
  for (const r of value.records) {
    if (!object(r)) throw Error("记录无效");
    for (const key of ["id", "name", "traceId", "spanId"])
      if (typeof r[key] !== "string" || !id.test(r[key]))
        throw Error(`记录标识无效：${key}`);
    if (seen.has(r.id)) throw Error("文件包含重复记录 ID");
    seen.add(r.id);
    if (
      r.parentSpanId != null &&
      (typeof r.parentSpanId !== "string" || !id.test(r.parentSpanId))
    )
      throw Error("父 span 无效");
    if (
      !["event", "model", "prompt", "resource"].includes(r.kind) ||
      !["backend", "web", "ios"].includes(r.platform) ||
      !["local", "client", "synthetic", "snapshot"].includes(r.source)
    )
      throw Error("记录类型、平台或来源无效");
    if (
      typeof r.status !== "string" ||
      r.status.length > 80 ||
      !finite(r.at) ||
      !object(r.data)
    )
      throw Error("记录数据无效");
    if (r.durationMs != null && (!finite(r.durationMs) || r.durationMs < 0))
      throw Error("耗时无效");
  }
  if (value.coverage !== undefined && !object(value.coverage))
    throw Error("覆盖说明无效");
  return value;
}

export function sanitizeData(value, depth = 0) {
  if (depth > 16) return "[depth omitted]";
  if (Array.isArray(value))
    return value.slice(0, 100).map((v) => sanitizeData(v, depth + 1));
  if (object(value))
    return Object.fromEntries(
      Object.entries(value)
        .slice(0, 100)
        .map(([k, v]) => [
          k.slice(0, 100),
          /authorization|api.?key|secret|password|credential|tokenhash|imagebase64|^token$|^sn$|accountid|clientid|importedby/i.test(
            k,
          )
            ? "[redacted]"
            : sanitizeData(v, depth + 1),
        ]),
    );
  if (typeof value === "string") {
    if (value.includes("data:") && value.includes(";base64,"))
      return "[binary omitted]";
    return value
      .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
      .replace(
        /(api[_-]?key|password|secret|access[_-]?token)["']?\s*[=:]\s*["']?[^\s,;"'}]+/gi,
        "$1=[redacted]",
      )
      .replace(
        /\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,})\b/g,
        "[credential omitted]",
      )
      .replace(/https?:\/\/[^\s"<>]+/g, "[remote URL omitted]")
      .slice(0, 16000);
  }
  return value;
}

export function sanitizeBundle(bundle) {
  return {
    schemaVersion: SCHEMA,
    dataset: {
      id: bundle.dataset.id,
      title: sanitizeData(bundle.dataset.title),
      source: bundle.dataset.source,
      exportedAt: bundle.dataset.exportedAt,
    },
    records: bundle.records.map((r) => ({
      id: r.id,
      kind: r.kind,
      name: r.name,
      at: r.at,
      traceId: r.traceId,
      spanId: r.spanId,
      parentSpanId: r.parentSpanId ?? null,
      platform: r.platform,
      source: r.source,
      status: r.status,
      durationMs: r.durationMs ?? null,
      data: sanitizeData(r.data),
    })),
    coverage: sanitizeData(bundle.coverage || {}),
  };
}

export function selectRecords(bundle, filters) {
  const cutoff = filters.hours
    ? bundle.dataset.exportedAt - Number(filters.hours) * 3600
    : -Infinity;
  const query = (filters.query || "").toLowerCase();
  return bundle.records
    .filter(
      (r) =>
        r.at >= cutoff &&
        (!filters.platform || r.platform === filters.platform) &&
        (!filters.source || r.source === filters.source) &&
        (!filters.device ||
          r.data.deviceId === filters.device ||
          r.data.cameraId === filters.device ||
          r.data.id === filters.device) &&
        (!query ||
          [
            r.name,
            r.traceId,
            r.status,
            r.data.model,
            r.data.tool,
            r.data.deviceId,
          ]
            .join(" ")
            .toLowerCase()
            .includes(query)),
    )
    .sort((a, b) => a.at - b.at);
}

export function metrics(rows) {
  const calls = rows.filter((r) => r.kind === "model");
  const usage = calls.filter(
    (r) => object(r.data.usage) && finite(r.data.usage.total_tokens),
  );
  const durations = calls
    .map((r) => r.durationMs)
    .filter(finite)
    .sort((a, b) => a - b);
  return {
    events: rows.filter((r) => r.kind === "event").length,
    calls: calls.length,
    traces: new Set(
      rows.filter((r) => r.kind !== "resource").map((r) => r.traceId),
    ).size,
    httpSuccess: calls.length
      ? calls.filter((r) => r.status === "http_ok").length / calls.length
      : null,
    usageCalls: usage.length,
    tokens: usage.length
      ? usage.reduce((n, r) => n + r.data.usage.total_tokens, 0)
      : null,
    p95: durations.length
      ? durations[Math.ceil(durations.length * 0.95) - 1]
      : null,
    clientEvents: rows.filter((r) => r.source === "client").length,
  };
}

export function exportBundle(bundle, rows, filters) {
  const ids = new Set(rows.map((r) => r.id));
  const prompts = new Set(
    rows.filter((r) => r.kind === "model").map((r) => r.data.promptId),
  );
  const related = bundle.records.filter(
    (r) => !ids.has(r.id) && prompts.has(r.id),
  );
  const exportID =
    typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
          b.toString(16).padStart(2, "0"),
        ).join("");
  return {
    ...bundle,
    dataset: {
      ...bundle.dataset,
      id: "export-" + exportID,
      exportedAt: bundle.dataset.exportedAt,
    },
    records: [...rows, ...related],
    coverage: {
      ...bundle.coverage,
      filters,
      exportedRecords: rows.length,
      relatedPrompts: related.length,
      parentDataset: bundle.dataset.id,
    },
  };
}

export function emptyBundle() {
  return {
    schemaVersion: SCHEMA,
    dataset: {
      id: "empty",
      title: "尚未加载数据",
      source: "local",
      exportedAt: 0,
    },
    records: [],
    coverage: {},
  };
}

/** Explicitly synthetic, deterministic fixture. Never loaded automatically. */
export function sampleBundle() {
  const at = Date.UTC(2026, 9, 14, 6) / 1000;
  const records = [];
  const add = (
    id,
    kind,
    name,
    traceId,
    spanId,
    offset,
    status,
    data = {},
    extra = {},
  ) =>
    records.push({
      id,
      kind,
      name,
      traceId,
      spanId,
      parentSpanId: null,
      at: at + offset,
      platform: "backend",
      source: "synthetic",
      status,
      durationMs: null,
      data,
      ...extra,
    });
  for (let i = 0; i < 12; i++) {
    const t = "demo-run-" + (i + 1),
      s = "agent-" + i,
      m = "model-" + i,
      p = "prompt-" + i,
      offset = -i * 900;
    add(
      t + "-client",
      "event",
      "api.completed",
      t,
      "client-" + i,
      offset,
      "completed",
      { deviceId: i % 2 ? "demo-doorbell" : "demo-indoor" },
      { platform: i % 2 ? "web" : "ios", durationMs: 98 },
    );
    add(t + "-start", "event", "agent.started", t, s, offset + 0.1, "observed");
    add(
      p,
      "prompt",
      "request.snapshot",
      t,
      m,
      offset + 0.2,
      "observed",
      {
        contentCapture: false,
        hashMeaning: "synthetic example",
        request: {
          model: "demo-vision-model",
          messages: [
            {
              role: "system",
              content: "这是模拟提示词。只描述可见事实；遮挡时返回 UNKNOWN。",
            },
            {
              role: "user",
              content: {
                omitted: "dynamic content (capture disabled)",
                characters: 46,
              },
            },
          ],
        },
      },
      { parentSpanId: s },
    );
    add(
      t + "-model",
      "model",
      i % 2 ? "chat" : "image_review",
      t,
      m,
      offset + 1,
      i === 3 ? "http_error" : "http_ok",
      {
        model: i % 2 ? "demo-chat-model" : "demo-vision-model",
        operation: i % 2 ? "chat" : "image_review",
        promptId: p,
        httpStatus: i === 3 ? 429 : 200,
        usage:
          i < 9
            ? {
                prompt_tokens: 840 + i * 30,
                completion_tokens: 120,
                total_tokens: 960 + i * 30,
              }
            : null,
      },
      { parentSpanId: s, durationMs: 450 + i * 132 },
    );
    if (i % 2 === 0)
      add(
        t + "-frame",
        "event",
        "capture.frame_accepted",
        t,
        "capture-" + i,
        offset + 0.3,
        "accepted",
        {
          deviceId: "demo-indoor",
          requestId: "capture-" + i,
          capturedAt: null,
          timestampMeaning: "client_live_sample",
        },
        { parentSpanId: s },
      );
    add(
      t + "-end",
      "event",
      "agent.finished",
      t,
      s,
      offset + 2,
      i === 3 ? "failed" : "completed",
      {},
      { durationMs: 1800 + i * 132 },
    );
  }
  for (const [id, name, data] of [
    [
      "indoor",
      "live_devices",
      { id: "demo-indoor", name: "客厅云台 · 模拟", model: "T8171" },
    ],
    [
      "doorbell",
      "live_devices",
      { id: "demo-doorbell", name: "门铃 · 模拟", model: "T8214" },
    ],
    [
      "skill",
      "skills",
      {
        id: "demo-skill",
        name: "室内区域守护 · 模拟",
        status: "draft",
        cameraId: "demo-indoor",
      },
    ],
    [
      "trial",
      "skill_trials",
      { id: "demo-trial", status: "completed", verdict: "uncertain" },
    ],
    [
      "recording",
      "recordings",
      { id: "demo-recording", status: "ready", duration: 32 },
    ],
  ])
    add(
      "resource-" + id,
      "resource",
      name,
      "snapshot:" + id,
      "snapshot:" + id,
      3,
      "snapshot",
      data,
    );
  return {
    schemaVersion: SCHEMA,
    dataset: {
      id: "synthetic-demo-v1",
      title: "跨端观察链路 · 模拟样例",
      source: "synthetic",
      exportedAt: at + 5,
    },
    records,
    coverage: {
      synthetic: true,
      contentCapture: false,
      limitations: ["仅验证交互，不代表设备、模型或团队运行结果"],
    },
  };
}
