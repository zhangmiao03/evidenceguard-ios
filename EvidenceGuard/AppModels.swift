import Foundation

struct ROI: Codable, Equatable { var x: Double; var y: Double; var width: Double; var height: Double
    static let initial = ROI(x: 0.18, y: 0.25, width: 0.55, height: 0.55)
}
struct SkillTarget: Codable, Equatable { var description: String; var cameraId: String; var channelId: String; var box: ROI }
struct SkillRules: Codable, Equatable {
    var taskKind: String?
    var durationSeconds: Double?
    var trigger = "leaves_region"
    var minConfidence = 0.85
    var consecutiveFrames: Int? // Decode historical completed rules only. New drafts do not send this.
    var sampleIntervalSeconds: Int? = 3
    var confirmationSeconds: Int? = 6
    var sampleEvery: Int { get { sampleIntervalSeconds ?? 3 } set { sampleIntervalSeconds = newValue } }
    var confirmationSpan: Int { get { confirmationSeconds ?? 6 } set { confirmationSeconds = newValue } }
    var unknownPolicy = "hold_and_recheck"
    var completion = "continuous"
    var saveEvidence = true
    var description = "按秒抽样确认关注区域状态，无法确认时保留判断"
}
struct VisualSkill: Codable, Identifiable, Equatable {
    var id: String; var name: String; var prompt: String; var status: String; var revision: Int
    var target: SkillTarget; var regions: [String: ROI]; var devices: [String]; var mode: String
    var result: String; var resultReason: String; var lastObservedAt: Double?; var alert: String; var createdAt: Double
    var rules: SkillRules?; var replacesId: String?
    var capability: SkillCapability?
    var needsTimingReview: Bool?
    var originConversationId: String?
    var replay: ReplayConfig?
    var replayState: ReplayState?
    var lifecycleLabel: String { ["draft":"待确认", "active":"运行中", "paused":"已暂停", "stopped":"已停止", "completed":"已完成"][status] ?? status }
    var resultLabel: String {
        if status == "draft", let capability { return capability.canActivate ? "待确认 · " + capability.label : capability.label }
        if replay != nil && alert == "open" { return "回放提醒待核验" }
        if status != "active" { return lifecycleLabel }
        return ["confirmed":"已确认", "needs_attention":"需要处理", "unknown":"无法确认", "initializing":"等待观察"][result] ?? "无法确认"
    }
    var asset: String {
        if name.contains("宠物") { return "PetThumb" }
        if name.contains("车") { return "CarThumb" }
        if name.contains("包裹") { return "DoorThumb" }
        return "BoxThumb"
    }
}
struct CameraChannel: Codable, Equatable { var id: String; var label: String; var kind: String }
struct CameraDevice: Codable, Identifiable, Equatable {
    var id: String; var model: String; var name: String; var role: String; var connection: String; var adapter: String
    var channels: [CameraChannel]; var capabilities: [String: String]; var evidence: String
    var lastFrameUrl: String?; var lastCapturedAt: Double?
    var fresh: Bool { connection == "online" && lastCapturedAt.map { Date().timeIntervalSince1970 - $0 < 8 } == true }
    var connectionLabel: String { fresh ? "画面可用" : connection == "offline" ? "设备离线" : "等待新画面" }
}
struct EvidenceItem: Codable, Identifiable, Equatable {
    var id: String; var skillId: String; var cameraId: String; var capturedAt: Double; var relation: String
    var reason: String; var imageUrl: String?; var revision: Int; var sourceType: String
    var recordingId: String?; var clipStart: Double?; var clipEnd: Double?; var seekSeconds: Double?; var originalEventTime: Double?; var videoUrl: String?
    var title: String { if sourceType == "replay" { return "回放测试 · 区域状态提醒" }; return ["inside":"目标在区域内", "outside":"目标在区域外", "unknown":"无法确认目标位置"][relation] ?? "观察记录" }
    var exportText: String { "EvidenceGuard 观察记录\n\(title)\n\(reason)\n\(sourceType == "replay" ? "记录生成时间（非原录像拍摄时间）" : "采集时间")：\(displayTime(capturedAt))\n设备：\(cameraId)\n任务：\(skillId) · 规则版本 \(revision)\n来源：\(sourceType)\n证据 ID：\(id)" }
}
struct BootstrapSummary: Codable, Equatable { var activeSkills: Int; var openAlerts: Int; var unknownSkills: Int }
struct AgentInfo: Codable, Equatable { var provider: String; var mode: String; var ready: Bool; var tools: [String] }
struct IntegrationInfo: Codable, Equatable { var lab: String; var officialSdk: String; var physicalDevicesValidated: Bool }
struct Bootstrap: Codable, Equatable {
    var now: Double; var summary: BootstrapSummary; var skills: [VisualSkill]; var cameras: [CameraDevice]
    var evidence: [EvidenceItem]; var agent: AgentInfo; var integration: IntegrationInfo
    var recordings: [VideoRecording]?
    var videoModels: VideoModelInfo?
    var personal: PersonalSnapshot?
    static let empty = Bootstrap(now: 0, summary: .init(activeSkills: 0, openAlerts: 0, unknownSkills: 0), skills: [], cameras: [], evidence: [], agent: .init(provider: "待连接", mode: "", ready: false, tools: []), integration: .init(lab: "", officialSdk: "已收到，待真机验证", physicalDevicesValidated: false))
}
struct ToolReceipt: Codable, Equatable { var tool: String; var status: String }
struct CameraCapture: Codable, Identifiable, Equatable {
    var id: String; var cameraId: String; var skillId: String?; var status: String; var reason: String
    var requestedAt: Double; var capturedAt: Double?; var imageUrl: String?; var sourceType: String?
    var historical: Bool?
}
struct CameraOccupancy: Codable, Identifiable, Equatable {
    var skillId: String; var name: String; var devices: [String]; var executionEpoch: String
    var id: String { skillId }
}
struct AgentRun: Codable, Identifiable, Equatable {
    var id: String; var conversationId: String; var skillId: String?; var message: String; var status: String; var createdAt: Double
    var text: String?; var error: String?; var draft: VisualSkill?; var toolReceipts: [ToolReceipt]
    var captures: [CameraCapture]?
    var executionMode: String?
    var videos: [VideoHit]?
    var cameraId: String?
    var historyFilter: HistoryFilter?
    var historyScope: HistoryFilter?
    var isRunning: Bool { status == "queued" || status == "running" }
}
struct RunEvent: Decodable, Identifiable {
    var runId: String; var sequence: Int; var type: String; var at: Double?
    var payload: RunProgress?
    var progressLabel: String {
        if type == "video_verification_progress", let done = payload?.completed, let total = payload?.total { return "已复核 \(done)/\(total) 段录像" }
        return ["video_search_started":"正在筛选已存录像", "video_search_empty":"所选范围暂无可检索录像", "video_embedding_started":"正在检索相关片段", "video_candidates_found":"已找到候选，等待视频复核", "video_verification_started":"正在观看候选录像", "video_search_completed":"视频复核完成，正在整理证据"][type] ?? label
    }
    var id: String { "\(runId)-\(sequence)" }
    var label: String { ["timing_review_required":"检测已升级为按秒抽样，需重新验收", "trial_reviewed":"已核验试跑报告", "capability_checked":"已检查任务执行能力", "replay_acknowledged":"已标记核验，证据保留", "camera_requested":"已请求新画面", "camera_completed":"已取得新画面", "camera_failed":"画面请求未完成", "recheck_requested":"已请求复核", "alert_opened":"触发提醒", "alert_resolved":"新证据确认恢复", "observation_recovered":"恢复观察，等待新画面", "result_changed":"观察结果更新", "skill_confirmed":"用户已确认启用", "skill_revised":"草案已更新", "skill_drafted":"已生成草案", "lifecycle_changed":"任务状态已变更", "skill_completed":"一次性任务已完成", "replay_observing":"正在分析已到达的回放片段", "replay_model_completed":"回放模型观察完成", "replay_model_failed":"回放模型复核失败", "replay_input_failed":"回放输入失败，已暂停", "replay_finished":"回放测试结束", "replay_interrupted":"回放中断，等待恢复", "replay_transport_changed":"回放输入连接已变化", "run_queued":"请求已排队", "run_started":"开始理解需求", "model_started":"AI 正在处理", "tool_started":"正在查询或生成草案", "tool_completed":"操作已完成", "tool_failed":"操作未完成", "frame_attached":"已附上所选摄像头画面", "frame_unavailable":"本次未取得画面", "response_completed":"回复已完成", "run_failed":"本次请求未完成", "run_cancelled":"已取消"][type] ?? type }
}
enum AppRoute: Hashable {
    case skill(String), evidence(String), evidenceList(String?), cameras, camera(String), alerts
    case conversation(String, String?), settings, officialSDK, notificationSettings, voiceSettings, privacy, help, profile
    case addDevice, personalAgent, personalInbox
    case recordings, video(String, Double), replayVideo(String, Double)
}
struct VideoModelInfo: Codable, Equatable {
    var visionModel: String; var embeddingModel: String; var embeddingReady: Bool
}
struct VideoRecording: Codable, Identifiable, Equatable {
    var id: String; var cameraId: String; var title: String; var recordedAt: Double?; var sourceType: String
    var timestampMeaning: String?
    var aspectRatio: Double?
    var status: String; var duration: Double?; var segmentCount: Int; var error: String?; var playbackUrl: String
    var stateLabel: String { ["queued":"等待索引", "indexing":"正在建立视频索引", "ready":"可检索", "failed":"索引未完成", "interrupted":"索引已中断", "stale":"需要重建索引"][status] ?? status }
}
struct VideoHit: Codable, Identifiable, Equatable {
    var id: String; var recordingId: String; var cameraId: String; var title: String; var playbackUrl: String
    var segmentStart: Double; var segmentEnd: Double; var seekSeconds: Double; var recordedAt: Double?
    var sourceType: String; var verdict: String; var summary: String; var limitation: String
    var verificationStatus: String?
    var verdictLabel: String { if verificationStatus == "failed" { return "视频复核失败 · 可重试" }; return ["matched":"模型判断匹配 · 请核验", "not_matched":"模型未发现所问动作", "uncertain":"候选片段 · 无法确认"][verdict] ?? "待核验" }
}
func videoTime(_ seconds: Double) -> String {
    let t = max(0, Int(seconds)); return String(format: "%02d:%02d", t / 60, t % 60)
}
func displayTime(_ timestamp: Double?) -> String {
    guard let timestamp, timestamp > 0 else { return "暂无观察" }
    return Date(timeIntervalSince1970: timestamp).formatted(date: .abbreviated, time: .standard)
}

struct RunProgress: Decodable { var completed: Int?; var total: Int? }
struct HistoryFilter: Codable, Equatable {
    var period: String
    var startAt: Double? = nil
    var endAt: Double? = nil
    var label: String {
        if period == "custom", let startAt, let endAt {
            let a = Date(timeIntervalSince1970: startAt).formatted(date: .numeric, time: .shortened)
            let b = Date(timeIntervalSince1970: endAt).formatted(date: .numeric, time: .shortened)
            return "\(a) – \(b)"
        }
        return ["all":"全部日期", "today":"今天", "yesterday":"昨天", "last_24_hours":"过去 24 小时"][period] ?? "按问题判断"
    }
}

struct ReplayConfig: Codable, Equatable { var recordingId: String }
struct ReplayState: Codable, Equatable { var cursor: Double?; var modelCalls: Int?; var online: Bool? }

struct SkillContract: Codable, Equatable {
    var precondition: String; var trigger: String; var temporal: String; var unknown: String; var evidence: String; var completion: String
}
struct SkillCapability: Codable, Equatable {
    var status: String; var label: String; var canActivate: Bool; var canTrial: Bool
    var blockers: [String]; var warnings: [String]; var contract: SkillContract?
}
struct TrialObservation: Codable, Equatable {
    var start: Double; var end: Double; var baseline: Bool; var verdict: String; var eventTime: Double?; var summary: String
    var label: String { baseline ? (verdict == "matched" ? "基线已建立" : "基线无法确认") : verdict == "matched" ? "发现候选" : verdict == "uncertain" ? "无法确认" : "未见触发" }
}
struct SkillTrial: Codable, Identifiable, Equatable {
    var id: String; var skillId: String; var revision: Int; var status: String; var summary: String
    var sourceRecordingId: String?
    var expectedOutcome: String?; var acceptancePassed: Bool?
    var stale: Bool; var canConfirm: Bool; var baselineEstablished: Bool; var failureCount: Int; var wouldAlert: Bool
    var eventTime: Double?; var clipStart: Double?; var clipEnd: Double?; var videoUrl: String?; var elapsedSeconds: Double?
    var observations: [TrialObservation]; var limitations: [String]; var contract: SkillContract
    var running: Bool { status == "queued" || status == "running" }
    var label: String { stale ? "报告已过期" : ["queued":"等待试跑", "running":"试跑中", "completed":"试跑结束", "failed":"试跑失败", "cancelled":"已取消", "interrupted":"已中断", "stale":"报告已过期"][status] ?? status }
}

struct DeploymentCamera: Codable, Identifiable { var id: String; var name: String; var position: String; var candidateUse: String; var verdict: String; var reason: String }
struct PreparationAction: Codable, Identifiable { var id: String; var instruction: String; var completed: Bool }
struct DeploymentPlan: Codable {
    var status: String; var canPublish: Bool; var summary: String; var cameras: [DeploymentCamera]
    var actions: [PreparationAction]; var blockers: [String]; var sampleIntervalSeconds: Int; var confirmationSeconds: Int; var note: String
}


struct PersonalPreferences: Codable, Equatable {
    var enabled = false
    var dailySummary = false
    var summaryHour = 18
    var quietStart = 22
    var quietEnd = 8
    var timezone = TimeZone.current.identifier
}
struct PersonalMemory: Codable, Identifiable, Equatable {
    var id: String; var content: String; var source: String; var createdAt: Double; var expiresAt: Double?
}
struct PersonalNotice: Codable, Identifiable, Equatable {
    var id: String; var kind: String; var title: String; var body: String
    var createdAt: Double; var read: Bool; var skillId: String?
    var kindLabel: String { ["event":"事件触发", "schedule":"定时概况", "followup":"后续提醒"][kind] ?? "助手提醒" }
}
struct PersonalSnapshot: Codable, Equatable {
    var preferences: PersonalPreferences; var revision: Int
    var memories: [PersonalMemory]; var inbox: [PersonalNotice]; var delivery: String; var lastError: String?
}
