import { test } from "node:test";
import assert from "node:assert/strict";
import { FrameGate } from "../src/frame-gate.mjs";
const f = (n) => ({
  blob: new Blob(["jpeg"]),
  width: 12,
  height: 8,
  timestamp: n,
});
test("cached, duplicate, stopped and expired frames cannot answer a new challenge", () => {
  const gate = new FrameGate();
  gate.accept(f(1), 1000);
  const command = { deadline: 10, afterSequence: 0 };
  assert.equal(gate.after(command, 1, 1000), null);
  assert.equal(gate.accept(f(1), 1200), false);
  gate.accept(f(2), 1500);
  assert.equal(gate.after(command, 1, 1600).sequence, 2);
  assert.equal(gate.after(command, 1, 5000), null);
  assert.equal(gate.after({ ...command, deadline: 1 }, 1, 1600), null);
});
