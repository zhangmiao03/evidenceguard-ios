import { installationID, requireSecureConnection, newID, privateKey } from "./browser-support";
import type { Conflict } from "./product-types";
import { observe, routeTemplate } from "./telemetry";

export type Device = {
  id: string;
  sn: string;
  model: string;
  name: string;
  connection: string;
  evidence: string;
  capabilities: Record<string, string>;
  lastFrameUrl?: string;
};
export type MediaSession = { id: string; token: string; deviceId: string; traceId?: string };
export type CaptureCommand = {
  traceId?: string;
  parentSpanId?: string;
  requestId: string;
  afterSequence: number;
  deadline: number;
};
export type Capture = {
  id: string;
  status: string;
  reason: string;
  imageUrl?: string;
  sampledAt?: number;
  capturedAt?: number;
  timestampMeaning?: string;
};
export type Run = {
  id: string;
  status: string;
  message: string;
  text?: string;
  error?: string;
  captures?: Capture[];
};
export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public conflicts: Conflict[] = [],
  ) {
    super(message);
  }
}
export const installation = installationID();

export const api = {
  token: "",
  scoped() {
    return { ...this };
  },
  async request<T>(
    path: string,
    body?: unknown,
    session?: MediaSession,
    method?: string,
    traceOverride?: string,
    executorToken?: string,
  ): Promise<T> {
    if (!path.startsWith("/api/")) throw new Error("请求不属于当前服务");
    if (this.token) requireSecureConnection();
    const candidate = body && typeof body === "object" && "requestId" in body ? String(body.requestId) : "";
    const traceID = traceOverride || (/^[A-Za-z0-9_.:-]{1,120}$/.test(candidate) ? candidate : session?.traceId || newID());
    const track = (body !== undefined || (method && method !== "GET")) && !/\/(heartbeat|presence)$/.test(path);
    const started = performance.now();
    let outcome = "failed";
    const headers: Record<string, string> = {
      "X-EG-Installation-ID": installation!,
      "X-EG-Trace-ID": traceID,
    };
    if (location.protocol === "https:" || ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)) headers["X-EG-Private-Key"] = privateKey();
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    if (session) headers["X-EG-Media-Session"] = session.token;
    if (executorToken) headers["X-EG-Executor-Token"] = executorToken;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(path, {
        method: method || (body === undefined ? "GET" : "POST"),
        headers,
        signal: controller.signal,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new APIError(
          typeof data.detail === "string"
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail
                  .map((item: { msg?: string }) => item.msg || "输入无效")
                  .join("；")
              : `请求未完成（${response.status}）`,
          response.status,
          data.conflicts || [],
        );
      }
      const value = await response.json();
      outcome = "completed";
      return value;
    } finally {
      clearTimeout(timeout);
      if (track) observe({ name: outcome === "completed" ? "api.completed" : "api.failed", traceId: traceID, status: outcome, durationMs: performance.now() - started, route: routeTemplate(path) }, this.token);
    }
  },
  async uploadRecording(
    file: File,
    cameraId: string,
    recordedAt?: number,
  ): Promise<unknown> {
    if (!file.size || file.size > 150_000_000)
      throw new Error("请选择不超过 150 MB 的录像");
    if (this.token) requireSecureConnection();
    const query = new URLSearchParams({
      cameraId,
      title: file.name.replace(/\.[^.]+$/, ""),
    });
    if (recordedAt !== undefined) query.set("recordedAt", String(recordedAt));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(`/api/recordings?${query}`, {
        method: "POST",
        body: file,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/octet-stream",
          "X-EG-Installation-ID": installation,
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        },
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.detail === "string" ? body.detail : "录像上传未完成",
        );
      return body;
    } finally {
      clearTimeout(timeout);
    }
  },
  async media(path: string, timeoutMs = 12000): Promise<string> {
    if (this.token) requireSecureConnection();
    if (
      !/^\/api\/(?:media\/[a-f0-9]{64}|recordings\/[A-Za-z0-9_-]+\/(?:video|preview)|replay-evidence\/[A-Za-z0-9_-]+\/video|skill-trials\/[A-Za-z0-9_-]+\/video|camera\/frames\/[A-Za-z0-9_-]+\/[A-Za-z0-9_.-]+)$/.test(
        path,
      ) ||
      path.includes("..")
    )
      throw new Error("无效的证据地址");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const r = await fetch(path, {
        signal: controller.signal,
        headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
      });
      if (!r.ok) throw new Error("证据读取失败，请检查连接后重试");
      return URL.createObjectURL(await r.blob());
    } finally {
      clearTimeout(timeout);
    }
  },
};
