import type { Capture, Device, Run } from "./api";

export type Tab = "assistant" | "cameras" | "tasks" | "memory" | "settings";
export type ROI = { x: number; y: number; width: number; height: number };
export const initialROI: ROI = { x: 0.18, y: 0.25, width: 0.55, height: 0.55 };
export type Rules = {
  taskKind: string;
  durationSeconds: number;
  trigger: string;
  minConfidence: number;
  sampleIntervalSeconds: number;
  confirmationSeconds: number;
  unknownPolicy: string;
  completion: string;
  saveEvidence: boolean;
  description: string;
};
export const defaultRules: Rules = {
  taskKind: "unspecified",
  durationSeconds: 0,
  trigger: "leaves_region",
  minConfidence: 0.85,
  sampleIntervalSeconds: 3,
  confirmationSeconds: 6,
  unknownPolicy: "hold_and_recheck",
  completion: "continuous",
  saveEvidence: true,
  description: "按秒抽样确认关注区域状态，无法确认时保留判断",
};
export type Contract = {
  precondition: string;
  trigger: string;
  temporal: string;
  unknown: string;
  evidence: string;
  completion: string;
};
export type Capability = {
  status: string;
  label: string;
  canActivate: boolean;
  canTrial: boolean;
  blockers: string[];
  warnings: string[];
  contract?: Contract;
};
export type Skill = {
  id: string;
  name: string;
  prompt: string;
  revision: number;
  status: string;
  target: {
    description: string;
    cameraId: string;
    channelId: string;
    box: ROI;
  };
  devices: string[];
  regions: Record<string, ROI>;
  rules: Rules;
  mode: string;
  result: string;
  resultReason: string;
  alert: string;
  createdAt: number;
  lastObservedAt?: number;
  replay?: { recordingId: string } | null;
  replayState?: { cursor: number; online: boolean; modelCalls: number };
  capability?: Capability;
  needsTimingReview?: boolean;
  replacesId?: string;
};
export type Conflict = {
  skillId: string;
  name: string;
  executionEpoch: string;
  devices: string[];
};
export type Trial = {
  id: string;
  skillId: string;
  revision: number;
  status: string;
  summary: string;
  stale: boolean;
  canConfirm: boolean;
  wouldAlert: boolean;
  expectedOutcome?: string;
  sourceRecordingId?: string;
  videoUrl?: string;
  eventTime?: number;
  clipStart?: number;
  contract: Contract;
  observations: {
    start: number;
    end: number;
    baseline: boolean;
    verdict: string;
    summary: string;
  }[];
  limitations: string[];
};
export type Deployment = {
  status: string;
  canPublish: boolean;
  summary: string;
  blockers: string[];
  note: string;
  cameras: { id: string; name: string; reason: string; verdict: string }[];
  actions: { id: string; instruction: string; completed: boolean }[];
};
export type Recording = {
  id: string;
  cameraId: string;
  title: string;
  status: string;
  sourceType: string;
  duration?: number;
  recordedAt?: number;
  error?: string;
  playbackUrl: string;
  segmentCount?: number;
};
export type Evidence = {
  id: string;
  skillId?: string;
  cameraId?: string;
  reason: string;
  imageUrl?: string;
  deviceName?: string;
  sourceType?: string;
  capturedAt?: number;
  sampledAt?: number;
  videoUrl?: string;
  recordingId?: string;
  seekSeconds?: number;
};
export type Preferences = {
  enabled: boolean;
  dailySummary: boolean;
  summaryHour: number;
  quietStart: number;
  quietEnd: number;
  timezone: string;
};
export type Memory = {
  source?: string;
  sourceQuote?: string;
  id: string;
  content: string;
  createdAt: number;
  expiresAt?: number | null;
};
export type Notice = {
  id: string;
  kind: string;
  title: string;
  body: string;
  createdAt: number;
  read: boolean;
  skillId?: string;
};
export type AssistantMessage = Notice & {
  why: string;
  feedback?: string;
  sources: {
    id: string;
    type: string;
    name?: string;
    reason?: string;
    limitation?: string;
    evidenceId?: string;
    skillId?: string;
    sourceType?: string;
  }[];
};
export type Personal = {
  automaticMemory?: { enabled: boolean; pending: number; status: string; reason: string };
  revision: number;
  preferences: Preferences;
  memories: Memory[];
  inbox: Notice[];
  messages?: AssistantMessage[];
  activity?: {
    id: string;
    status: string;
    reason: string;
    createdAt: number;
  }[];
  delivery: string;
  lastError?: string;
};
export type Camera = Device & {
  adapter?: string;
  channels?: { id: string; label: string }[];
};
export type Bootstrap = {
  skills: Skill[];
  cameras: Camera[];
  evidence: Evidence[];
  recordings?: Recording[];
  personal?: Personal;
  agent: { ready: boolean; provider: string; mode: string };
};
export const emptyBootstrap: Bootstrap = {
  skills: [],
  cameras: [],
  evidence: [],
  agent: { ready: false, provider: "", mode: "" },
};
export type Conversation = {
  id: string;
  kind: string;
  title: string;
  preview: string;
  updatedAt: number;
  unreadCount: number;
  lastMode: string;
};
export type HistoryFilter = {
  period: string;
  startAt?: number;
  endAt?: number;
};
export type ChatRun = Omit<Run, "captures"> & {
  conversationId: string;
  createdAt: number;
  executionMode?: string;
  cameraId?: string;
  draft?: Skill;
  toolReceipts?: { tool: string; status: string }[];
  captures?: (Capture & {
    cameraId?: string;
    sourceType?: string;
    historical?: boolean;
  })[];
  videos?: {
    id: string;
    recordingId: string;
    title: string;
    summary: string;
    limitation: string;
    seekSeconds: number;
    verdict: string;
  }[];
};
export const statusLabel = (value: string) =>
  ({
    active: "运行中",
    draft: "待确认",
    paused: "已暂停",
    stopped: "已停止",
    completed: "已完成",
    confirmed: "已确认",
    needs_attention: "需要处理",
    unknown: "无法确认",
    initializing: "等待观察",
    queued: "等待中",
    running: "处理中",
    failed: "失败",
    cancelled: "已取消",
  })[value] || value;
export const timeLabel = (value?: number | null) =>
  value ? new Date(value * 1000).toLocaleString() : "时间未知";
export const running = (status: string) =>
  ["queued", "running"].includes(status);
