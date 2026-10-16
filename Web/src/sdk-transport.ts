/** Forward buffered bodies so localhost HTTP/1.1 does not become a streaming upload. */
export async function relaySDKRequest(
  fetcher: typeof fetch,
  request: Request,
  target: string,
  headers: Headers,
  signal = request.signal,
) {
  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();
  return fetcher(target, {
    method: request.method,
    headers,
    body,
    signal,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  });
}

let guarded = false;
/** The shipped UMD logs ECDH keys and signed URLs without a logger setting.
 * Suppress calls originating in that artifact; keep our own diagnostics intact.
 * Keep this guard after disconnect because vendor teardown can log asynchronously.
 */
export function guardSDKLogs() {
  if (guarded) return;
  guarded = true;
  for (const method of ["log", "info", "debug", "warn", "error"] as const) {
    const original = console[method].bind(console);
    console[method] = (...args: unknown[]) => {
      const stack = new Error().stack;
      if (!stack || /\/sdk\/index\.js(?:[:?]|$)/m.test(stack)) return;
      original(...args);
    };
  }
}

export function safeSDKError(message: string) {
  return message
    .replace(/(?:https?|wss?):\/\/\S+/gi, "[设备连接地址已隐藏]")
    .replace(/[A-Za-z0-9_+/=-]{48,}/g, "[授权数据已隐藏]")
    .slice(0, 240);
}
