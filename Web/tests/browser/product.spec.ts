import { test, expect, type Page } from "@playwright/test";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

const camera = {
  id: "sdk-living",
  sn: "T8171TEST0002",
  name: "客厅摄像头",
  model: "T8171",
  connection: "unknown",
  capabilities: {},
  evidence: "测试",
};
const main = {
  id: "main-test",
  kind: "main",
  title: "助手主对话",
  preview: "",
  unreadCount: 0,
  updatedAt: 1,
};
const rules = {
  taskKind: "parcel_removal",
  durationSeconds: 0,
  trigger: "leaves_region",
  minConfidence: 0.85,
  sampleIntervalSeconds: 3,
  confirmationSeconds: 6,
  unknownPolicy: "hold_and_recheck",
  completion: "continuous",
  saveEvidence: true,
  description: "看不清时保留判断",
};
const box = { x: 0.1, y: 0.1, width: 0.5, height: 0.5 };
const draft = {
  id: "skill-test",
  name: "客厅物品守护",
  prompt: "箱子离开区域时提醒我",
  revision: 1,
  status: "draft",
  target: { description: "纸箱", cameraId: camera.id, channelId: "main", box },
  devices: [camera.id],
  regions: { [camera.id]: box },
  rules,
  result: "unknown",
  resultReason: "等待确认",
  alert: "none",
  createdAt: 10,
};
const blocked = {
  label: "真机持续执行器尚未接入",
  canActivate: false,
  canTrial: false,
  blockers: ["先完成真机采集与执行验收"],
  warnings: [],
};

async function setup(
  page: Page,
  options: {
    failPreferences?: boolean;
    lostSend?: boolean;
    conflict?: boolean;
    proactive?: boolean;
    replay?: boolean;
    sendGate?: Promise<void>;
  } = {},
) {
  const state = {
    personal: {
      revision: 0,
      preferences: {
        enabled: false,
        dailySummary: false,
        summaryHour: 18,
        quietStart: 22,
        quietEnd: 8,
        timezone: "Asia/Shanghai",
      },
      memories: [] as any[],
      inbox: [],
      messages: options.proactive
        ? ([
            {
              id: "notice-1",
              title: "客厅需要关注",
              body: "当前画面无法确认",
              why: "来自最新观察",
              createdAt: 20,
              read: false,
              sources: [
                {
                  id: "source",
                  type: "skill",
                  name: "客厅守护",
                  skillId: draft.id,
                },
              ],
            },
          ] as any[])
        : ([] as any[]),
      delivery: "in_app",
    },
    skills: [
      JSON.parse(
        JSON.stringify({
          ...draft,
          status: options.conflict ? "paused" : "draft",
          replay: options.replay ? { recordingId: "record-test" } : null,
        }),
      ),
    ],
    conversations: [{ ...main }],
    recordings: options.replay
      ? ([
          {
            id: "record-test",
            cameraId: camera.id,
            title: "门口测试录像",
            duration: 12,
            status: "ready",
            sourceType: "upload",
            playbackUrl: "/api/recordings/record-test/video",
          },
        ] as any[])
      : ([] as any[]),
    trials: [] as any[],
    runs: {} as Record<string, any[]>,
    calls: [] as {
      path: string;
      method: string;
      body: any;
      installation?: string;
    }[],
    failPreferences: options.failPreferences,
    lostSend: options.lostSend,
    conflict: options.conflict,
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname,
      method = route.request().method();
    const body = route.request().postData()
      ? route.request().headers()["content-type"]?.includes("application/json")
        ? route.request().postDataJSON()
        : { bytes: route.request().postDataBuffer()?.length }
      : undefined;
    state.calls.push({
      path,
      method,
      body,
      installation: route.request().headers()["x-eg-installation-id"],
    });
    let json: any = {},
      status = 200;
    if (path === "/api/bootstrap")
      json = {
        skills: state.skills,
        cameras: [camera],
        recordings: state.recordings,
        evidence: [],
        personal: state.personal,
        agent: { ready: true, provider: "contract-test" },
      };
    else if (path === "/api/devices") json = [camera];
    else if (path === "/api/captures") json = [];
    else if (path === "/api/personal/preferences") {
      if (state.failPreferences) {
        state.failPreferences = false;
        status = 503;
        json = { detail: "模拟服务中断" };
      } else {
        state.personal.preferences = body;
        state.personal.revision++;
        json = state.personal;
      }
    } else if (path === "/api/personal/memories") {
      state.personal.memories.unshift({
        id: "memory-1",
        content: body.content,
        createdAt: Date.now() / 1000,
        expiresAt: body.temporary ? Date.now() / 1000 + 86400 : null,
      });
      json = state.personal;
    } else if (path.startsWith("/api/personal/memories/")) {
      state.personal.memories = [];
      json = state.personal;
    } else if (path.endsWith("/feedback")) {
      state.personal.messages[0] = {
        ...state.personal.messages[0],
        feedback: body.action,
        read: true,
      };
      json = state.personal;
    } else if (path === "/api/agent/conversations/main")
      json = state.conversations[0];
    else if (path === "/api/agent/conversations" && method === "GET")
      json = state.conversations;
    else if (path === "/api/agent/conversations") {
      json = { ...main, id: "topic-test", kind: "topic", title: "新对话" };
      state.conversations.push(json);
    } else if (path.startsWith("/api/agent/conversations/")) {
      const id = path.split("/").pop()!;
      if (method === "PATCH") {
        const item = state.conversations.find((c) => c.id === id)!;
        item.title = body.title;
        json = item;
      } else json = state.runs[id] || [];
    } else if (path === "/api/agent/runs") {
      if (options.sendGate) await options.sendGate;
      if (state.lostSend) {
        state.lostSend = false;
        await route.abort("failed");
        return;
      }
      json = {
        id: body.requestId,
        conversationId: body.conversationId,
        status: "completed",
        message: body.message,
        text: "已经核对当前任务。",
        createdAt: Date.now() / 1000,
        executionMode: body.executionMode,
        captures: [],
      };
      state.runs[body.conversationId] = [
        ...(state.runs[body.conversationId] || []).filter(
          (r) => r.id !== json.id,
        ),
        json,
      ];
    } else if (path === "/api/skills/drafts") {
      json = state.skills[0];
    } else if (path === `/api/skills/${draft.id}` && method === "PATCH") {
      if (body.revision !== state.skills[0].revision) {
        status = 409;
        json = { detail: "规则已被另一客户端修改，请重新打开" };
      } else {
        state.skills[0] = {
          ...state.skills[0],
          ...body,
          revision: body.revision + 1,
        };
        json = { ...state.skills[0], capability: blocked };
      }
    } else if (path.endsWith("/capability"))
      json = options.replay
        ? {
            ...blocked,
            canTrial: true,
            canActivate: true,
            blockers: [],
            label: "可进行回放测试",
          }
        : blocked;
    else if (path.endsWith("/events")) json = [];
    else if (path.endsWith("/trials") && method === "GET") json = state.trials;
    else if (path.endsWith("/trials")) {
      json = {
        id: "trial-1",
        skillId: draft.id,
        revision: body.revision,
        status: "completed",
        summary: "已完成正例核验",
        stale: false,
        canConfirm: body.expectedOutcome === "alert",
        wouldAlert: true,
        expectedOutcome: body.expectedOutcome,
        observations: [],
        limitations: [],
      };
      state.trials = [json];
    } else if (path.endsWith("/confirm")) {
      state.skills[0].status = "active";
      json = state.skills[0];
    } else if (path === "/api/recordings" && method === "POST") {
      const query = new URL(route.request().url()).searchParams;
      json = {
        id: "record-upload",
        title: query.get("title"),
        cameraId: query.get("cameraId"),
        recordedAt: query.has("recordedAt")
          ? Number(query.get("recordedAt"))
          : null,
        status: "ready",
        duration: 6,
        playbackUrl: "/api/recordings/record-upload/video",
      };
      state.recordings.push(json);
    } else if (path.endsWith("/index")) {
      state.recordings[0].status = "indexed";
      json = state.recordings[0];
    } else if (path.endsWith("/video")) {
      status = 503;
      json = { detail: "模拟录像不可用" };
    } else if (path.endsWith("/lifecycle")) {
      if (
        state.conflict &&
        body.action === "resume" &&
        !body.switchFrom?.occupied
      ) {
        status = 409;
        json = {
          detail: "摄像头被占用",
          conflicts: [
            {
              skillId: "occupied",
              name: "原守护",
              executionEpoch: "epoch-2",
              devices: [camera.id],
            },
          ],
        };
      } else {
        state.skills[0].status = {
          pause: "paused",
          resume: "active",
          stop: "stopped",
        }[body.action as string];
        json = state.skills[0];
      }
    } else {
      status = 404;
      json = { detail: `测试未实现接口 ${method} ${path}` };
    }
    await route.fulfill({ status, json });
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await enter(page);
  return { state, errors };
}
async function enter(page: Page) {
  await page
    .getByLabel("团队访问令牌", { exact: true })
    .fill("synthetic-team-token");
  await page.getByRole("button", { name: "进入工作台 →" }).click();
  await expect(
    page.getByText("云端已连接", { exact: true }).first(),
  ).toBeVisible();
}
async function nav(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name, exact: true })
    .click();
}

test("five product sections are reachable and fit desktop and phone", async ({
  page,
}, info) => {
  const { errors } = await setup(page);
  for (const name of ["摄像头 Skill", "任务", "记忆", "设置", "助手"]) {
    await nav(page, name);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: info.outputPath("five-section-assistant.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("temporary memory persists on reload and deletion requires confirmation", async ({
  page,
}) => {
  const { state, errors } = await setup(page);
  await nav(page, "记忆");
  await page.getByRole("button", { name: "添加记忆", exact: true }).click();
  await page.getByLabel("希望助手记住什么").fill("今天只关注客厅");
  await page.getByLabel("仅保留 24 小时").check();
  await page.getByRole("button", { name: "确认记住" }).click();
  await expect(page.getByText("今天只关注客厅", { exact: true })).toBeVisible();
  expect(state.personal.memories[0].expiresAt).toBeGreaterThan(
    Date.now() / 1000,
  );
  const installation = state.calls[0].installation;
  await page.reload();
  await enter(page);
  await nav(page, "记忆");
  await expect(page.getByText("今天只关注客厅", { exact: true })).toBeVisible();
  expect(state.calls.at(-1)?.installation).toBe(installation);
  await page.getByRole("button", { name: "移除记忆：今天只关注客厅" }).click();
  expect(state.calls.some((c) => c.method === "DELETE")).toBe(false);
  await page.getByRole("button", { name: "确认移除" }).click();
  await expect(
    page.getByText("这里还没有记忆。", { exact: false }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("reminder edits survive refresh, navigation, failure and explicit retry", async ({
  page,
}) => {
  const { state } = await setup(page, { failPreferences: true });
  await nav(page, "设置");
  await page.getByLabel("应用内主动提醒", { exact: true }).check();
  await page.getByLabel("每日守护概况", { exact: true }).check();
  await page.getByLabel("每日概况时间").selectOption("21");
  await nav(page, "任务");
  await page.getByRole("button", { name: "定时", exact: true }).click();
  await page.getByRole("button", { name: "设置时间与免打扰" }).click();
  await expect(page.getByLabel("每日概况时间")).toHaveValue("21");
  await page.getByRole("button", { name: "保存提醒设置" }).click();
  await expect(page.getByRole("alert")).toContainText("修改已保留");
  await expect(page.getByLabel("每日概况时间")).toHaveValue("21");
  await page.getByRole("button", { name: "保存提醒设置" }).click();
  await expect(page.getByRole("status")).toContainText("提醒设置已保存");
  expect(state.personal.preferences).toMatchObject({
    enabled: true,
    dailySummary: true,
    summaryHour: 21,
  });
  await nav(page, "任务");
  await expect(page.getByRole("heading", { name: "每天 21:00" })).toBeVisible();
});

test("assistant sends without a device and reuses the failed request identity", async ({
  page,
}) => {
  const { state } = await setup(page, { lostSend: true });
  await page
    .getByRole("textbox", { name: "消息输入框" })
    .fill("我关心的任务现在怎么样？");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.getByRole("alert")).toContainText("输入已保留");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(
    page.getByText("已经核对当前任务。", { exact: true }),
  ).toBeVisible();
  const sends = state.calls.filter((c) => c.path === "/api/agent/runs");
  expect(sends).toHaveLength(2);
  expect(sends[0].body.requestId).toBe(sends[1].body.requestId);
  expect(sends[1].body.cameraId).toBeUndefined();
  await page.reload();
  await enter(page);
  await expect(
    page.getByText("已经核对当前任务。", { exact: true }),
  ).toBeVisible();
});

test("late topic replies stay in their own conversation after starting a task", async ({
  page,
}) => {
  let release!: () => void;
  const sendGate = new Promise<void>((resolve) => (release = resolve));
  const { state } = await setup(page, { sendGate });
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByLabel("选择对话")).toHaveValue("topic-test");
  await page
    .getByRole("textbox", { name: "消息输入框" })
    .fill("只属于独立话题的问题");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect
    .poll(() => state.calls.filter((c) => c.path === "/api/agent/runs").length)
    .toBe(1);
  await nav(page, "任务");
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await expect(page.getByLabel("选择对话")).toHaveValue(main.id);
  const taskPrompt =
    "我想创建一项摄像头 Skill，请先帮我确认观察对象和提醒条件。";
  await expect(page.getByRole("textbox", { name: "消息输入框" })).toHaveValue(
    taskPrompt,
  );
  release();
  await expect(page.getByRole("button", { name: "发送问题" })).toBeEnabled();
  await expect(
    page.getByText("只属于独立话题的问题", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "消息输入框" })).toHaveValue(
    taskPrompt,
  );
  await page.getByLabel("选择对话").selectOption("topic-test");
  await expect(
    page.getByText("只属于独立话题的问题", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("已经核对当前任务。", { exact: true }),
  ).toBeVisible();
});

test("history queries use a separate read-only stream and validate the time range", async ({
  page,
}) => {
  const { state } = await setup(page);
  await page.getByLabel("对话范围", { exact: true }).selectOption("history");
  await page.getByLabel("查询日期").selectOption("custom");
  await page.getByRole("textbox", { name: "消息输入框" }).fill("查找包裹离区片段");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.getByRole("alert")).toContainText("起止时间");
  expect(state.calls.some((c) => c.path === "/api/agent/runs")).toBe(false);
  await page.getByLabel("查询日期").selectOption("today");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(
    page.getByText("已经核对当前任务。", { exact: true }),
  ).toBeVisible();
  const sent = state.calls.find((c) => c.path === "/api/agent/runs")!.body;
  expect(sent).toMatchObject({
    conversationId: "main-test-history",
    executionMode: "history",
    historyFilter: { period: "today" },
  });
  await page.getByLabel("对话范围", { exact: true }).selectOption("live");
  await expect(
    page.getByText("已经核对当前任务。", { exact: true }),
  ).toHaveCount(0);
});

test("topics rename and browser drafts restore while main inbox stays fixed", async ({
  page,
}) => {
  const { state } = await setup(page);
  await expect(page.getByLabel("选择对话")).toHaveValue(main.id);
  await page.getByRole("textbox", { name: "消息输入框" }).fill("主对话未发送内容");
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByLabel("选择对话")).toHaveValue("topic-test");
  await expect(page.getByRole("textbox", { name: "消息输入框" })).toHaveValue("");
  await page.getByRole("button", { name: "重命名" }).click();
  await page.getByLabel("对话名称").fill("客厅观察讨论");
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(page.getByRole("dialog", { name: "重命名对话" })).toHaveCount(0);
  await page.getByRole("textbox", { name: "消息输入框" }).fill("独立话题草稿");
  await page.reload();
  await enter(page);
  await expect(page.getByLabel("选择对话")).toHaveValue("topic-test");
  await expect(page.getByRole("textbox", { name: "消息输入框" })).toHaveValue(
    "独立话题草稿",
  );
  await page.getByLabel("选择对话").selectOption(main.id);
  await expect(page.getByRole("textbox", { name: "消息输入框" })).toHaveValue(
    "主对话未发送内容",
  );
  expect(state.conversations[0].kind).toBe("main");
  await page.getByRole("button", { name: "退出", exact: true }).click();
  expect(
    await page.evaluate(
      () =>
        Object.keys(localStorage).filter((k) =>
          k.startsWith("evidenceguard.chat."),
        ).length,
    ),
  ).toBe(0);
});

test("proactive reminders expose sources, feedback and a grounded reply", async ({
  page,
}) => {
  const { state } = await setup(page, { proactive: true });
  await expect(page.getByText("客厅需要关注", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "已处理", exact: true }).click();
  await expect(page.getByText("已反馈：已处理", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "继续追问" }).click();
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect
    .poll(
      () =>
        state.calls.find((c) => c.path === "/api/agent/runs")?.body
          .replyToMessageId,
    )
    .toBe("notice-1");
});

test("Skill editor saves normalized regions and respects the server activation gate", async ({
  page,
}, info) => {
  const { state, errors } = await setup(page);
  await nav(page, "摄像头 Skill");
  await page.getByRole("button", { name: /客厅摄像头.*T8171/ }).click();
  await page.getByRole("button", { name: "圈选守护 · 创建 Skill" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "设置守护" })).toBeVisible();
  await dialog.getByLabel("守护名称", { exact: true }).fill("客厅新守护");
  await dialog.getByLabel("左侧（比例）").fill("0.2");
  await dialog.getByRole("button", { name: "下一步：提醒条件" }).click();
  await dialog.getByLabel("检测间隔（秒）").fill("5");
  await dialog.getByLabel("确认跨度（秒）").fill("10");
  await dialog.getByRole("button", { name: "保存草案，检查并确认" }).click();
  await expect(
    dialog.getByText("先完成真机采集与执行验收", { exact: true }),
  ).toBeVisible();
  await dialog.getByLabel("我确认仅使用合成测试标记验证规则").check();
  await expect(
    dialog.getByRole("button", { name: "确认并开始标记测试" }),
  ).toBeDisabled();
  const saved = state.calls.find(
    (c) => c.method === "PATCH" && c.path === `/api/skills/${draft.id}`,
  )!.body;
  expect(saved.regions[camera.id].x).toBe(0.2);
  expect(saved.rules).toMatchObject({
    sampleIntervalSeconds: 5,
    confirmationSeconds: 10,
    unknownPolicy: "hold_and_recheck",
  });
  expect(state.calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
  await page.screenshot({ path: info.outputPath("skill-capability.png") });
  expect(errors).toEqual([]);
});

test("task camera conflicts require explicit approval and preserve execution epochs", async ({
  page,
}) => {
  const { state } = await setup(page, { conflict: true });
  await nav(page, "任务");
  await page.getByRole("button", { name: /客厅物品守护/ }).click();
  await page.getByRole("button", { name: "恢复守护" }).click();
  await expect(
    page.getByRole("heading", { name: "摄像头正在执行其他任务" }),
  ).toBeVisible();
  expect(state.skills[0].status).toBe("paused");
  await page.getByRole("button", { name: "保留原任务" }).click();
  expect(state.calls.filter((c) => c.path.endsWith("/lifecycle"))).toHaveLength(
    1,
  );
  await page.getByRole("button", { name: "恢复守护" }).click();
  await page.getByRole("button", { name: "暂停占用任务并继续" }).click();
  await expect(page.getByRole("button", { name: "暂停守护" })).toBeVisible();
  expect(
    state.calls.filter((c) => c.path.endsWith("/lifecycle")).at(-1)!.body
      .switchFrom,
  ).toEqual({ occupied: "epoch-2" });
  await page.getByRole("button", { name: "停止任务", exact: true }).click();
  expect(state.skills[0].status).toBe("active");
  await page.getByRole("button", { name: "确认停止", exact: true }).click();
  await expect.poll(() => state.skills[0].status).toBe("stopped");
});

test("stale Skill revisions keep edits and never silently activate", async ({
  page,
}) => {
  const { state } = await setup(page);
  await nav(page, "任务");
  await page.getByRole("button", { name: /客厅物品守护/ }).click();
  await page.getByLabel("守护名称", { exact: true }).fill("我的修改");
  state.skills[0].revision = 9;
  await page.getByRole("button", { name: "保存草案", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("另一客户端修改");
  await expect(page.getByLabel("守护名称", { exact: true })).toHaveValue(
    "我的修改",
  );
  expect(state.calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
});

test("replay activation requires a current trial, human review and source acknowledgement", async ({
  page,
}) => {
  const { state } = await setup(page, { replay: true });
  await nav(page, "任务");
  await page.getByRole("button", { name: /客厅物品守护/ }).click();
  await page.getByRole("button", { name: "下一步：提醒条件" }).click();
  await page.getByRole("button", { name: "保存草案，检查并确认" }).click();
  const confirm = page.getByRole("button", { name: "确认并开始回放" });
  await expect(confirm).toBeDisabled();
  await page
    .getByRole("combobox", { name: "人工预期", exact: true })
    .selectOption("alert");
  await page.getByRole("button", { name: "开始试跑", exact: true }).click();
  await expect(page.getByText("已完成正例核验")).toBeVisible();
  await expect(confirm).toBeDisabled();
  await page.getByLabel("我已核验本版本的试跑报告").check();
  await expect(confirm).toBeDisabled();
  await page.getByLabel("我确认使用录像回放测试此规则").check();
  await confirm.click();
  await expect(page.getByRole("button", { name: "暂停守护" })).toBeVisible();
  expect(
    state.calls.find((c) => c.path.endsWith("/confirm"))!.body,
  ).toMatchObject({
    trialId: "trial-1",
    trialReviewed: true,
    replayAcknowledged: true,
    fixtureAcknowledged: false,
  });
});

test("recording import keeps unknown capture dates and playback failures are visible", async ({
  page,
}) => {
  const { state } = await setup(page);
  // WebKit does not expose File request bodies through route.postData().
  // Bypass network interception for this POST and receive native browser bytes.
  let receivedBytes = 0;
  const receiver = createServer((request, response) => {
    if (request.method === "OPTIONS") {
      response.writeHead(204, {
        "Access-Control-Allow-Origin": "http://127.0.0.1:5178",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers":
          "Content-Type, Authorization, X-EG-Installation-ID",
      });
      response.end();
      return;
    }
    request.on("data", (chunk: Buffer) => {
      receivedBytes += chunk.length;
    });
    request.on("end", () => {
      const query = new URL(request.url!, "http://localhost").searchParams;
      const record = {
        id: "record-upload",
        title: query.get("title"),
        cameraId: query.get("cameraId"),
        recordedAt: query.has("recordedAt")
          ? Number(query.get("recordedAt"))
          : null,
        status: "ready",
        duration: 6,
        playbackUrl: "/api/recordings/record-upload/video",
      };
      state.recordings.push(record);
      response.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "http://127.0.0.1:5178",
        "Access-Control-Allow-Credentials": "true",
      });
      response.end(JSON.stringify(record));
    });
  });
  await new Promise<void>((resolve) =>
    receiver.listen(0, "127.0.0.1", resolve),
  );
  const port = (receiver.address() as AddressInfo).port;
  await page.evaluate((port) => {
    const original = window.fetch;
    window.fetch = (input, init) => {
      if (
        typeof input === "string" &&
        input.startsWith("/api/recordings?") &&
        init?.method === "POST"
      ) {
        return original(
          `http://127.0.0.1:${port}/upload?${input.split("?")[1]}`,
          init,
        );
      }
      return original(input, init);
    };
  }, port);
  try {
    await nav(page, "摄像头 Skill");
    await page.getByRole("button", { name: "录像资料", exact: true }).click();
    await page.getByLabel("选择录像（上限 150 MB）").setInputFiles({
      name: "indoor-test.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("synthetic-upload-only"),
    });
    await page.getByRole("button", { name: "上传录像", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "indoor-test" }),
    ).toBeVisible();
    expect(state.recordings[0].recordedAt).toBeNull();
    expect(receivedBytes).toBe(Buffer.byteLength("synthetic-upload-only"));
    await page.getByRole("button", { name: "建立检索索引" }).click();
    await expect.poll(() => state.recordings[0].status).toBe("indexed");
    await page.getByRole("button", { name: "播放录像" }).click();
    await expect(page.getByRole("alert")).toContainText("证据读取失败");
  } finally {
    await new Promise<void>((resolve, reject) =>
      receiver.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
