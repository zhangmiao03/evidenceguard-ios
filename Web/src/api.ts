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
export type MediaSession = { id: string; token: string; deviceId: string };
export type CaptureCommand = {
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
  ) {
    super(message);
  }
}
const key = "evidenceguard.web.installation";
let installation = localStorage.getItem(key);
if (!installation) {
  installation = crypto.randomUUID();
  localStorage.setItem(key, installation);
}

export const api = {
  token: "",
  async request<T>(
    path: string,
    body?: unknown,
    session?: MediaSession,
    method?: string,
  ): Promise<T> {
    if (!path.startsWith("/api/")) throw new Error("请求不属于当前服务");
    const headers: Record<string, string> = {
      "X-EG-Installation-ID": installation!,
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    if (session) headers["X-EG-Media-Session"] = session.token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(path, {
      method: method || (body === undefined ? "GET" : "POST"),
      headers,
      signal: AbortSignal.timeout(12000),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new APIError(
        typeof data.detail === "string"
          ? data.detail
          : `请求未完成（${response.status}）`,
        response.status,
      );
    }
    return response.json();
  },
  async media(path: string): Promise<string> {
    if (!/^\/api\/media\/[a-f0-9]{64}$/.test(path))
      throw new Error("无效的证据地址");
    const r = await fetch(path, {
      headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
    });
    if (!r.ok) throw new Error("证据图片读取失败");
    return URL.createObjectURL(await r.blob());
  },
};
