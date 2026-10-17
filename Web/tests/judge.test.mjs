import { test } from "node:test";
import assert from "node:assert/strict";
import {
  taskGroups,
  taskMetrics,
  replaySteps,
  taskTitle,
  readable,
  phaseRecords,
} from "../src/dashboard/judge.mjs";
const row = (id, name, extra = {}) => ({
  id,
  traceId: "agent-a",
  kind: "event",
  at: Number(id) || 1,
  status: "observed",
  name,
  data: {},
  ...extra,
});
test("judge groups only actual tasks, deduplicates rows, never turns HTTP success into Agent success", () => {
  const model = row("2", "chat", { kind: "model", status: "http_ok" });
  const rows = [
    row("1", "agent.started"),
    model,
    model,
    ...Array.from({ length: 100 }, (_, i) =>
      row("poll" + i, "http.request", { traceId: "poll" + i }),
    ),
    row("s", "runs", { kind: "resource" }),
  ];
  const groups = taskGroups(rows);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].models.length, 1);
  assert.equal(groups[0].status, "unobserved");
  assert.deepEqual(taskMetrics(groups), {
    agents: 1,
    finals: 0,
    unknown: 0,
    failed: 0,
    incomplete: 1,
    http: 1,
    codex: 0,
  });
});
test("replay preserves tool start, nested model, tool finish and runtime final order", () => {
  const rows = [
    row("7", "agent.result", {
      status: "completed",
      data: { content: { answer: "无法确认包裹被取走" } },
    }),
    row("1", "agent.started"),
    row("2", "chat", { kind: "model" }),
    row("3", "tool.started"),
    row("4", "video_verify", { kind: "model" }),
    row("5", "tool.finished"),
    row("6", "codex_step", {
      kind: "model",
      data: { transport: "codex_app_server" },
    }),
  ];
  const task = taskGroups(rows)[0];
  assert.equal(task.http, 2);
  assert.equal(task.codex, 1);
  assert.equal(task.tools.length, 1);
  assert.equal(taskMetrics([task]).unknown, 1);
  assert.deepEqual(
    replaySteps(task).map((r) => r.id),
    ["1", "2", "3", "4", "5", "6", "7"],
  );
  assert.deepEqual(
    phaseRecords(task.records, 2).map((r) => r.name),
    ["chat", "codex_step"],
  );
});
test("latest user message becomes task title, technical identifiers stay out of summary", () => {
  const r = row("1", "request.snapshot", {
    kind: "prompt",
    data: {
      request: {
        messages: [
          { role: "user", content: "旧的问题" },
          { role: "assistant", content: "旧回答" },
          {
            role: "user",
            content: "查看记录 evidence-abcdef12345678901234567890 的图片",
          },
        ],
      },
    },
  });
  assert.equal(taskTitle([r]), "查看记录 〔记录编号〕 的图片");
  assert.ok(r.data.request.messages[2].content.includes("abcdef"));
  assert.equal(readable("没有记录"), "没有记录");
});
test("standalone model attempts are inspectable but excluded from Agent completion counts", () => {
  const g = taskGroups([
    row("1", "embedding", { kind: "model", status: "http_ok" }),
  ]);
  assert.equal(g.length, 1);
  assert.equal(taskMetrics(g).agents, 0);
  assert.equal(g[0].answer, "");
});
