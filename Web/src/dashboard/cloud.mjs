/** Same-origin, anonymous telemetry only. Never forward App credentials.
 * @param {string} path
 * @param {{signal?: AbortSignal, timeout?: number, fetcher?: typeof fetch}} options
 */
export async function cloudJSON(path, { signal, timeout = 12000, fetcher = fetch } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, timeout);
  try {
    const response = await fetcher(path, { signal: controller.signal, credentials: "omit", cache: "no-store", headers: { Accept: "application/json" } });
    if ([401, 403].includes(response.status)) throw Error(`此网址的 Dashboard 数据接口返回 ${response.status}。页面入口与数据服务未正确连接；无需填写 App 密钥，请重试或使用作品主入口。`);
    if (!response.ok) throw Error(`云端采集接口返回 ${response.status}，正在等待恢复。`);
    if (!(response.headers.get("content-type") || "").includes("application/json")) throw Error("数据接口返回了网页而不是数据，请检查 Dashboard 部署入口。");
    return await response.json();
  } catch (error) {
    if (controller.signal.aborted && !signal?.aborted) throw Error("云端读取超时，将自动重试；当前空白不代表服务器没有数据。");
    throw error;
  } finally {
    clearTimeout(timer); signal?.removeEventListener("abort", abort);
  }
}
