import test from "node:test";
import assert from "node:assert/strict";
import {
  validateBundle,
  sanitizeBundle,
  sampleBundle,
  emptyBundle,
  selectRecords,
  metrics,
  exportBundle,
} from "../src/dashboard/data.mjs";

test("offline samples are explicit and empty data does not invent usage", () => {
  assert.equal(sampleBundle().dataset.source, "synthetic");
  assert.equal(validateBundle(emptyBundle()).records.length, 0);
  assert.equal(metrics([]).tokens, null);
  assert.equal(metrics([]).httpSuccess, null);
  assert.equal(metrics([]).p95, null);
});
test("invalid versions, duplicate IDs, nonfinite durations and spoofed platforms are rejected", () => {
  const bundle = sampleBundle();
  assert.throws(() => validateBundle({ ...bundle, schemaVersion: "v2" }));
  assert.throws(() =>
    validateBundle({
      ...bundle,
      records: [...bundle.records, bundle.records[0]],
    }),
  );
  for (const change of [
    { durationMs: NaN },
    { durationMs: -1 },
    { platform: "admin" },
    { at: Infinity },
    { data: null },
  ]) {
    assert.throws(() =>
      validateBundle({
        ...bundle,
        records: [{ ...bundle.records[0], ...change }],
      }),
    );
  }
});
test("filters use snapshot time, model totals include actual attempts only", () => {
  const bundle = sampleBundle();
  const rows = selectRecords(bundle, { hours: "1", platform: "backend" });
  assert.ok(
    rows.every(
      (r) =>
        r.at >= bundle.dataset.exportedAt - 3600 && r.platform === "backend",
    ),
  );
  const all = metrics(bundle.records);
  assert.equal(all.calls, 12);
  assert.equal(all.usageCalls, 9);
  assert.equal(all.httpSuccess, 11 / 12);
  assert.equal(all.tokens, 9720);
});
test("filtered exports retain related prompts and round trip with immutable IDs", () => {
  const bundle = sampleBundle();
  const rows = selectRecords(bundle, { query: "http_error" });
  const exported = exportBundle(bundle, rows, { query: "http_error" });
  validateBundle(JSON.parse(JSON.stringify(exported)));
  assert.equal(exported.coverage.relatedPrompts, 1);
  assert.equal(exported.records.length, 2);
  assert.notEqual(exported.dataset.id, bundle.dataset.id);
  assert.notEqual(
    exported.dataset.id,
    exportBundle(bundle, rows, {}).dataset.id,
  );
});

test("imported snapshots remove credential fields and embedded image payloads", () => {
  const bundle = sampleBundle();
  bundle.records[0].data = {
    Authorization: "should-disappear",
    deviceSn: "T8214PRIVATE001",
    mediaSessionToken: "private-session-value",
    usage: { total_tokens: 16 },
    image: "data:image/png;base64,NOTREAL",
  };
  const clean = sanitizeBundle(validateBundle(bundle));
  assert.ok(!JSON.stringify(clean).includes("should-disappear"));
  assert.ok(!JSON.stringify(clean).includes("NOTREAL"));
  assert.ok(!JSON.stringify(clean).includes("T8214PRIVATE001"));
  assert.ok(!JSON.stringify(clean).includes("private-session-value"));
  assert.equal(clean.records[0].data.usage.total_tokens, 16);
});

test("full content survives export and import with nested credentials removed", () => {
  const bundle = sampleBundle();
  const answer = "完整正文".repeat(8000) + "END-OF-ANSWER";
  bundle.records[0].data = {
    capture: { version: 1, mode: "full_redacted", truncated: false },
    content: { answer, arguments: '{"Cookie":"nested-private","query":"ordinary"}', result: [],
      reasoning_content: "private-model-reasoning" },
    usage: { total_tokens: 9, completion_tokens_details: { reasoning_tokens: 2 } },
  };
  const clean = sanitizeBundle(validateBundle(bundle));
  assert.equal(clean.records[0].data.content.answer, answer);
  assert.deepEqual(clean.records[0].data.content.result, []);
  assert.equal(clean.records[0].data.usage.completion_tokens_details.reasoning_tokens, 2);
  assert.ok(!JSON.stringify(clean).includes("nested-private"));
  assert.ok(!JSON.stringify(clean).includes("private-model-reasoning"));
  const exported = exportBundle(clean, clean.records, {});
  const again = sanitizeBundle(validateBundle(JSON.parse(JSON.stringify(exported))));
  assert.equal(again.records[0].data.content.answer, answer);
  assert.equal(again.records[0].data.capture.truncated, false);
});

test("over-limit full content is explicitly marked as truncated", () => {
  const bundle = sampleBundle();
  bundle.records[0].data = { capture: { version: 1, mode: "full_redacted" }, content: { answer: "x".repeat(260000) } };
  const clean = sanitizeBundle(validateBundle(bundle));
  assert.equal(clean.records[0].data.capture.mode, "truncated");
  assert.equal(clean.records[0].data.capture.truncated, true);
  assert.ok(clean.records[0].data.content.answer.endsWith("[truncated: capture limit]"));
});

test("Codex boundaries and repeated usage snapshots do not inflate HTTP or token metrics", () => {
  const bundle = sampleBundle();
  const original = metrics(bundle.records);
  const base = bundle.records[0];
  bundle.records.push({ ...base, id: "codex-1", kind: "model", status: "executor_ok", durationMs: 500000,
    data: { transport: "codex_app_server", usage: { total_tokens: 9999 } } });
  bundle.records.push({ ...base, id: "codex-usage", kind: "event", name: "codex.usage",
    data: { transport: "codex_app_server", content: { tokenUsage: { totalTokens: 9999 } } } });
  const current = metrics(bundle.records);
  assert.equal(current.codexSteps, 1);
  for (const key of ["calls", "usageCalls", "tokens", "httpSuccess", "p95"]) assert.equal(current[key], original[key]);
});
