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
    image: "data:image/png;base64,NOTREAL",
  };
  const clean = sanitizeBundle(validateBundle(bundle));
  assert.ok(!JSON.stringify(clean).includes("should-disappear"));
  assert.ok(!JSON.stringify(clean).includes("NOTREAL"));
});
