import Foundation

enum HardwareValue: Codable, Equatable, Sendable {
    case object([String: HardwareValue]), array([HardwareValue]), string(String), number(Double), bool(Bool), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([String: HardwareValue].self) { self = .object(v) }
        else { self = .array(try c.decode([HardwareValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    subscript(_ key: String) -> HardwareValue { object[key] ?? .null }
    var object: [String: HardwareValue] { if case .object(let v) = self { return v }; return [:] }
    var array: [HardwareValue] { if case .array(let v) = self { return v }; return [] }
    var string: String { if case .string(let v) = self { return v }; return "" }
    var boolean: Bool { if case .bool(let v) = self { return v }; return false }
    var json: String { let e=JSONEncoder(); e.outputFormatting=[.prettyPrinted,.sortedKeys]; return (try? String(data:e.encode(self),encoding:.utf8)) ?? "{}" }
    static func parse(_ json: String) throws -> HardwareValue { try JSONDecoder().decode(Self.self,from:Data(json.utf8)) }
}

enum AssistantIdentity {
    static let name = "anker"
}

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
    var connectionLabel: String { connection == "event_only" ? "事件已接入" : fresh ? "画面可用" : connection == "offline" ? "设备离线" : "等待新画面" }
}
struct EvidenceItem: Codable, Identifiable, Equatable {
    var id: String; var skillId: String; var cameraId: String; var capturedAt: Double; var relation: String
    var reason: String; var imageUrl: String?; var revision: Int; var sourceType: String
    var recordingId: String?; var clipStart: Double?; var clipEnd: Double?; var seekSeconds: Double?; var originalEventTime: Double?; var videoUrl: String?
    var deviceName: String?; var detectionType: String?; var reviewStatus: String?
    var title: String { if sourceType == "synthetic_demo" { return "合成测试 · 画面核验" }; if sourceType == "official_sdk" { return "摄像头事件" }; if sourceType == "replay" { return "回放测试 · 区域状态提醒" }; return ["inside":"目标在区域内", "outside":"目标在区域外", "unknown":"无法确认目标位置"][relation] ?? "观察记录" }
    var exportText: String { "EvidenceGuard 观察记录\n\(title)\n\(reason)\n\(["replay", "synthetic_demo"].contains(sourceType) ? "记录生成时间（非原录像拍摄时间）" : "采集时间")：\(displayTime(capturedAt))\n设备：\(cameraId)\n任务：\(skillId) · 规则版本 \(revision)\n来源：\(sourceType)\n证据 ID：\(id)" }
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
    var cameraEvents: SDKEventTimeline?
    static let empty = Bootstrap(now: 0, summary: .init(activeSkills: 0, openAlerts: 0, unknownSkills: 0), skills: [], cameras: [], evidence: [], agent: .init(provider: "待连接", mode: "", ready: false, tools: []), integration: .init(lab: "", officialSdk: "已收到，待真机验证", physicalDevicesValidated: false))
}
struct SDKEventTimeline: Codable, Equatable {
    var events: [SDKEventRecord]; var truncated: Bool; var continuousCoverage: Bool
}
struct SDKEventRecord: Codable, Identifiable, Equatable {
    var id: String; var cameraId: String; var deviceName: String
    var startMs: Int64; var endMs: Int64; var detectionType: String
    var hasVideo: Bool; var imageUrl: String?; var reviewStatus: String; var reason: String; var sourceType: String
    var date: Date { Date(timeIntervalSince1970: Double(startMs) / 1_000) }
    var label: String { ["human":"人物活动", "motion":"画面活动", "package_put":"包裹放置", "package_take":"包裹取走", "vehicle":"车辆活动", "pet":"宠物活动", "ring":"门铃响起"][detectionType] ?? "设备事件" }
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
struct ConversationSummary: Codable, Identifiable, Equatable {
    var id: String; var kind: String; var title: String; var preview: String
    var createdAt: Double; var updatedAt: Double; var unreadCount: Int
    var hasActiveRun: Bool; var lastMode: String
}
// Durable request identity survives a lost HTTP response or an App restart.
struct PendingChatRequest: Codable {
    var id: String; var message: String; var conversation: String
    var skill: String?; var camera: String?; var mode: String
    var filter: HistoryFilter?; var replyID: String?
    func matches(message: String, camera: String?, mode: String, filter: HistoryFilter?, replyID: String?) -> Bool {
        self.message == message && self.camera == camera && self.mode == mode && self.filter == filter && self.replyID == replyID
    }
}
struct LocalChatState: Codable {
    var drafts: [String: String] = [:]
    var pending: [String: PendingChatRequest] = [:]
    var modes: [String: String] = [:]
    var newConversationRequestID: String?
}
struct AgentRun: Codable, Identifiable, Equatable {
    var id: String; var conversationId: String; var skillId: String?; var message: String; var status: String; var createdAt: Double
    var text: String?; var error: String?; var draft: VisualSkill?; var toolReceipts: [ToolReceipt]
    var captures: [CameraCapture]?
    var hardwareOperations: [HardwareValue]?
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
enum AppTab: Int, CaseIterable {
    case assistant, cameraSkills, tasks, memory, profile
}

enum AppRoute: Hashable {
    case connectedApps, cameraObservation
    case pushDelivery(String, String)
    case pushConversation(String, String?, String)
    case demoScene
    case skill(String), evidence(String), evidenceList(String?), cameras, camera(String), alerts
    case conversation(String, String?), settings, officialSDK, cameraEvents, notificationSettings, voiceSettings, privacy, help, profile
    case addDevice, personalAgent, personalInbox, account
    case recordings, video(String, Double), replayVideo(String, Double)
    case evidenceConversation(String)
}

struct PushTap: Identifiable, Codable, Equatable {
    var id: String
    var scope: String
}

enum PushNavigation {
    // Retain a tap while the vendor workspace releases or a sheet owns the UI.
    // Consume only after product navigation is ready, preserving other tab paths.
    @discardableResult static func consume(_ pending: inout PushTap?, selection: inout AppTab,
                                           paths: inout [[AppRoute]], productVisible: Bool,
                                           presentationBlocked: Bool) -> Bool {
        guard productVisible, !presentationBlocked, let tap = pending,
              paths.indices.contains(AppTab.assistant.rawValue) else { return false }
        selection = .assistant
        paths[AppTab.assistant.rawValue].append(.pushDelivery(tap.id, tap.scope))
        pending = nil
        return true
    }
}
struct DemoSceneSnapshot: Decodable { var enabled: Bool; var scenes: [DemoScene] }
struct DemoScene: Decodable, Identifiable {
    var id: String; var title: String; var status: String; var reason: String
    var createdAt: Double; var samples: [DemoSceneSample]
    var policyStatus: String?; var policyReason: String?; var valueScore: Int?; var messageId: String?; var assistantDraft: String?
    var isRunning: Bool { status == "pending" || status == "running" }
    var label: String { ["pending":"等待核验", "running":"视觉核验中", "completed":"视觉核验完成", "unavailable":"核验未完成", "budget_exhausted":"核验额度已用完"][status] ?? status }
    var deliveryLabel: String { ["pending":"等待评估", "running":"正在评估", "retry":"等待重试", "deferred":"按偏好延后", "digest":"保留至已订阅的每日汇总", "sent":"已进入助手对话", "merged":"已合并同类提醒", "summarized":"已纳入汇总", "silent":"无需打扰", "cancelled":"已取消", "expired":"已过提醒时效", "failed":"评估未完成"][policyStatus ?? ""] ?? "尚未安排提醒" }
}
struct DemoSceneSample: Decodable, Identifiable { var id: String; var imageUrl: String; var relativeSeconds: Int }
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
    var morningReport = false
    var eveningReport = false
    var morningHour = 8
    var eveningHour = 20
    var supportsTwoReports = true
    var quietStart = 22
    var quietEnd = 8
    var timezone = TimeZone.current.identifier
    init() {}
    private enum CodingKeys: String, CodingKey {
        case enabled, dailySummary, summaryHour, morningReport, eveningReport, morningHour, eveningHour, quietStart, quietEnd, timezone
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        supportsTwoReports = c.contains(.morningReport) && c.contains(.eveningReport)
        enabled = try c.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
        dailySummary = try c.decodeIfPresent(Bool.self, forKey: .dailySummary) ?? false
        summaryHour = try c.decodeIfPresent(Int.self, forKey: .summaryHour) ?? 18
        morningReport = try c.decodeIfPresent(Bool.self, forKey: .morningReport) ?? false
        eveningReport = try c.decodeIfPresent(Bool.self, forKey: .eveningReport) ?? dailySummary
        morningHour = try c.decodeIfPresent(Int.self, forKey: .morningHour) ?? 8
        eveningHour = try c.decodeIfPresent(Int.self, forKey: .eveningHour) ?? summaryHour
        quietStart = try c.decodeIfPresent(Int.self, forKey: .quietStart) ?? 22
        quietEnd = try c.decodeIfPresent(Int.self, forKey: .quietEnd) ?? 8
        timezone = try c.decodeIfPresent(String.self, forKey: .timezone) ?? TimeZone.current.identifier
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(enabled, forKey: .enabled)
        try c.encode(dailySummary, forKey: .dailySummary)
        try c.encode(summaryHour, forKey: .summaryHour)
        try c.encode(quietStart, forKey: .quietStart)
        try c.encode(quietEnd, forKey: .quietEnd)
        try c.encode(timezone, forKey: .timezone)
        if supportsTwoReports {
            try c.encode(morningReport, forKey: .morningReport)
            try c.encode(eveningReport, forKey: .eveningReport)
            try c.encode(morningHour, forKey: .morningHour)
            try c.encode(eveningHour, forKey: .eveningHour)
        }
    }
    var reportScheduleLabel: String {
        var parts: [String] = []
        if morningReport { parts.append(String(format: "早安 %02d:00", morningHour)) }
        if eveningReport { parts.append(String(format: "晚间 %02d:00", eveningHour)) }
        return parts.isEmpty ? "尚未开启" : parts.joined(separator: " · ")
    }
}
struct PersonalMemory: Codable, Identifiable, Equatable {
    var id: String; var content: String; var source: String; var createdAt: Double; var expiresAt: Double?
    var sourceQuote: String?
    var updatedAt: Double?
}
struct AutomaticMemoryStatus: Codable, Equatable {
    var enabled: Bool; var pending: Int; var status: String; var reason: String
}
struct PersonalNotice: Codable, Identifiable, Equatable {
    var id: String; var kind: String; var title: String; var body: String
    var createdAt: Double; var read: Bool; var skillId: String?
    var kindLabel: String { ["event":"事件触发", "schedule":"定时概况", "followup":"后续提醒"][kind] ?? "助手提醒" }
}
struct PersonalSnapshot: Codable, Equatable {
    var preferences: PersonalPreferences; var revision: Int
    var memories: [PersonalMemory]; var inbox: [PersonalNotice]; var delivery: String; var lastError: String?
    var messages: [AssistantMessage]?
    var activity: [ProactiveActivity]?
    var automaticMemory: AutomaticMemoryStatus?
}

struct ProactiveSource: Codable, Identifiable, Equatable {
    var id: String; var type: String
    var name: String?; var title: String?; var reason: String?; var limitation: String?
    var observedAt: Double?; var skillId: String?; var evidenceId: String?; var sourceType: String?
}
struct AssistantMessage: Codable, Identifiable, Equatable {
    var id: String; var title: String; var body: String; var why: String
    var createdAt: Double; var read: Bool; var feedback: String?; var skillId: String?
    var sources: [ProactiveSource]
}
struct ProactiveActivity: Codable, Identifiable, Equatable {
    var id: String; var status: String; var kind: String; var reason: String; var createdAt: Double
    var statusLabel: String { ["pending":"等待检查", "running":"正在检查", "retry":"等待重试", "deferred":"稍后检查", "sent":"已发消息", "merged":"已合并同类事件", "digest":"等待每日汇总", "summarized":"已纳入汇总", "silent":"保持安静", "cancelled":"已取消", "expired":"已过期", "failed":"检查未完成"][status] ?? status }
}
