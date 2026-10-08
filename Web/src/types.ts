export type ROI = { x: number; y: number; width: number; height: number };
export type Camera = {
  id: string;
  name: string;
  model: string;
  connection: string;
  adapter: string;
  evidence: string;
  lastFrameUrl?: string;
  lastCapturedAt?: number;
};
export type Capability = {
  label: string;
  canActivate: boolean;
  canTrial: boolean;
  blockers: string[];
  warnings: string[];
  contract?: Record<string, string>;
};
export type Rules = {
  taskKind: string;
  trigger: string;
  durationSeconds: number;
  minConfidence: number;
  sampleIntervalSeconds: number;
  confirmationSeconds: number;
  unknownPolicy: string;
  completion: string;
  saveEvidence: boolean;
  description: string;
};
export type Skill = {
  id: string;
  name: string;
  prompt: string;
  status: string;
  revision: number;
  devices: string[];
  regions: Record<string, ROI>;
  target: {
    description: string;
    cameraId: string;
    channelId: string;
    box: ROI;
  };
  rules: Rules;
  replay?: { recordingId: string } | null;
  capability?: Capability;
  resultReason: string;
  originConversationId?: string;
};
export type Recording = {
  id: string;
  title: string;
  cameraId: string;
  status: string;
  duration?: number;
  recordedAt?: number;
  playbackUrl: string;
  error?: string;
};
export type VideoHit = {
  id: string;
  title: string;
  playbackUrl: string;
  seekSeconds: number;
  summary: string;
  limitation: string;
  verdict: string;
};
export type Run = {
  id: string;
  message: string;
  status: string;
  text?: string;
  error?: string;
  draft?: Skill;
  captures?: {
    id: string;
    cameraId: string;
    imageUrl?: string;
    reason: string;
  }[];
  videos?: VideoHit[];
};
export type Trial = {
  id: string;
  status: string;
  revision: number;
  summary: string;
  stale: boolean;
  canConfirm: boolean;
  videoUrl?: string;
  limitations: string[];
  observations: {
    start: number;
    end: number;
    summary: string;
    verdict: string;
  }[];
};
export type Bootstrap = {
  summary: { activeSkills: number; openAlerts: number; unknownSkills: number };
  skills: Skill[];
  cameras: Camera[];
  recordings: Recording[];
  evidence: {
    id: string;
    reason: string;
    imageUrl?: string;
    videoUrl?: string;
    seekSeconds?: number;
    sourceType: string;
  }[];
  agent: { ready: boolean; provider: string };
  integration: { officialSdk: string; physicalDevicesValidated: boolean };
};
