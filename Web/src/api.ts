export class APIError extends Error {
  constructor(
    message: string,
    public conflicts: {
      skillId: string;
      name: string;
      executionEpoch: string;
    }[] = [],
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new APIError(
      typeof value.detail === "string"
        ? value.detail
        : "请求未完成，请检查输入和服务连接。",
      value.conflicts,
    );
  return value as T;
}
export const running = (status: string) =>
  ["queued", "running"].includes(status);
export const statusLabel = (status: string) =>
  ({
    draft: "待确认",
    active: "运行中",
    paused: "已暂停",
    stopped: "已停止",
    completed: "已完成",
    queued: "排队中",
    running: "处理中",
    ready: "可检索",
    failed: "未完成",
    indexing: "建立索引中",
    cancelled: "已取消",
    interrupted: "已中断",
  })[status] || status;
