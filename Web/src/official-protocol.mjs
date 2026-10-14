export function proxyTarget(input, origin) {
  const url = new URL(input, origin);
  if (
    url.origin === "https://openapi-us.eufylife.com" &&
    url.pathname.startsWith("/v1/")
  )
    return `/api/sdk/openapi${url.pathname}${url.search}`;
  if (url.origin === origin && url.pathname === "/ai-api/chat/completions")
    return "/api/sdk/official-ai/chat/completions";
  return null;
}

export function acceptsOfficialMessage(event, frameWindow, origin, channel) {
  return (
    event.source === frameWindow &&
    event.origin === origin &&
    (event.data?.type === "eg:official:ready" ||
      event.data?.channel === channel)
  );
}
