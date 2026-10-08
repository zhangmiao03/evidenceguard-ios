import { useEffect, useState } from "react";
import { ArrowLeft, Save, FlaskConical } from "lucide-react";
import { api, APIError, running, statusLabel } from "./api";
import { RegionEditor } from "./RegionEditor";
import type { Bootstrap, Skill, Trial } from "./types";
const defaultROI = { x: 0.18, y: 0.25, width: 0.55, height: 0.55 };

export function SkillEditor({
  initial,
  data,
  close,
  changed,
}: {
  initial: Skill;
  data: Bootstrap;
  close: () => void;
  changed: () => Promise<void>;
}) {
  const [skill, setSkill] = useState(() => structuredClone(initial));
  const [dirty, setDirty] = useState(false);
  const [mode, setMode] = useState<"target" | "region">("target");
  const [regionCamera, setRegionCamera] = useState(initial.target.cameraId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [trial, setTrial] = useState<Trial | null>(null);
  const [expected, setExpected] = useState("explore");
  const [reviewed, setReviewed] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [conflicts, setConflicts] = useState<APIError["conflicts"]>([]);
  const cameraID = mode === "target" ? skill.target.cameraId : regionCamera;
  const camera = data.cameras.find((c) => c.id === cameraID);
  const imageURL = skill.replay
    ? `/api/recordings/${encodeURIComponent(skill.replay.recordingId)}/preview`
    : camera?.lastFrameUrl;
  const editable = skill.status === "draft";
  function edit(next: Skill) {
    setSkill(next);
    setDirty(true);
    setTrial(null);
    setReviewed(false);
    setAcknowledged(false);
    setConflicts([]);
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof APIError) setConflicts(e.conflicts);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!trial || !running(trial.status)) return;
    let cancelled = false;
    const timer = setInterval(() => {
      api<Trial>(`/api/skill-trials/${trial.id}`)
        .then((value) => {
          if (!cancelled) setTrial(value);
        })
        .catch((e) => {
          if (!cancelled) setError(e.message);
        });
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [trial?.id, trial?.status]);
  async function save() {
    const { revision, name, prompt, target, regions, devices, rules, replay } =
      skill;
    const value = await api<Skill>(`/api/skills/${skill.id}`, "PATCH", {
      revision,
      name,
      prompt,
      target,
      regions,
      devices,
      rules,
      replay: replay || null,
    });
    setSkill(value);
    setDirty(false);
    setTrial(null);
    setReviewed(false);
    setAcknowledged(false);
    setConflicts([]);
    await changed();
  }
  async function activate(switchFrom: Record<string, string> = {}) {
    const result = await api<Skill>(`/api/skills/${skill.id}/confirm`, "POST", {
      revision: skill.revision,
      fixtureAcknowledged: !skill.replay && acknowledged,
      replayAcknowledged: !!skill.replay && acknowledged,
      trialId: trial?.id,
      trialReviewed: reviewed,
      switchFrom,
    });
    setSkill(result);
    setConflicts([]);
    await changed();
  }
  const canConfirm =
    editable &&
    !dirty &&
    skill.capability?.canActivate &&
    acknowledged &&
    (!skill.replay ||
      (trial?.canConfirm &&
        !trial.stale &&
        trial.revision === skill.revision &&
        reviewed));
  return (
    <section className="editor-panel">
      <div className="page-title">
        <button className="icon-button" aria-label="返回" onClick={close}>
          <ArrowLeft />
        </button>
        <div>
          <h1>{editable ? "编辑守护草案" : skill.name}</h1>
          <p>
            规则版本 {skill.revision} · {statusLabel(skill.status)}
          </p>
        </div>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="editor-grid">
        <div className="card">
          <div className="toolbar">
            <h2>圈定观察内容</h2>
            <div className="segmented">
              <button
                disabled={!editable}
                className={mode === "target" ? "selected" : ""}
                onClick={() => setMode("target")}
              >
                目标框
              </button>
              <button
                disabled={!editable}
                className={mode === "region" ? "selected" : ""}
                onClick={() => setMode("region")}
              >
                关注区域
              </button>
            </div>
          </div>
          {mode === "region" && (
            <label>
              区域所属摄像头
              <select
                value={regionCamera}
                onChange={(e) => setRegionCamera(e.target.value)}
              >
                {skill.devices.map((id) => (
                  <option key={id} value={id}>
                    {data.cameras.find((c) => c.id === id)?.name || id}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className={!editable ? "read-only" : ""}>
            <RegionEditor
              url={imageURL}
              mode={mode}
              box={
                cameraID === skill.target.cameraId
                  ? skill.target.box
                  : { x: 0, y: 0, width: 0.001, height: 0.001 }
              }
              region={skill.regions[cameraID] || defaultROI}
              onChange={(box) => {
                if (!editable) return;
                edit(
                  mode === "target"
                    ? { ...skill, target: { ...skill.target, box } }
                    : {
                        ...skill,
                        regions: { ...skill.regions, [cameraID]: box },
                      },
                );
              }}
            />
          </div>
          <p className="muted">
            在画面上拖动，分别设置目标和关注区域。保存后需重新试跑；返回不会启用任务。
          </p>
          <details>
            <summary>精确调整坐标（0–1）</summary>
            <div className="number-grid">
              {(["x", "y", "width", "height"] as const).map((key) => (
                <label key={key}>
                  {key}
                  <input
                    disabled={!editable}
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={
                      (mode === "target"
                        ? skill.target.box
                        : skill.regions[cameraID] || defaultROI)[key]
                    }
                    onChange={(e) => {
                      const current =
                        mode === "target"
                          ? skill.target.box
                          : skill.regions[cameraID] || defaultROI;
                      const next = {
                        ...current,
                        [key]: Number(e.target.value),
                      };
                      edit(
                        mode === "target"
                          ? { ...skill, target: { ...skill.target, box: next } }
                          : {
                              ...skill,
                              regions: { ...skill.regions, [cameraID]: next },
                            },
                      );
                    }}
                  />
                </label>
              ))}
            </div>
          </details>
        </div>
        <div className="card">
          <h2>任务配置</h2>
          <fieldset disabled={!editable || busy}>
            <label>
              名称
              <input
                value={skill.name}
                onChange={(e) => edit({ ...skill, name: e.target.value })}
              />
            </label>
            <label>
              任务需求
              <textarea
                value={skill.prompt}
                onChange={(e) => edit({ ...skill, prompt: e.target.value })}
              />
            </label>
            <label>
              观察对象
              <input
                value={skill.target.description}
                onChange={(e) =>
                  edit({
                    ...skill,
                    target: { ...skill.target, description: e.target.value },
                  })
                }
              />
            </label>
            <label>
              主摄像头
              <select
                value={skill.target.cameraId}
                disabled={!!skill.replay}
                onChange={(e) => {
                  const id = e.target.value;
                  setRegionCamera(id);
                  edit({
                    ...skill,
                    devices: [id],
                    regions: { [id]: defaultROI },
                    target: { ...skill.target, cameraId: id, box: defaultROI },
                  });
                }}
              >
                {data.cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.model}
                  </option>
                ))}
              </select>
            </label>
            {!skill.replay &&
              data.cameras
                .filter((c) => c.id !== skill.target.cameraId)
                .map((c) => (
                  <label className="check" key={c.id}>
                    <input
                      type="checkbox"
                      checked={skill.devices.includes(c.id)}
                      onChange={(e) => {
                        const ids = e.target.checked
                          ? [...skill.devices, c.id]
                          : skill.devices.filter((id) => id !== c.id);
                        setRegionCamera(skill.target.cameraId);
                        edit({
                          ...skill,
                          devices: ids,
                          regions: Object.fromEntries(
                            ids.map((id) => [
                              id,
                              skill.regions[id] || defaultROI,
                            ]),
                          ),
                        });
                      }}
                    />
                    使用 {c.name} 补充观察（同时占用该设备）
                  </label>
                ))}
            <label>
              任务类型
              <select
                value={skill.rules.taskKind}
                onChange={(e) =>
                  edit({
                    ...skill,
                    rules: { ...skill.rules, taskKind: e.target.value },
                  })
                }
              >
                {[
                  ["unspecified", "请选择"],
                  ["parcel_removal", "包裹离区"],
                  ["marker_region", "测试标记进出"],
                  ["pet_activity", "宠物行为 · 待实现"],
                  ["vehicle_activity", "车辆行为 · 待实现"],
                  ["custom", "其他需求 · 待实现"],
                ].map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label>
              观察输入
              <select
                value={skill.replay?.recordingId || ""}
                onChange={(e) => {
                  const r = data.recordings.find(
                    (r) => r.id === e.target.value,
                  );
                  if (r) {
                    setRegionCamera(r.cameraId);
                    edit({
                      ...skill,
                      replay: { recordingId: r.id },
                      devices: [r.cameraId],
                      regions: {
                        [r.cameraId]: skill.regions[r.cameraId] || defaultROI,
                      },
                      target: { ...skill.target, cameraId: r.cameraId },
                      rules: { ...skill.rules, completion: "once" },
                    });
                  } else edit({ ...skill, replay: null });
                }}
              >
                <option value="">实时输入 · 真机尚待验收</option>
                {data.recordings.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title} · {r.duration?.toFixed(1)} s
                  </option>
                ))}
              </select>
            </label>
            <div className="number-grid">
              <label>
                Every N s
                <input
                  type="number"
                  min="3"
                  max="300"
                  value={skill.rules.sampleIntervalSeconds}
                  onChange={(e) =>
                    edit({
                      ...skill,
                      rules: {
                        ...skill.rules,
                        sampleIntervalSeconds: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
              <label>
                确认跨度（s）
                <input
                  type="number"
                  min={skill.rules.sampleIntervalSeconds}
                  max="600"
                  value={skill.rules.confirmationSeconds}
                  onChange={(e) =>
                    edit({
                      ...skill,
                      rules: {
                        ...skill.rules,
                        confirmationSeconds: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
            </div>
            <label>
              触发条件
              <select
                value={skill.rules.trigger}
                onChange={(e) =>
                  edit({
                    ...skill,
                    rules: { ...skill.rules, trigger: e.target.value },
                  })
                }
              >
                <option value="leaves_region">离开区域</option>
                <option value="enters_region">进入区域</option>
                <option value="record_activity">记录活动 · 待实现</option>
              </select>
            </label>
            <label>
              结束方式
              <select
                value={skill.rules.completion}
                onChange={(e) =>
                  edit({
                    ...skill,
                    rules: { ...skill.rules, completion: e.target.value },
                  })
                }
              >
                <option value="once">提醒一次或片尾结束</option>
                <option value="continuous">持续守护</option>
              </select>
            </label>
          </fieldset>
          <button
            className="primary"
            disabled={!editable || !dirty || busy}
            onClick={() => void perform(save)}
          >
            <Save size={16} />
            保存草案
          </button>
          {dirty && <p className="muted">有未保存修改。保存后再试跑和确认。</p>}
        </div>
      </div>
      <div className="card">
        <h2>{skill.capability?.label || "执行能力待检查"}</h2>
        {skill.capability?.blockers.map((text) => (
          <p className="notice" key={text}>
            {text}
          </p>
        ))}
        {skill.capability?.contract && (
          <dl className="contract">
            {Object.entries(skill.capability.contract).map(([key, value]) => (
              <div key={key}>
                <dt>
                  {{
                    precondition: "前提",
                    trigger: "触发",
                    temporal: "时间",
                    unknown: "无法确认时",
                    evidence: "证据",
                    completion: "结束",
                  }[key] || key}
                </dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {skill.capability?.warnings.map((text) => (
          <p className="muted" key={text}>
            {text}
          </p>
        ))}
      </div>
      {editable && (
        <div className="card">
          <h2>试跑与确认</h2>
          <p>
            每台摄像头同时运行一个实时
            Skill；历史查询只分析已入库的媒体。真机发布仍由服务端验收控制。
          </p>
          {skill.replay && (
            <>
              <label>
                本段录像预期
                <select
                  value={expected}
                  disabled={busy || (!!trial && running(trial.status))}
                  onChange={(e) => setExpected(e.target.value)}
                >
                  <option value="explore">只探索，不作为启用验收</option>
                  <option value="alert">应该提醒</option>
                  <option value="no_alert">不应该提醒</option>
                </select>
              </label>
              <button
                disabled={
                  busy ||
                  dirty ||
                  !skill.capability?.canTrial ||
                  (!!trial && running(trial.status))
                }
                onClick={() =>
                  void perform(async () => {
                    setTrial(
                      await api<Trial>(
                        `/api/skills/${skill.id}/trials`,
                        "POST",
                        { revision: skill.revision, expectedOutcome: expected },
                      ),
                    );
                    setReviewed(false);
                  })
                }
              >
                <FlaskConical size={16} />
                运行隔离试跑
              </button>
            </>
          )}
          {trial && (
            <div className="trial">
              <strong>{statusLabel(trial.status)}</strong>
              <p>{trial.summary}</p>
              {trial.videoUrl && (
                <video controls preload="metadata" src={trial.videoUrl} />
              )}
              <ol>
                {trial.observations.map((o, i) => (
                  <li key={i}>
                    {o.start}–{o.end} s · {o.summary}
                  </li>
                ))}
              </ol>
              {trial.limitations.map((t) => (
                <p className="muted" key={t}>
                  {t}
                </p>
              ))}
              {running(trial.status) && (
                <button
                  onClick={() =>
                    void perform(async () =>
                      setTrial(
                        await api<Trial>(
                          `/api/skill-trials/${trial.id}/cancel`,
                          "POST",
                          {},
                        ),
                      ),
                    )
                  }
                >
                  取消试跑
                </button>
              )}
              <label className="check">
                <input
                  type="checkbox"
                  disabled={!trial.canConfirm || trial.stale}
                  checked={reviewed}
                  onChange={(e) => setReviewed(e.target.checked)}
                />
                已看过本版本报告和片段，并核验预期结果
              </label>
            </div>
          )}
          <label className="check">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            我确认当前使用{skill.replay ? "录像回放测试" : "合成测试标记"}
            ，不代表真实摄像头守护
          </label>
          <button
            className="primary"
            disabled={busy || !canConfirm}
            onClick={() => void perform(() => activate())}
          >
            确认启用测试任务
          </button>
          {conflicts.length > 0 && (
            <div className="notice">
              <p>
                设备已有任务：{conflicts.map((c) => c.name).join("、")}
                。切换将停止这些任务。
              </p>
              <button
                disabled={busy || !canConfirm}
                onClick={() =>
                  void perform(() =>
                    activate(
                      Object.fromEntries(
                        conflicts.map((c) => [c.skillId, c.executionEpoch]),
                      ),
                    ),
                  )
                }
              >
                我确认停止上述任务并切换
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
