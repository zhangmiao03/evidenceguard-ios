import { test } from "node:test";
import assert from "node:assert/strict";
import {
  proxyTarget,
  acceptsOfficialMessage,
} from "../src/official-protocol.mjs";

test("official proxy matches exact origin and preserves signed paths and queries", () => {
  const origin = "https://team.example";
  assert.equal(
    proxyTarget(
      "https://openapi-us.eufylife.com/v1/smart/websdk/ws/sign?sn=T8171",
      origin,
    ),
    "/api/sdk/openapi/v1/smart/websdk/ws/sign?sn=T8171",
  );
  assert.equal(
    proxyTarget("/ai-api/chat/completions", origin),
    "/api/sdk/official-ai/chat/completions",
  );
  for (const url of [
    "https://openapi-us.eufylife.com.attacker.test/v1/token",
    "http://openapi-us.eufylife.com/v1/token",
    "https://openapi-us.eufylife.com/not-v1",
    "https://untrusted.test/ai-api/chat/completions",
  ])
    assert.equal(proxyTarget(url, origin), null);
});

test("official frame handshake rejects another window, origin and stale generation", () => {
  const frame = {},
    origin = "https://team.example",
    channel = "current-channel";
  const event = {
    source: frame,
    origin,
    data: { type: "eg:official:stopped", channel },
  };
  assert.equal(acceptsOfficialMessage(event, frame, origin, channel), true);
  assert.equal(
    acceptsOfficialMessage({ ...event, source: {} }, frame, origin, channel),
    false,
  );
  assert.equal(
    acceptsOfficialMessage(
      { ...event, origin: "https://untrusted.test" },
      frame,
      origin,
      channel,
    ),
    false,
  );
  assert.equal(
    acceptsOfficialMessage(
      { ...event, data: { ...event.data, channel: "old" } },
      frame,
      origin,
      channel,
    ),
    false,
  );
  assert.equal(
    acceptsOfficialMessage(
      { ...event, data: { type: "eg:official:ready" } },
      frame,
      origin,
      channel,
    ),
    true,
  );
});
