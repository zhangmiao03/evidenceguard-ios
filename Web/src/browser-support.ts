export function newID(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (n) => n.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function requireSecureConnection(): void {
  if (
    location.protocol !== "https:" &&
    !["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)
  )
    throw new Error(
      "请通过 HTTPS 访问团队服务；普通局域网 HTTP 不能安全发送账号凭证。电脑本机可使用 localhost。",
    );
}

// Safari/private browsing and managed browsers may deny storage. Keep the
// installation stable for this page even when persistence is unavailable.
export function installationID(): string {
  const key = "evidenceguard.web.installation";
  try {
    const saved = localStorage.getItem(key);
    if (saved && /^[a-f0-9-]{36}$/i.test(saved)) return saved;
  } catch {
    /* session-only identity */
  }
  const id = newID();
  try {
    localStorage.setItem(key, id);
  } catch {
    /* session-only identity */
  }
  return id;
}
