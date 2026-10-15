import { api, APIError, type Device, type MediaSession } from "./api";

export type HardwareOperation = {
  id: string; tool: string; deviceId: string; taskId: string; requestHash: string;
  executionState: string; executorPlatform: string; requestedPlatform: string; requesterPlatform?: string;
  arguments: Record<string, unknown>; sdkUsed?: boolean; physicalResult?: string;
  leaseReleasedByHuman?: boolean; error?: { message: string };
  result?: { data: Record<string, unknown>; references: HardwareReference[] };
};
export type HardwareReference = { id: string; kind: string; label?: string; ready?: boolean; validUntil: number; allowedTools?: string[] };
export type HardwareDevice = {
  id: string; label: string; executorPlatform: string; executorOnline: boolean; capabilityRevision: string;
  viewRevision: number; settingsRevision: number; privacy: string; privacySource?: string;
  routes: Record<string, { ready: boolean; sdkMapping: string }>;
  validationResults: { tool: string; status: string }[];
};
export type HardwareSnapshot = {
  devices: HardwareDevice[]; operations: HardwareOperation[];
  tools: { name: string; description: string; inputSchema: { required: string[]; properties: Record<string, Record<string, unknown>> } }[];
};
export type ExecutorSession = { executorId: string; token: string; deviceId: string };
type Claim = { command: "execute" | "stop" | null; operation?: HardwareOperation & { leaseToken: string } };
const wait = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
export const hardware = <T>(path: string, body?: unknown) => api.request<T>("/api/hardware/" + path, body);

// One host per existing product media session. This code never opens an SDK player
// or subscribes to raw frames: the existing LiveView answers the capture challenge.
export class WebToolExecutor {
  private stopped = false;
  private session?: ExecutorSession;
  private running?: Promise<void>;
  private work = new Set<Promise<void>>();
  private pending = new Map<string, Record<string, unknown>>();
  private client = api.scoped();
  private artifactAbort = new AbortController();
  constructor(private device: Device, private media: MediaSession, private report: (message: string) => void) {}
  start() { this.running = this.run(); }
  private request<T>(path: string, body?: unknown) {
    return this.client.request<T>("/api/hardware/" + path, body, undefined, undefined, undefined, this.session?.token);
  }
  private async run() {
    try {
      const timeout = setTimeout(() => this.artifactAbort.abort(), 12000);
      let bytes: ArrayBuffer;
      try {
        const response = await fetch("/sdk/index.js", { signal: this.artifactAbort.signal });
        if (!response.ok || !/javascript/.test(response.headers.get("content-type") || "")) throw new Error("缺少官方 Web SDK 构件");
        bytes = await response.arrayBuffer();
      } finally { clearTimeout(timeout); }
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const hash = Array.from(new Uint8Array(digest), v => v.toString(16).padStart(2, "0")).join("");
      if (this.stopped) return;
      this.session = await this.request<ExecutorSession>("executors", {
        deviceId: this.device.id, model: this.device.model, platform: "web", adapterVersion: "web-tools-1",
        sdkArtifactHash: hash, firmwareVersion: "unknown", privacy: "unknown", officialIdentityReady: true,
        routes: { camera_observe: { ready: true, sdkMapping: "product_live_challenge" } }, fields: {},
        sessionId: this.media.id, mediaToken: this.media.token,
      });
      if (!this.session.executorId || !this.session.token) { this.session = undefined; throw new Error("执行器登记回执不完整"); }
      let failures = 0;
      while (!this.stopped) {
        try {
          for (const [id, body] of this.pending) {
            await this.request(`executors/${this.session.executorId}/result`, body);
            this.pending.delete(id);
          }
          const claim = await this.request<Claim>(`executors/${this.session.executorId}/claim`, {});
          if (this.stopped) break;
          if (claim.command && claim.operation) {
            const work = this.execute(claim);
            this.work.add(work); void work.finally(() => this.work.delete(work));
          }
          failures = 0;
        } catch (e) {
          if (this.stopped) break;
          if ((e instanceof APIError && e.status < 500) || ++failures >= 3) throw e;
          // Retry the same receipt/claim only. Never replay the observation or SDK action.
          this.report("连接暂时中断，正在重新同步执行回执");
        }
        await wait(700);
      }
    } catch (e) {
      if (!this.stopped) this.report(e instanceof Error ? e.message : "硬件工具连接未完成");
    } finally {
      // Disconnect before media release and workspace switch. No control handoff is implicit.
      if (this.session) {
        try { await this.request(`executors/${this.session.executorId}/disconnect`, {}); }
        catch (e) { if (!(e instanceof APIError && e.status === 403)) this.report("工具执行端已停止；离线租约需在工具面板核对"); }
      }
    }
  }
  private async execute(claim: Claim) {
    const op = claim.operation!, session = this.session!;
    const key = op.id + ":" + claim.command;
    try {
      if (op.deviceId !== this.device.id || op.executorPlatform !== "Web") throw new Error("命令不属于此 Web 会话");
      if (claim.command === "execute" && op.tool === "camera_observe") {
        await this.request(`executors/${session.executorId}/observe`, { operationId: op.id, leaseToken: op.leaseToken });
        return;
      }
      // Observation has no physical movement. Its product challenge may finish,
      // but a stopped operation will not publish that frame as a tool result.
      this.pending.set(key, { operationId: op.id, leaseToken: op.leaseToken, command: claim.command,
        status: claim.command === "stop" && op.tool === "camera_observe" ? "stopped" : "failed",
        sdkUsed: false, simulated: false, data: {} });
    } catch {
      this.pending.set(key, { operationId: op.id, leaseToken: op.leaseToken, command: claim.command,
        status: "unknown", sdkUsed: false, simulated: false,
        error: { code: "CAPTURE_UNCONFIRMED", message: "本次新帧回执未确认，没有重复取样" } });
    }
  }
  async stop() {
    this.stopped = true;
    this.artifactAbort.abort();
    await this.running;
    await Promise.allSettled(this.work);
    this.pending.clear();
  }
}
