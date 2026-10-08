import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizedBox } from "../src/geometry.mjs";
test("reverse drag and out-of-image pointers produce a bounded camera ROI", () => {
  assert.deepEqual(normalizedBox({ x: 1.2, y: 0.8 }, { x: -0.1, y: 0.2 }), {
    x: 0,
    y: 0.2,
    width: 1,
    height: 0.6000000000000001,
  });
});
test("a tap cannot replace the target with an empty ROI", () => {
  assert.equal(normalizedBox({ x: 0.2, y: 0.3 }, { x: 0.2, y: 0.3 }), null);
});
