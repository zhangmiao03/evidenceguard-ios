import {
  installationID,
  requireSecureConnection,
  newID,
} from "./browser-support";
const installation = installationID();

export type Observation = {
  name: string;
  traceId: string;
  parentSpanId?: string | null;
  durationMs?: number;
  deviceId?: string;
  requestId?: string;
  route?: string;
  status?: string;
};
let pending = 0;
/** Bounded best effort. No recursive API calls, retries, bodies, images or secrets. */
export function observe(event: Observation, token = "") {
  if (pending >= 8) return;
  try {
    if (token) requireSecureConnection();
  } catch {
    return;
  }
  pending++;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2500);
  void fetch("/api/ops/client-events", {
    method: "POST",
    signal: controller.signal,
    headers: {
      "Content-Type": "application/json",
      "X-EG-Installation-ID": installation,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify([
      {
        ...event,
        id: newID(),
        spanId: newID(),
        platform: "web",
        appVersion: "web-0.2/ops-v1",
        status: event.status || "observed",
      },
    ]),
  })
    .catch(() => {})
    .finally(() => {
      clearTimeout(timeout);
      pending--;
    });
}
export function routeTemplate(path: string) {
  return path
    .split("?")[0]
    .replace(
      /\/(?:[a-f0-9-]{20,}|live-[a-z0-9]+|sdk-[a-z0-9]+)(?=\/|$)/gi,
      "/:id",
    );
}
