import { useEffect, useRef, useState } from "react";
import { api, APIError } from "./api";
import {
  ErrorNotice,
  EvidenceGallery,
  ImageEvidence,
  Modal,
  VideoPlayer,
} from "./ProductUI";
import {
  defaultRules,
  initialROI,
  running,
  statusLabel,
  timeLabel,
  type Bootstrap,
  type Capability,
  type Conflict,
  type Contract,
  type Deployment,
  type Evidence,
  type Recording,
  type ROI,
  type Skill,
  type Trial,
} from "./product-types";

export function TasksPage({
  data,
  evidence,
  selectedSkill,
  onSkill,
  onRefresh,
  onAssistant,
  onSettings,
}: {
  data: Bootstrap;
  evidence: Evidence[];
  selectedSkill: string;
  onSkill: (id: string) => void;
  onRefresh: () => Promise<void>;
  onAssistant: (prompt: string, id?: string) => void;
  onSettings: () => void;
}) {
  const [section, setSection] = useState("tasks"),
    [filter, setFilter] = useState("all");
  const skill = data.skills.find((s) => s.id === selectedSkill);
  const items = data.skills.filter(
    (s) =>
      filter === "all" ||
      (filter === "attention"
        ? (s.alert === "open" && s.status !== "stopped") ||
          (s.status === "active" && s.result !== "confirmed")
        : s.status === filter),
  );
  const prefs = data.personal?.preferences;
  return (
    <div className="page-stack">
      <div className="section-heading">
        <div className="segmented" aria-label="任务分类">
          {[
            ["tasks", "任务"],
            ["scheduled", "定时"],
            ["evidence", "证据库"],
          ].map(([id, label]) => (
            <button
              key={id}
              aria-pressed={section === id}
              onClick={() => setSection(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="primary"
          onClick={() =>
            onAssistant(
              "我想创建一项摄像头 Skill，请先帮我确认观察对象和提醒条件。",
            )
          }
        >
          新建任务
        </button>
      </div>
      {section === "tasks" && (
        <>
          <div className="filter-row">
            {[
              ["all", "全部"],
              ["active", "运行中"],
              ["draft", "待确认"],
              ["paused", "已暂停"],
              ["attention", "需要关注"],
              ["stopped", "已停止"],
              ["completed", "已完成"],
            ].map(([id, label]) => (
              <button
                className={filter === id ? "filter active" : "filter"}
                aria-pressed={filter === id}
                onClick={() => setFilter(id)}
                key={id}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="task-grid">
            {items
              .sort((a, b) => b.createdAt - a.createdAt)
              .map((s) => (
                <button
                  className="card task-tile"
                  key={s.id}
                  onClick={() => onSkill(s.id)}
                >
                  <div className="section-heading">
                    <span className="task-symbol">
                      {s.status === "active" ? "◉" : "◇"}
                    </span>
                    <span className="pill blue">{statusLabel(s.status)}</span>
                  </div>
                  <h2>{s.name}</h2>
                  <p>{s.status === "draft" ? s.prompt : s.resultReason}</p>
                  <small>
                    {s.replay
                      ? "录像回放测试"
                      : s.devices
                          .map(
                            (id) =>
                              data.cameras.find((c) => c.id === id)?.name || id,
                          )
                          .join("、")}
                  </small>
                  <div className="task-result">
                    {statusLabel(s.result)} <span>查看详情 →</span>
                  </div>
                </button>
              ))}
          </div>
          {!items.length && (
            <div className="empty-inline">
              暂无这类任务。告诉助手你的需求，一起确认对象、区域和提醒条件。
            </div>
          )}
        </>
      )}
      {section === "scheduled" && (
        <section className="card product-card">
          <span className="pill blue">每日守护概况</span>
          <h2>
            {prefs?.dailySummary
              ? `每天 ${String(prefs.summaryHour).padStart(2, "0")}:00`
              : "尚未开启每日概况"}
          </h2>
          <p>
            {prefs?.dailySummary && !prefs.enabled
              ? "主动提醒总开关已关闭，概况已暂停。"
              : "汇总已保存的观察与待处理事项，发到助手主对话。"}
          </p>
          <small>时区：{prefs?.timezone || "未读取"} · 应用内提醒</small>
          <p>
            当前支持每日概况。摄像头任务按规则持续或单次执行，暂不支持预约启停。
          </p>
          <button className="primary" onClick={onSettings}>
            设置时间与免打扰
          </button>
        </section>
      )}
      {section === "evidence" && (
        <EvidenceGallery items={evidence} onSkill={onSkill} />
      )}
      {skill && (
        <SkillDetail
          key={skill.id}
          skill={skill}
          data={data}
          evidence={evidence}
          onClose={() => onSkill("")}
          onRefresh={onRefresh}
          onAssistant={onAssistant}
        />
      )}
    </div>
  );
}

function SkillDetail({
  skill,
  data,
  evidence,
  onClose,
  onRefresh,
  onAssistant,
}: {
  skill: Skill;
  data: Bootstrap;
  evidence: Evidence[];
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onAssistant: (prompt: string, id?: string) => void;
}) {
  const [editing, setEditing] = useState(skill.status === "draft"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [stopping, setStopping] = useState(false),
    [events, setEvents] = useState<
      { type: string; sequence: number; at?: number }[]
    >([]);
  const [trials, setTrials] = useState<Trial[]>([]),
    [conflicts, setConflicts] = useState<Conflict[]>([]),
    [plan, setPlan] = useState<Deployment | null>(null);
  const [trial, setTrial] = useState<Trial | null>(null),
    [showEvidence, setShowEvidence] = useState(false);
  const mounted = useRef(true),
    client = useRef(api.scoped());
  useEffect(() => {
    mounted.current = true;
    let loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const [e, t] = await Promise.all([
          client.current.request<typeof events>(
            `/api/skills/${skill.id}/events`,
          ),
          client.current.request<Trial[]>(`/api/skills/${skill.id}/trials`),
        ]);
        if (mounted.current) {
          setEvents(e);
          setTrials(t);
        }
      } catch (e) {
        if (mounted.current)
          setError(e instanceof Error ? e.message : "运行记录暂未同步");
      } finally {
        loading = false;
      }
    };
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [skill.id]);
  const perform = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      if (mounted.current) {
        setStopping(false);
        setConflicts([]);
        await onRefresh();
      }
    } catch (e) {
      if (mounted.current) {
        if (e instanceof APIError && e.conflicts.length)
          setConflicts(e.conflicts);
        else setError(e instanceof Error ? e.message : "操作未完成");
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const lifecycle = (action: string, switchFrom: Record<string, string> = {}) =>
    perform(() =>
      client.current.request(`/api/skills/${skill.id}/lifecycle`, {
        action,
        switchFrom,
      }),
    );
  if (editing)
    return (
      <SkillEditor
        initial={skill}
        data={data}
        onClose={() => setEditing(false)}
        onRefresh={onRefresh}
      />
    );
  return (
    <Modal title={skill.name} busy={busy} onClose={onClose}>
      <div className="page-stack">
        <span className="pill blue">
          {statusLabel(skill.status)} · {statusLabel(skill.result)}
        </span>
        <p>{skill.resultReason}</p>
        <small>
          最近观察：{timeLabel(skill.lastObservedAt)} · 规则版本{" "}
          {skill.revision}
        </small>
        <ErrorNotice error={error} />
        {skill.status === "draft" && (
          <button className="primary" onClick={() => setEditing(true)}>
            继续设置守护
          </button>
        )}
        <details>
          <summary>守护规则与采样说明</summary>
          <p>{skill.prompt}</p>
          <p>{skill.rules?.description}</p>
          <p>
            每 {skill.rules?.sampleIntervalSeconds || 3} 秒检测，确认跨度{" "}
            {skill.rules?.confirmationSeconds || 6} 秒；看不清时保留判断。
          </p>
        </details>
        {skill.replay && (
          <section className="context-strip">
            <div>
              <strong>录像回放测试</strong>
              <p>
                已到达 {skill.replayState?.cursor || 0} 秒，模型观察{" "}
                {skill.replayState?.modelCalls || 0} 次。
                {skill.replayState?.online === false ? "回放输入已断开。" : ""}
              </p>
              <small>不是实时摄像头守护，请核验提醒片段。</small>
              {skill.status === "active" && (
                <button
                  disabled={busy}
                  className="text-button"
                  onClick={() =>
                    void perform(() =>
                      client.current.request(
                        `/api/skills/${skill.id}/replay-transport`,
                        { online: skill.replayState?.online === false },
                      ),
                    )
                  }
                >
                  {skill.replayState?.online === false
                    ? "恢复回放输入"
                    : "模拟输入断流"}
                </button>
              )}
            </div>
          </section>
        )}
        <div className="button-row">
          <button
            className="secondary"
            onClick={() => setShowEvidence(!showEvidence)}
          >
            查看此任务证据
          </button>
          <button
            className="secondary"
            onClick={() => {
              onClose();
              onAssistant("", skill.id);
            }}
          >
            与 AI 继续沟通
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const p = await client.current.request<Deployment>(
                  `/api/skills/${skill.id}/deployment`,
                );
                if (mounted.current) setPlan(p);
              })
            }
          >
            设备适配与验收准备
          </button>
        </div>
        {showEvidence && (
          <EvidenceGallery
            items={evidence.filter((e) => e.skillId === skill.id)}
            onSkill={() => setShowEvidence(false)}
          />
        )}
        {plan && (
          <DeploymentPanel
            plan={plan}
            busy={busy}
            onPrepare={(action, completed) =>
              void perform(async () => {
                const p = await client.current.request<Deployment>(
                  `/api/skills/${skill.id}/deployment/preparation`,
                  { revision: skill.revision, action, completed },
                );
                if (mounted.current) setPlan(p);
              })
            }
          />
        )}
        {!!trials.length && (
          <details>
            <summary>试跑报告 · {trials.length}</summary>
            {trials.map((t) => (
              <button
                className="draft-link"
                key={t.id}
                onClick={() => setTrial(t)}
              >
                {statusLabel(t.status)} · {t.summary}
              </button>
            ))}
          </details>
        )}
        {!!events.length && (
          <details>
            <summary>最近运行记录</summary>
            {events
              .slice(-20)
              .reverse()
              .map((e) => (
                <p key={e.sequence}>
                  {e.type} · {timeLabel(e.at)}
                </p>
              ))}
          </details>
        )}
        <div className="button-row">
          {skill.status === "active" && (
            <>
              {!skill.replay && (
                <>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      void perform(() =>
                        client.current.request(
                          `/api/skills/${skill.id}/recheck`,
                          { acknowledged: false },
                        ),
                      )
                    }
                  >
                    重新观察
                  </button>
                  {skill.alert === "open" && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void perform(() =>
                          client.current.request(
                            `/api/skills/${skill.id}/recheck`,
                            { acknowledged: true },
                          ),
                        )
                      }
                    >
                      我已处理，请复核
                    </button>
                  )}
                </>
              )}
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void lifecycle("pause")}
              >
                暂停守护
              </button>
            </>
          )}
          {skill.status === "paused" && (
            <button
              className="primary"
              disabled={busy || skill.needsTimingReview}
              onClick={() => void lifecycle("resume")}
            >
              恢复守护
            </button>
          )}
          {skill.replay && skill.alert === "open" && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void perform(() =>
                  client.current.request(
                    `/api/skills/${skill.id}/replay-acknowledge`,
                    {},
                  ),
                )
              }
            >
              标记已核验（保留证据）
            </button>
          )}
          {["active", "paused"].includes(skill.status) && (
            <button
              className="secondary"
              onClick={() => {
                onClose();
                onAssistant("我想调整这项守护规则：", skill.id);
              }}
            >
              修改规则
            </button>
          )}
          {["draft", "active", "paused"].includes(skill.status) && (
            <button
              className="text-button danger"
              disabled={busy}
              onClick={() => setStopping(true)}
            >
              {skill.status === "draft" ? "丢弃草案" : "停止任务"}
            </button>
          )}
        </div>
        {stopping && (
          <div className="confirmation-box">
            <p>停止后需重新创建任务，已有证据保留。</p>
            <button
              className="primary danger-button"
              disabled={busy}
              onClick={() => void lifecycle("stop")}
            >
              确认停止
            </button>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => setStopping(false)}
            >
              取消
            </button>
          </div>
        )}
        {!!conflicts.length && (
          <ConflictConfirmation
            conflicts={conflicts}
            busy={busy}
            onCancel={() => setConflicts([])}
            onConfirm={() =>
              void lifecycle(
                "resume",
                Object.fromEntries(
                  conflicts.map((c) => [c.skillId, c.executionEpoch]),
                ),
              )
            }
          />
        )}
        {trial && <TrialReport trial={trial} onClose={() => setTrial(null)} />}
      </div>
    </Modal>
  );
}

export function SkillEditor({
  initial,
  data,
  onClose,
  onRefresh,
}: {
  initial: Skill;
  data: Bootstrap;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const normalized = (s: Skill) => ({
    ...s,
    rules: { ...defaultRules, ...s.rules },
  });
  const [skill, setSkill] = useState(() => normalized(initial)),
    [saved, setSaved] = useState(() => JSON.stringify(normalized(initial)));
  const [step, setStep] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [capability, setCapability] = useState<Capability | null>(null),
    [trial, setTrial] = useState<Trial | null>(null),
    [reviewed, setReviewed] = useState(false);
  const [ack, setAck] = useState(false),
    [expected, setExpected] = useState("explore"),
    [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [discard, setDiscard] = useState(false),
    [camera, setCamera] = useState(initial.target.cameraId),
    [plan, setPlan] = useState<Deployment | null>(null);
  const mounted = useRef(true),
    client = useRef(api.scoped());
  const dirty = JSON.stringify(skill) !== saved;
  const validROI = (r: ROI) =>
    [r.x, r.y, r.width, r.height].every(Number.isFinite) &&
    r.x >= 0 &&
    r.y >= 0 &&
    r.width > 0 &&
    r.height > 0 &&
    r.x + r.width <= 1.000001 &&
    r.y + r.height <= 1.000001;
  const valid =
    skill.name.trim().length > 0 &&
    skill.prompt.trim().length >= 2 &&
    skill.target.description.trim().length > 0 &&
    skill.devices.length > 0 &&
    skill.devices.length <= 2 &&
    validROI(skill.target.box) &&
    skill.devices.every(
      (id) => !!skill.regions[id] && validROI(skill.regions[id]),
    ) &&
    Number.isInteger(skill.rules.sampleIntervalSeconds) &&
    skill.rules.sampleIntervalSeconds >= 3 &&
    skill.rules.sampleIntervalSeconds <= 300 &&
    Number.isInteger(skill.rules.confirmationSeconds) &&
    skill.rules.confirmationSeconds <= 600 &&
    skill.rules.confirmationSeconds >= skill.rules.sampleIntervalSeconds &&
    skill.rules.durationSeconds >= 0 &&
    skill.rules.durationSeconds <= 86400 &&
    skill.rules.description.trim().length >= 2;
  const update = (value: Partial<Skill>) => {
    setSkill((old) => ({ ...old, ...value }));
    setReviewed(false);
    setAck(false);
  };
  const rules = (value: Partial<Skill["rules"]>) =>
    update({ rules: { ...skill.rules, ...value } });
  const check = async () => {
    const [c, t] = await Promise.all([
      client.current.request<Capability>(`/api/skills/${skill.id}/capability`),
      client.current.request<Trial[]>(`/api/skills/${skill.id}/trials`),
    ]);
    if (mounted.current) {
      setCapability(c);
      setTrial(t[0] || null);
    }
  };
  useEffect(() => {
    mounted.current = true;
    void check().catch((e) => {
      if (mounted.current) setError(e.message);
    });
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!trial || !running(trial.status)) return;
    let alive = true,
      loading = false;
    const timer = setInterval(async () => {
      if (loading) return;
      loading = true;
      try {
        const value = await client.current.request<Trial>(
          `/api/skill-trials/${trial.id}`,
        );
        if (alive) setTrial(value);
      } catch (e) {
        if (alive)
          setError(e instanceof Error ? e.message : "试跑报告同步失败");
      } finally {
        loading = false;
      }
    }, 1800);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [trial?.id, trial?.status]);
  const perform = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      if (mounted.current) {
        if (e instanceof APIError && e.conflicts.length)
          setConflicts(e.conflicts);
        else setError(e instanceof Error ? e.message : "操作未完成");
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const save = async () => {
    const { revision, name, prompt, target, regions, devices, replay } = skill;
    // Historical frame-count fields are not part of the current editing contract.
    const cleanRules = Object.fromEntries(
      Object.keys(defaultRules).map((key) => [
        key,
        skill.rules[key as keyof typeof defaultRules],
      ]),
    );
    const value = await client.current.request<Skill>(
      `/api/skills/${skill.id}`,
      {
        revision,
        name: name.trim(),
        prompt: prompt.trim(),
        target,
        regions,
        devices,
        rules: cleanRules,
        replay: replay || null,
      },
      undefined,
      "PATCH",
    );
    if (!mounted.current) return;
    const next = normalized(value);
    setSkill(next);
    setSaved(JSON.stringify(next));
    setReviewed(false);
    setAck(false);
    setCapability(value.capability || null);
    await check();
    await onRefresh();
  };
  const confirm = async (switchFrom: Record<string, string> = {}) => {
    await client.current.request(`/api/skills/${skill.id}/confirm`, {
      revision: skill.revision,
      fixtureAcknowledged: !skill.replay && ack,
      replayAcknowledged: !!skill.replay && ack,
      trialId: trial?.id,
      trialReviewed: reviewed,
      switchFrom,
    });
    await onRefresh();
    if (mounted.current) onClose();
  };
  const selectSource = (id: string) => {
    const record = data.recordings?.find((r) => r.id === id);
    if (record) {
      update({
        replay: { recordingId: id },
        devices: [record.cameraId],
        target: { ...skill.target, cameraId: record.cameraId },
        regions: {
          [record.cameraId]: skill.regions[record.cameraId] || initialROI,
        },
        rules: {
          ...skill.rules,
          trigger: "leaves_region",
          completion: "once",
          saveEvidence: true,
        },
      });
      setCamera(record.cameraId);
    } else update({ replay: null });
  };
  const image = skill.replay
    ? `/api/recordings/${skill.replay.recordingId}/preview`
    : data.cameras.find((c) => c.id === camera)?.lastFrameUrl;
  const ready =
    !dirty &&
    capability?.canActivate &&
    ack &&
    (!skill.replay ||
      (trial?.canConfirm &&
        !trial.stale &&
        trial.revision === skill.revision &&
        reviewed));
  return (
    <Modal
      title="设置守护"
      busy={busy}
      onClose={() => (dirty ? setDiscard(true) : onClose())}
    >
      <div className="page-stack">
        <div className="segmented" aria-label="守护设置步骤">
          {["对象", "条件", "确认"].map((label, i) => (
            <button
              aria-pressed={step === i}
              key={i}
              disabled={busy || i > step}
              onClick={() => setStep(i)}
            >
              {i + 1} · {label}
            </button>
          ))}
        </div>
        <p className="subtle-note">
          保存草案不会开始守护。设备能力、输入来源和人工确认共同决定是否可以启用。
        </p>
        <ErrorNotice error={error} />
        <fieldset disabled={busy} className="page-stack">
          {step === 0 && (
            <>
              <div className="form-grid">
                <label>
                  守护名称
                  <input
                    value={skill.name}
                    maxLength={80}
                    onChange={(e) => update({ name: e.target.value })}
                  />
                </label>
                <label>
                  观察对象
                  <input
                    value={skill.target.description}
                    maxLength={200}
                    onChange={(e) =>
                      update({
                        target: {
                          ...skill.target,
                          description: e.target.value,
                        },
                      })
                    }
                  />
                </label>
              </div>
              <label>
                需求描述
                <textarea
                  rows={3}
                  value={skill.prompt}
                  maxLength={2000}
                  onChange={(e) => update({ prompt: e.target.value })}
                />
              </label>
              <label>
                数据来源
                <select
                  value={skill.replay?.recordingId || ""}
                  onChange={(e) => selectSource(e.target.value)}
                >
                  <option value="">摄像头输入（实际执行能力需检查）</option>
                  {(data.recordings || [])
                    .filter(
                      (r) => (r.duration || 0) >= 2 && (r.duration || 0) <= 60,
                    )
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        录像回放：{r.title}
                      </option>
                    ))}
                </select>
              </label>
              <fieldset className="camera-choices">
                <legend>选择摄像头（最多两台）</legend>
                {data.cameras.map((c) => (
                  <label className="check-label" key={c.id}>
                    <input
                      type="checkbox"
                      checked={skill.devices.includes(c.id)}
                      disabled={
                        !!skill.replay ||
                        (!skill.devices.includes(c.id) &&
                          skill.devices.length >= 2) ||
                        (skill.devices.includes(c.id) &&
                          skill.devices.length === 1)
                      }
                      onChange={(e) => {
                        const devices = e.target.checked
                          ? [...skill.devices, c.id]
                          : skill.devices.filter((id) => id !== c.id);
                        const target = {
                          ...skill.target,
                          cameraId: devices.includes(skill.target.cameraId)
                            ? skill.target.cameraId
                            : devices[0],
                        };
                        update({
                          devices,
                          target,
                          regions: Object.fromEntries(
                            devices.map((id) => [
                              id,
                              skill.regions[id] || initialROI,
                            ]),
                          ),
                        });
                        if (!devices.includes(camera)) setCamera(devices[0]);
                      }}
                    />
                    {c.name} · {c.model}
                  </label>
                ))}
              </fieldset>
              <div className="form-grid">
                <label>
                  主观察视角
                  <select
                    value={skill.target.cameraId}
                    onChange={(e) => {
                      update({
                        target: { ...skill.target, cameraId: e.target.value },
                      });
                      setCamera(e.target.value);
                    }}
                  >
                    {skill.devices.map((id) => (
                      <option value={id} key={id}>
                        {data.cameras.find((c) => c.id === id)?.name || id}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  正在圈选的视角
                  <select
                    value={camera}
                    onChange={(e) => setCamera(e.target.value)}
                  >
                    {skill.devices.map((id) => (
                      <option value={id} key={id}>
                        {data.cameras.find((c) => c.id === id)?.name || id}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <RegionEditor
                key={camera}
                image={image}
                target={
                  camera === skill.target.cameraId
                    ? skill.target.box
                    : undefined
                }
                region={skill.regions[camera] || initialROI}
                onTarget={(box) => update({ target: { ...skill.target, box } })}
                onRegion={(box) =>
                  update({ regions: { ...skill.regions, [camera]: box } })
                }
              />
            </>
          )}
          {step === 1 && (
            <>
              <label>
                任务类型
                <select
                  value={skill.rules.taskKind}
                  onChange={(e) => rules({ taskKind: e.target.value })}
                >
                  <option value="unspecified">请选择具体类型</option>
                  <option value="parcel_removal">包裹离开关注区域</option>
                  <option value="marker_region">测试标记区域进出</option>
                  <option value="pet_activity">宠物行为（执行器待接入）</option>
                  <option value="vehicle_activity">
                    车辆行为（执行器待接入）
                  </option>
                  <option value="custom">其他需求（执行器待接入）</option>
                </select>
              </label>
              <div className="form-grid">
                <label>
                  触发条件
                  <select
                    value={skill.rules.trigger}
                    onChange={(e) => rules({ trigger: e.target.value })}
                  >
                    <option value="leaves_region">离开区域</option>
                    {!skill.replay && (
                      <>
                        <option value="enters_region">进入区域</option>
                        <option value="record_activity">
                          记录活动（执行器待接入）
                        </option>
                      </>
                    )}
                  </select>
                </label>
                <label>
                  任务方式
                  <select
                    disabled={!!skill.replay}
                    value={skill.rules.completion}
                    onChange={(e) => rules({ completion: e.target.value })}
                  >
                    <option value="continuous">持续守护</option>
                    <option value="once">触发一次后完成</option>
                  </select>
                </label>
                <label>
                  检测间隔（秒）
                  <input
                    type="number"
                    min={3}
                    max={300}
                    value={skill.rules.sampleIntervalSeconds}
                    onChange={(e) =>
                      rules({
                        sampleIntervalSeconds: Number(e.target.value),
                        confirmationSeconds: Math.max(
                          Number(e.target.value),
                          skill.rules.confirmationSeconds,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  确认跨度（秒）
                  <input
                    type="number"
                    min={skill.rules.sampleIntervalSeconds}
                    max={600}
                    value={skill.rules.confirmationSeconds}
                    onChange={(e) =>
                      rules({ confirmationSeconds: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
              <label>
                需求补充
                <textarea
                  rows={3}
                  maxLength={300}
                  value={skill.rules.description}
                  onChange={(e) => rules({ description: e.target.value })}
                />
              </label>
              <details>
                <summary>额外行为持续时间（执行器待接入）</summary>
                <label>
                  持续时间（秒，0 为无）
                  <input
                    type="number"
                    min={0}
                    max={86400}
                    value={skill.rules.durationSeconds}
                    onChange={(e) =>
                      rules({ durationSeconds: Number(e.target.value) })
                    }
                  />
                </label>
              </details>
              <p>
                看不清、遮挡或设备离线时保留判断。离散采样可能漏过短暂动作，报告时间为确认时刻。
              </p>
            </>
          )}
          {step === 2 && (
            <>
              <h3>{skill.name}</h3>
              <p>
                {skill.target.description} ·{" "}
                {skill.replay ? "录像回放测试" : "摄像头输入"}
              </p>
              {dirty && (
                <p className="notice error">草案已修改，请保存并重新检查。</p>
              )}
              {capability && (
                <div className="capability-box">
                  <strong>{capability.label}</strong>
                  {capability.blockers.map((b) => (
                    <p className="warning-text" key={b}>
                      {b}
                    </p>
                  ))}
                  {capability.contract && (
                    <ContractSummary contract={capability.contract} />
                  )}
                  {capability.warnings.map((w) => (
                    <p key={w}>{w}</p>
                  ))}
                </div>
              )}
              <button
                className="secondary"
                disabled={!valid}
                onClick={() =>
                  void perform(async () => {
                    if (dirty) await save();
                    else await check();
                  })
                }
              >
                保存并检查能力
              </button>
              {skill.replay && (
                <section className="trial-panel">
                  <h3>启用前试跑</h3>
                  <label>
                    人工预期
                    <select
                      value={expected}
                      onChange={(e) => setExpected(e.target.value)}
                    >
                      <option value="explore">探索，不作为验收</option>
                      <option value="alert">应该提醒</option>
                      <option value="no_alert">不应提醒</option>
                    </select>
                  </label>
                  <button
                    className="secondary"
                    disabled={
                      dirty ||
                      !capability?.canTrial ||
                      (!!trial && running(trial.status))
                    }
                    onClick={() =>
                      void perform(async () => {
                        const t = await client.current.request<Trial>(
                          `/api/skills/${skill.id}/trials`,
                          {
                            revision: skill.revision,
                            expectedOutcome: expected,
                          },
                        );
                        if (mounted.current) {
                          setTrial(t);
                          setReviewed(false);
                        }
                      })
                    }
                  >
                    开始试跑
                  </button>
                  {trial && (
                    <>
                      <TrialContent trial={trial} />
                      {running(trial.status) && (
                        <button
                          className="text-button"
                          onClick={() =>
                            void perform(async () => {
                              const t = await client.current.request<Trial>(
                                `/api/skill-trials/${trial.id}/cancel`,
                                {},
                              );
                              if (mounted.current) setTrial(t);
                            })
                          }
                        >
                          取消试跑
                        </button>
                      )}
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={reviewed}
                          disabled={dirty || !trial.canConfirm || trial.stale}
                          onChange={(e) => setReviewed(e.target.checked)}
                        />
                        我已核验本版本的试跑报告
                      </label>
                    </>
                  )}
                </section>
              )}
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={ack}
                  onChange={(e) => setAck(e.target.checked)}
                />
                {skill.replay
                  ? "我确认使用录像回放测试此规则"
                  : "我确认仅使用合成测试标记验证规则"}
              </label>
              <button
                className="secondary"
                disabled={dirty}
                onClick={() =>
                  void perform(async () => {
                    const p = await client.current.request<Deployment>(
                      `/api/skills/${skill.id}/deployment`,
                    );
                    if (mounted.current) setPlan(p);
                  })
                }
              >
                查看设备适配与配合事项
              </button>
              {plan && (
                <DeploymentPanel
                  plan={plan}
                  busy={busy}
                  onPrepare={(action, completed) =>
                    void perform(async () => {
                      const p = await client.current.request<Deployment>(
                        `/api/skills/${skill.id}/deployment/preparation`,
                        { revision: skill.revision, action, completed },
                      );
                      if (mounted.current) setPlan(p);
                    })
                  }
                />
              )}
            </>
          )}
        </fieldset>
        <div className="sticky-actions">
          <button
            className="secondary"
            disabled={busy || !valid}
            onClick={() => void perform(save)}
          >
            保存草案
          </button>
          {step < 2 ? (
            <button
              className="primary"
              disabled={busy || !valid}
              onClick={() =>
                step === 0
                  ? setStep(1)
                  : void perform(async () => {
                      if (dirty) await save();
                      else await check();
                      if (mounted.current) setStep(2);
                    })
              }
            >
              {step === 0 ? "下一步：提醒条件" : "保存草案，检查并确认"}
            </button>
          ) : (
            <button
              className="primary"
              disabled={busy || !ready || !valid}
              onClick={() => void perform(() => confirm())}
            >
              {skill.replay ? "确认并开始回放" : "确认并开始标记测试"}
            </button>
          )}
        </div>
        {!!conflicts.length && (
          <ConflictConfirmation
            conflicts={conflicts}
            busy={busy}
            onCancel={() => setConflicts([])}
            onConfirm={() =>
              void perform(() =>
                confirm(
                  Object.fromEntries(
                    conflicts.map((c) => [c.skillId, c.executionEpoch]),
                  ),
                ),
              )
            }
          />
        )}
        {discard && (
          <div className="confirmation-box">
            <p>放弃尚未保存的修改？已保存的草案仍会保留。</p>
            <button className="secondary" onClick={onClose}>
              放弃修改并返回
            </button>
            <button className="text-button" onClick={() => setDiscard(false)}>
              继续编辑
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function RegionEditor({
  image,
  target,
  region,
  onTarget,
  onRegion,
}: {
  image?: string;
  target?: ROI;
  region: ROI;
  onTarget: (r: ROI) => void;
  onRegion: (r: ROI) => void;
}) {
  const [mode, setMode] = useState("region");
  const drag = useRef<{ x: number; y: number } | null>(null);
  const current = mode === "target" && target ? target : region;
  const set = mode === "target" && target ? onTarget : onRegion;
  return (
    <div className="region-editor">
      <div className="segmented">
        <button
          aria-pressed={mode === "region"}
          onClick={() => setMode("region")}
        >
          蓝框：关注区域
        </button>
        {target && (
          <button
            aria-pressed={mode === "target"}
            onClick={() => setMode("target")}
          >
            橙框：观察对象
          </button>
        )}
      </div>
      <div className="region-canvas">
        {image ? (
          <ImageEvidence path={image} alt="用于圈选的参考画面" />
        ) : (
          <div className="region-placeholder">
            暂无参考画面，可先保存坐标；请在启用前核对真实视野。
          </div>
        )}
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-label="拖动圈选区域，也可在下方输入坐标"
          onPointerDown={(e) => {
            const b = e.currentTarget.getBoundingClientRect();
            drag.current = {
              x: (e.clientX - b.left) / b.width,
              y: (e.clientY - b.top) / b.height,
            };
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            const b = e.currentTarget.getBoundingClientRect();
            const x = Math.max(0, Math.min(1, (e.clientX - b.left) / b.width)),
              y = Math.max(0, Math.min(1, (e.clientY - b.top) / b.height));
            const box = {
              x: Math.min(x, drag.current.x),
              y: Math.min(y, drag.current.y),
              width: Math.abs(x - drag.current.x),
              height: Math.abs(y - drag.current.y),
            };
            if (box.width >= 0.005 && box.height >= 0.005) set(box);
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
        >
          <rect
            x={region.x * 100}
            y={region.y * 100}
            width={region.width * 100}
            height={region.height * 100}
            fill="#246bfe22"
            stroke="#246bfe"
            strokeWidth=".6"
          />
          {target && (
            <rect
              x={target.x * 100}
              y={target.y * 100}
              width={target.width * 100}
              height={target.height * 100}
              fill="#ffad2822"
              stroke="#ed8a17"
              strokeWidth=".6"
            />
          )}
        </svg>
      </div>
      <small>
        拖动鼠标或触摸圈选，坐标以画面比例保存。当前参考图不代表实时状态。
      </small>
      <div className="roi-fields">
        {(
          [
            ["x", "左侧"],
            ["y", "顶部"],
            ["width", "宽度"],
            ["height", "高度"],
          ] as const
        ).map(([key, name]) => (
          <label key={key}>
            {name}（比例）
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={Number(current[key].toFixed(4))}
              onChange={(e) =>
                set({ ...current, [key]: Number(e.target.value) })
              }
            />
          </label>
        ))}
      </div>
    </div>
  );
}
function ConflictConfirmation({
  conflicts,
  busy,
  onConfirm,
  onCancel,
}: {
  conflicts: Conflict[];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="alert" className="confirmation-box">
      <h3>摄像头正在执行其他任务</h3>
      <p>
        将暂停：{conflicts.map((c) => c.name).join("、")}
        。原任务会释放全部绑定设备，暂停期间不再检测。
      </p>
      <button className="primary" disabled={busy} onClick={onConfirm}>
        暂停占用任务并继续
      </button>
      <button className="text-button" disabled={busy} onClick={onCancel}>
        保留原任务
      </button>
    </div>
  );
}
function ContractSummary({ contract }: { contract: Contract }) {
  return (
    <dl className="contract-list">
      {(
        [
          ["precondition", "前提"],
          ["trigger", "触发"],
          ["temporal", "时间"],
          ["unknown", "无法确认时"],
          ["evidence", "证据"],
          ["completion", "结束条件"],
        ] as const
      ).map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>{contract[key]}</dd>
        </div>
      ))}
    </dl>
  );
}
function TrialContent({ trial }: { trial: Trial }) {
  const [source, setSource] = useState(false);
  return (
    <div className="trial-report">
      <p>
        <strong>
          {statusLabel(trial.status)}
          {trial.stale ? " · 报告已过期" : ""}
        </strong>{" "}
        · 规则版本 {trial.revision}
      </p>
      <p>{trial.summary}</p>
      {trial.sourceRecordingId && (
        <>
          <button className="secondary" onClick={() => setSource((v) => !v)}>
            {source ? "收起完整录像" : "播放完整测试录像，核对人工预期"}
          </button>
          {source && (
            <VideoPlayer
              path={`/api/recordings/${trial.sourceRecordingId}/video`}
            />
          )}
        </>
      )}
      <p>
        {trial.canConfirm ? "本段符合人工预期，仅限回放" : "尚不能作为启用依据"}
      </p>
      <small>
        人工预期：{trial.expectedOutcome || "explore"} ·{" "}
        {trial.wouldAlert ? "会形成提醒" : "未形成提醒"}
      </small>
      {trial.videoUrl && (
        <VideoPlayer
          path={trial.videoUrl}
          offset={Math.max(0, (trial.eventTime || 0) - (trial.clipStart || 0))}
        />
      )}
      {trial.contract && <ContractSummary contract={trial.contract} />}
      <details>
        <summary>采样记录与限制</summary>
        {trial.observations.map((o, i) => (
          <p key={i}>
            {o.start} s · {o.verdict} · {o.summary}
          </p>
        ))}
        {trial.limitations.map((l) => (
          <p key={l}>{l}</p>
        ))}
      </details>
    </div>
  );
}
function TrialReport({
  trial,
  onClose,
}: {
  trial: Trial;
  onClose: () => void;
}) {
  return (
    <Modal title="试跑报告" onClose={onClose}>
      <TrialContent trial={trial} />
    </Modal>
  );
}
function DeploymentPanel({
  plan,
  busy,
  onPrepare,
}: {
  plan: Deployment;
  busy: boolean;
  onPrepare: (id: string, done: boolean) => void;
}) {
  return (
    <section className="capability-box">
      <h3>真机验收准备</h3>
      <p>{plan.summary}</p>
      {plan.blockers.map((b) => (
        <p className="warning-text" key={b}>
          {b}
        </p>
      ))}
      {plan.cameras.map((c) => (
        <p key={c.id}>
          {c.name} · {c.reason}
        </p>
      ))}
      {plan.actions.map((a) => (
        <label className="check-label" key={a.id}>
          <input
            type="checkbox"
            disabled={busy}
            checked={a.completed}
            onChange={(e) => onPrepare(a.id, e.target.checked)}
          />
          {a.instruction}
        </label>
      ))}
      <small>{plan.note}</small>
      <p>完成准备不等于已发布。真机持续任务仍须服务端能力检查通过。</p>
    </section>
  );
}

export function RecordingsPanel({
  data,
  onClose,
  onRefresh,
}: {
  data: Bootstrap;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null),
    [camera, setCamera] = useState(data.cameras[0]?.id || ""),
    [date, setDate] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<Recording | null>(null);
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  const perform = async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
      if (mounted.current) await onRefresh();
    } catch (e) {
      if (mounted.current)
        setError(e instanceof Error ? e.message : "操作未完成");
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <Modal title="录像资料" busy={busy} onClose={onClose}>
      <div className="page-stack">
        <p>
          导入已有录像，用于历史查询或 2–60 秒的 Skill
          回放测试。上传录像不代表开启设备持续录制。
        </p>
        <ErrorNotice error={error} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (file)
              void perform(async () => {
                await api.uploadRecording(
                  file,
                  camera,
                  date ? new Date(date).getTime() / 1000 : undefined,
                );
                if (mounted.current) {
                  setFile(null);
                  (
                    document.getElementById(
                      "recording-file",
                    ) as HTMLInputElement
                  ).value = "";
                }
              });
          }}
        >
          <fieldset disabled={busy}>
            <label>
              选择录像（上限 150 MB）
              <input
                id="recording-file"
                type="file"
                accept="video/*,.mp4,.mov,.mkv"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <div className="form-grid">
              <label>
                录像所属摄像头
                <select
                  value={camera}
                  onChange={(e) => setCamera(e.target.value)}
                >
                  {data.cameras.map((c) => (
                    <option value={c.id} key={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                拍摄开始时间（可不填）
                <input
                  type="datetime-local"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
            </div>
            <p className="subtle-note">
              未知日期请留空，不能用上传时间代替拍摄时间。
            </p>
            <button className="primary" disabled={busy || !file || !camera}>
              {busy ? "正在处理…" : "上传录像"}
            </button>
          </fieldset>
        </form>
        <div className="recording-list">
          {(data.recordings || []).map((r) => (
            <article className="card product-card" key={r.id}>
              <h3>{r.title}</h3>
              <p>
                {statusLabel(r.status)} · {r.duration?.toFixed(1) || "—"} 秒 ·
                拍摄时间 {timeLabel(r.recordedAt)}
              </p>
              {r.error && <p className="warning-text">{r.error}</p>}
              <div className="button-row">
                <button className="secondary" onClick={() => setSelected(r)}>
                  播放录像
                </button>
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    ["indexing", "queued", "processing"].includes(r.status)
                  }
                  onClick={() =>
                    void perform(() =>
                      api.request(`/api/recordings/${r.id}/index`, {}),
                    )
                  }
                >
                  建立检索索引
                </button>
              </div>
            </article>
          ))}
        </div>
        {!data.recordings?.length && (
          <p className="empty-inline">还没有录像资料。</p>
        )}
        {selected && (
          <Modal title={selected.title} onClose={() => setSelected(null)}>
            <VideoPlayer path={selected.playbackUrl} />
          </Modal>
        )}
      </div>
    </Modal>
  );
}
