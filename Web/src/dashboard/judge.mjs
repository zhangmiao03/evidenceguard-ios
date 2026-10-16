// Presentation derives from recorded rows only. No generated tasks or inferred success.
export const textOf = (value) =>
  typeof value === "string"
    ? value
    : Array.isArray(value)
      ? value
          .filter((v) => v?.type === "text" || v?.type === "input_text")
          .map((v) => v.text || "")
          .join("\n")
      : "";
export const readable = (value) =>
  textOf(value)
    .replace(/(?:[a-z]+[-_:])?[a-f0-9]{20,}/gi, "〔记录编号〕")
    .replace(
      /\b(?:run|evidence|capture|sdk|video|call|thread)-[a-z0-9_-]{16,}\b/gi,
      "〔记录编号〕",
    );
export const short = (value, n = 150) => {
  const s = readable(value);
  return s.length > n ? s.slice(0, n) + "…" : s;
};
export const modelText = (row) =>
  textOf(
    row?.data?.content?.response?.choices?.[0]?.message?.content ||
      row?.data?.content?.response?.content ||
      row?.data?.content?.output?.content,
  );
export const toolTitle = (name) =>
  ({
    search_recordings: "检索录像",
    read_stored_image: "查看已保存图片",
    read_observation_image: "核验来源图片",
    capture_camera_frame: "请求手机新画面",
    list_cameras: "查询设备",
    list_tasks: "查询任务",
    list_skills: "查询 Skill",
    draft_visual_skill: "生成 Skill 草案",
    read_proactive_context: "读取观察上下文",
    search_memory: "检索记忆",
    list_skill_capabilities: "检查 Skill 能力",
  })[name] ||
  name ||
  "工具调用";
export function taskTitle(rows) {
  const search = rows.find((r) => r.name === "vector.search")?.data.query;
  if (search) return `查找录像：${short(search, 80)}`;
  for (const r of rows) {
    const messages = r.data.request?.messages || r.data.content?.messages;
    if (Array.isArray(messages)) {
      const user = [...messages].reverse().find((m) => m.role === "user");
      const t = textOf(user?.content);
      if (t) return short(t, 110);
    }
  }
  const tool = rows.find(
    (r) => r.name === "tool.finished" || r.name === "tool.started",
  );
  if (tool) return toolTitle(tool.data.tool);
  const model = rows.find((r) => r.kind === "model");
  return (
    {
      image_review: "理解一张来源图片",
      video_verify: "核验一段录像",
      embedding: "生成检索向量",
      codex_step: "AI 执行器任务",
      chat: "与助手对话",
    }[model?.name] || "Agent 任务 · 需求正文未采集"
  );
}
export function taskGroups(rows) {
  const by = new Map();
  for (const r of rows) {
    if (r.kind === "resource" || !r.traceId) continue;
    const a = by.get(r.traceId) || [];
    a.push(r);
    by.set(r.traceId, a);
  }
  return [...by]
    .filter(([, rs]) =>
      rs.some(
        (r) =>
          r.kind === "model" ||
          ["agent.started", "agent.result", "context.prepared"].includes(
            r.name,
          ),
      ),
    )
    .map(([id, rs]) => {
      const records = [...new Map(rs.map((r) => [r.id, r])).values()].sort(
        (a, b) => a.at - b.at,
      );
      const models = records.filter((r) => r.kind === "model");
      const tools = records.filter((r) => r.name === "tool.finished");
      const final = [...records]
        .reverse()
        .find((r) => r.name === "agent.result");
      const end = [...records]
        .reverse()
        .find(
          (r) => r.name === "agent.finished" || r.name === "proactive_finished",
        );
      const isAgent = records.some(
        (r) => r.name === "agent.started" || r.name === "agent.result",
      );
      const status = final?.status || end?.status || "unobserved";
      const answer = textOf(final?.data.content?.answer);
      const uncertain = Boolean(
        answer && /无法确认|没有得到明确匹配|不能确定|证据不足/.test(answer),
      );
      return {
        id,
        records,
        models,
        tools,
        final,
        answer,
        status,
        uncertain,
        isAgent,
        title: taskTitle(records),
        at: records[0].at,
        lastAt: records[records.length - 1].at,
        http: models.filter((r) => r.data.transport !== "codex_app_server")
          .length,
        codex: models.filter((r) => r.data.transport === "codex_app_server")
          .length,
      };
    })
    .sort((a, b) => b.lastAt - a.lastAt);
}
export function replaySteps(task) {
  const rs = task?.records || [];
  return rs.filter(
    (r) =>
      r.kind === "model" ||
      [
        "agent.started",
        "context.prepared",
        "tool.started",
        "tool.finished",
        "vector.search",
        "agent.result",
      ].includes(r.name) ||
      (r.name === "agent.finished" &&
        !rs.some((x) => x.name === "agent.result")),
  );
}
export function taskMetrics(tasks) {
  const agents = tasks.filter((t) => t.isAgent);
  return {
    agents: agents.length,
    finals: agents.filter((t) => Boolean(t.answer)).length,
    unknown: agents.filter((t) => t.uncertain).length,
    failed: agents.filter((t) =>
      ["failed", "cancelled", "interrupted"].includes(t.status),
    ).length,
    incomplete: agents.filter((t) => !t.answer).length,
    http: tasks.reduce((s, t) => s + t.http, 0),
    codex: tasks.reduce((s, t) => s + t.codex, 0),
  };
}
export function phaseRecords(rows, phase) {
  return rows.filter((r) =>
    phase === 0
      ? ["agent.started", "capture.frame_accepted"].includes(r.name)
      : phase === 1
        ? r.name === "context.prepared" || r.kind === "prompt"
        : phase === 2
          ? r.kind === "model" &&
            ![
              "video_verify",
              "frame_presence",
              "image_review",
              "embedding",
            ].includes(r.name)
          : phase === 3
            ? ["tool.started", "tool.finished"].includes(r.name)
            : phase === 4
              ? [
                  "vector.search",
                  "video_verify",
                  "frame_presence",
                  "image_review",
                  "embedding",
                ].includes(r.name)
              : r.name === "agent.result" || r.name === "agent.finished",
  );
}
