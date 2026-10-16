import Foundation

enum CameraQuestion {
    static func needsLiveFrame(_ message: String) -> Bool {
        let text = message.lowercased()
        if ["录像", "回放", "昨天", "历史", "提醒我", "通知我", "不要看", "不用看"].contains(where: text.contains) { return false }
        return ["画面", "看一眼", "看一下摄像头", "看看摄像头", "现在门口", "快递到没到", "live", "snapshot"].contains(where: text.contains)
    }
}

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

// Presentation only. Raw requests and receipts remain intact for diagnostics.
enum ChatPresentation {
    static let actions = [
        "devices_list":"查看摄像头列表", "device_inspect":"查看摄像头能力", "camera_observe":"查看摄像头新画面",
        "camera_events_query":"查看摄像头事件", "camera_ptz_step":"移动摄像头", "camera_goto_preset":"转到选定位置",
        "camera_set_night_vision":"调整夜视模式", "doorbell_light_set":"调整门铃灯光", "doorbell_reply_play":"播放门铃回复",
        "camera_record_clip":"录制一段视频", "operation_get":"查看操作进度", "camera_stop":"停止摄像头操作",
        "device_state_get":"查看设备状态", "device_settings_get":"查看摄像头设置", "device_settings_set":"调整摄像头设置",
        "camera_events_subscribe":"关注新的摄像头事件", "camera_events_unsubscribe":"停止关注摄像头事件",
        "camera_event_get":"查看事件详情", "camera_evidence_get":"查看事件资料", "camera_evidence_download":"保存事件资料",
        "camera_presets_list":"查看摄像头预置位置", "doorbell_replies_list":"查看门铃回复选项", "camera_talk_start":"开启对讲",
        "camera_talk_stop":"结束对讲", "camera_light_set":"调整摄像头灯光", "camera_dual_mode_set":"调整双摄画面",
        "camera_ptz_mode_set":"调整摄像头跟踪模式", "camera_panorama_generate":"生成全景画面", "operation_cancel":"取消操作",
        "list_camera_capabilities":"查看摄像头能力", "request_camera_snapshot":"查看摄像头新画面", "list_tasks":"查看任务",
        "save_personal_task":"保存你交代的事项",
        "get_task_state":"查看任务进度", "search_evidence":"查找事件资料", "read_stored_image":"查看已保存的图片",
        "search_recordings":"查找并核对录像", "draft_visual_skill":"整理守护草案", "list_skill_capabilities":"查看可用守护能力",
        "list_camera_events":"查看摄像头事件", "request_recheck":"重新查看现场", "read_home_report":"整理家庭报告",
        "read_proactive_context":"核对已有记录", "read_observation_image":"查看观察图片",
        "gmail_search":"查找邮件", "gmail_read":"读取邮件", "lark_chats":"查看会话列表", "lark_messages":"读取会话消息",
        "read_phone_context":"查看已共享的手机信息"
    ]
    static let controls: Set<String> = ["camera_ptz_step", "camera_goto_preset", "camera_set_night_vision", "doorbell_light_set", "doorbell_reply_play", "camera_record_clip", "device_settings_set", "camera_events_subscribe", "camera_events_unsubscribe", "camera_talk_start", "camera_talk_stop", "camera_light_set", "camera_dual_mode_set", "camera_ptz_mode_set", "camera_panorama_generate", "camera_stop", "operation_cancel"]
    static func action(_ tool: String) -> String { actions[tool] ?? "处理请求" }
    static func progress(_ tool: String) -> String { (controls.contains(tool) ? "正在准备" : "正在") + action(tool) }
    static func receipt(_ tool: String, _ status: String) -> String {
        let state = ["completed":"已收到处理结果", "failed":"未完成", "unavailable":"暂不可用", "unsupported":"暂不支持", "awaitingApproval":"等待你确认", "queued":"正在等待设备", "executing":"正在执行", "verifying":"正在核对结果", "unknown":"结果尚未确认", "cancelled":"已取消"][status] ?? "状态待确认"
        return action(tool) + " · " + state
    }
    static func operationStatus(_ operation: HardwareValue) -> String {
        let action = action(operation["tool"].string)
        switch operation["executionState"].string {
        case "awaitingApproval": return "等待你确认，确认后才会" + action
        case "queued": return "正在等待设备响应，尚未开始" + action
        case "executing": return "正在" + action
        case "verifying": return "正在确认设备是否已停止，请稍候"
        case "completed": return "已收到设备处理回执，实际效果仍需核对"
        case "failed": return "这次操作未完成，请检查设备连接后重试"
        case "cancelled": return "这次操作已取消"
        default: return "操作结果尚未确认，请先核对设备状态"
        }
    }
    static func operationDetails(_ operation: HardwareValue, deviceName: String?, references: [HardwareValue] = []) -> String {
        let args = operation["arguments"], tool = operation["tool"].string
        var parts = ["设备：" + text(deviceName ?? "所选摄像头", fallback: "所选摄像头")]
        if let direction = ["LEFT":"向左", "RIGHT":"向右", "UP":"向上", "DOWN":"向下"][args["direction"].string] { parts.append("方向：" + direction + "移动一步") }
        if case .number(let seconds) = args["duration"], seconds.isFinite, (1...300).contains(seconds) { parts.append("持续 \(Int(seconds)) 秒") }
        if ["camera_light_set", "doorbell_light_set"].contains(tool), case .bool(let enabled) = args["enabled"] { parts.append(enabled ? "开启灯光" : "关闭灯光") }
        if tool == "device_settings_set" {
            let field = ["ptzSpeed":"转动速度", "microphoneEnabled":"麦克风", "audioRecordEnabled":"录像声音", "statusLED":"状态指示灯"][args["field"].string] ?? "所选设置"
            if case .bool(let enabled) = args["value"] { parts.append(field + "：" + (enabled ? "开启" : "关闭")) }
            else if case .number(let number) = args["value"], number.isFinite { parts.append(field + "：\(number)") }
            else { parts.append("调整" + field + "，请先核对所选选项") }
        }
        if tool == "camera_record_clip", let policy = ["required":"需要录入声音", "forbidden":"不录入声音", "allowIfPresent":"设备有音轨时一并录入"][args["audioPolicy"].string] { parts.append(policy) }
        for (key, label) in [("presetRef", "位置"), ("optionRef", "选项"), ("modeRef", "模式"), ("replyRef", "门铃回复"), ("channelRef", "灯光")] {
            let id = args[key].string
            if !id.isEmpty {
                let name = references.first(where: { $0["id"].string == id })?["label"].string ?? ""
                parts.append(label + "：" + text(name, fallback: "已选择，名称暂未同步"))
            }
        }
        if args["scope"].string == "persistent" { parts.append("该设置会持续生效") }
        return parts.joined(separator: " · ")
    }
    static func error(_ raw: String) -> String {
        let value = raw.lowercased()
        if value.contains("输入已保留") || value.contains("内容已保留") || value.contains("内容已保存") { return "这次发送未完成，输入已保留，请重试。" }
        if value.contains("timeout") || value.contains("timed out") || value.contains("超时") { return "等待响应超时，请稍后重试。" }
        if value.contains("offline") || value.contains("离线") { return "设备暂时离线，请检查连接后重试。" }
        if value.contains("unauthorized") || value.contains("401") { return "连接凭证已失效，请到设置重新连接。" }
        return "这次处理未完成，请检查连接后重试。"
    }
    static func text(_ raw: String, fallback: String = "处理信息已记录，请查看相关状态。") -> String {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return fallback }
        // Decode a stringified natural-language answer, never expose structured payloads.
        if let data = value.data(using: .utf8), let decoded = try? JSONSerialization.jsonObject(with: data, options: .fragmentsAllowed) {
            if let prose = decoded as? String, prose != value { return text(prose, fallback: fallback) }
            if let object = decoded as? [String: Any] {
                for key in ["text", "content", "body"] { if let prose = object[key] as? String { return text(prose, fallback: fallback) } }
            }
            return fallback
        }
        var output = value.replacingOccurrences(of: #"(?s)```.*?(?:```|$)"#, with: "", options: .regularExpression)
        output = output.replacingOccurrences(of: #"(?s)<(?:tool_call|function_call|analysis)>.*?(?:</(?:tool_call|function_call|analysis)>|$)"#, with: "", options: .regularExpression)
        // Hide technical lines in mixed prose too, including unfinished streamed payloads.
        output = output.components(separatedBy: .newlines).filter { line in
            let clean = line.trimmingCharacters(in: .whitespaces)
            return clean.range(of: #"[{}]|^[\[\]]|^[A-Za-z_][A-Za-z0-9_.]*\s*=|^[\"\'].*[\"\'],?$|^[\"'][A-Za-z_][A-Za-z0-9_]*[\"']\s*:|^(?:import\s|from\s|def\s|class\s|function\s|const\s|let\s|var\s|return\b|console\.|Traceback|File\s+\"|raise\s|Exception|Error:|HTTP/|curl\s)|=>|\\u[0-9a-fA-F]{4}|<\|[^>]+\|>|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\([^\n]*\)|(?<![A-Za-z0-9_])(?:requestHash|executionState|tool_calls|tool_call_id|executorPlatform|deviceId|operationId)\s*[=:]"#, options: .regularExpression) == nil
        }.joined(separator: "\n")
        for (tool, label) in actions.sorted(by: { $0.key.count > $1.key.count }) {
            output = output.replacingOccurrences(of: "(?<![A-Za-z0-9_])" + NSRegularExpression.escapedPattern(for: tool) + "(?![A-Za-z0-9_])", with: label, options: .regularExpression)
        }
        output = output.replacingOccurrences(of: #"`[^`]*`"#, with: "", options: .regularExpression)
        output = output.replacingOccurrences(of: #"(?<![A-Za-z0-9_])(?:(?:sdk|run|op|executor|proactive)-[A-Za-z0-9-]+|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[a-z][a-z0-9]*(?:_[a-z0-9]+)+|[0-9a-fA-F]{32,}|requestHash|executionState|executorPlatform|operationId|deviceId)(?![A-Za-z0-9_])(?:\([^\n)]*\))?"#, with: "相关记录", options: .regularExpression)
        output = output.trimmingCharacters(in: .whitespacesAndNewlines)
        return output.isEmpty ? fallback : output
    }
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
    var sampledAt: Double? = nil; var timestampMeaning: String? = nil
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
    var referenceImageID: String? = nil
    func matches(message: String, camera: String?, mode: String, filter: HistoryFilter?, replyID: String?, referenceImageID: String? = nil) -> Bool {
        self.message == message && self.camera == camera && self.mode == mode && self.filter == filter && self.replyID == replyID && self.referenceImageID == referenceImageID
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
    var completedAt: Double?
    var referenceImageId: String?
    var isRunning: Bool { status == "queued" || status == "running" }
}

enum ChatTimelineItem: Identifiable {
    case user(AgentRun), reply(AgentRun), proactive(AssistantMessage)
    var id: String {
        switch self {
        case .user(let run): return "0-user:" + run.id
        case .reply(let run): return "1-reply:" + run.id
        case .proactive(let message): return "2-message:" + message.id
        }
    }
    var createdAt: Double {
        switch self {
        case .user(let run): return run.createdAt
        case .reply(let run): return run.completedAt ?? run.createdAt
        case .proactive(let message): return message.createdAt
        }
    }
    static func items(runs: [AgentRun], messages: [AssistantMessage]) -> [Self] {
        var unique: [String: Self] = [:]
        for run in runs {
            for item in [Self.user(run), .reply(run)] { unique[item.id] = item }
        }
        for message in messages { let item = Self.proactive(message); unique[item.id] = item }
        return unique.values.sorted { ($0.createdAt, $0.id) < ($1.createdAt, $1.id) }
    }
    static func messageID(_ id: String) -> String { "2-message:" + id }
}
struct RunEvent: Decodable, Identifiable {
    var runId: String; var sequence: Int; var type: String; var at: Double?
    var payload: RunProgress?
    var progressLabel: String {
        if type == "tool_started" { return ChatPresentation.progress(payload?.tool ?? "") }
        if type == "tool_completed" { return "已处理" + ChatPresentation.action(payload?.tool ?? "") + "的请求，正在整理结果" }
        if type == "tool_failed" { return ChatPresentation.action(payload?.tool ?? "") + "未完成，正在核对原因" }
        if type == "video_verification_progress", let done = payload?.completed, let total = payload?.total { return "已复核 \(done)/\(total) 段录像" }
        return ["video_search_started":"正在筛选已存录像", "video_search_empty":"所选范围暂无可检索录像", "video_embedding_started":"正在检索相关片段", "video_candidates_found":"已找到候选，等待视频复核", "video_verification_started":"正在观看候选录像", "video_search_completed":"视频复核完成，正在整理证据"][type] ?? label
    }
    var id: String { "\(runId)-\(sequence)" }
    var label: String { ["timing_review_required":"检测已升级为按秒抽样，需重新验收", "trial_reviewed":"已核验试跑报告", "capability_checked":"已检查任务执行能力", "replay_acknowledged":"已标记核验，证据保留", "camera_requested":"已请求新画面", "camera_completed":"已取得新画面", "camera_failed":"画面请求未完成", "recheck_requested":"已请求复核", "alert_opened":"触发提醒", "alert_resolved":"新证据确认恢复", "observation_recovered":"恢复观察，等待新画面", "result_changed":"观察结果更新", "skill_confirmed":"用户已确认启用", "skill_revised":"草案已更新", "skill_drafted":"已生成草案", "lifecycle_changed":"任务状态已变更", "skill_completed":"一次性任务已完成", "replay_observing":"正在分析已到达的回放片段", "replay_model_completed":"回放模型观察完成", "replay_model_failed":"回放模型复核失败", "replay_input_failed":"回放输入失败，已暂停", "replay_finished":"回放测试结束", "replay_interrupted":"回放中断，等待恢复", "replay_transport_changed":"回放输入连接已变化", "run_queued":"请求已排队", "run_started":"开始理解需求", "model_started":"AI 正在处理", "tool_started":"正在查询或生成草案", "tool_completed":"操作已完成", "tool_failed":"操作未完成", "frame_attached":"已附上所选摄像头画面", "frame_unavailable":"本次未取得画面", "response_completed":"回复已完成", "run_failed":"本次请求未完成", "run_cancelled":"已取消"][type] ?? "正在处理请求" }
}
enum AppTab: Int, CaseIterable {
    case assistant, cameraSkills, tasks, memory, profile
}

enum AppRoute: Hashable {
    case connectedApps, cameraObservation
    case pushDelivery(String, String)
    case liveCamera(String)
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
    var retrievalVersion: Int?
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
    var thumbnailUrl: String?
    var verdictLabel: String { if verificationStatus == "failed" { return "视频复核失败 · 可重试" }; if verificationStatus == "verifying" { return "正在核对原录像" }; return ["candidate":"相关候选 · 尚未核验", "verification_failed":"复核失败 · 可重试", "matched":"模型判断匹配 · 请核验", "not_matched":"模型未发现所问动作", "uncertain":"候选片段 · 无法确认"][verdict] ?? "待核验" }
}

struct VideoSearchInput: Codable, Equatable {
    var text: String?
    var image_ref: String?
    var camera_ids: [String]
    var time_range: HistoryFilter
    var timezone: String = TimeZone.current.identifier
    var limit = 10
    var verify_limit = 3
}
struct VideoSearchScope: Decodable {
    var cameraIds: [String]
    var period: String
    var startAt: Double?
    var endAt: Double?
    var timezone: String
    var coverage: String
}
struct VideoSearchResult: Decodable, Identifiable {
    var id: String
    var status: String
    var query: VideoSearchInput
    var scope: VideoSearchScope
    var videos: [VideoHit]
    var reason: String
    var candidateCount: Int
    var verifiedCount: Int
    var indexChanged: Bool
    var removedCandidates: Int
    var isRunning: Bool { status == "searching" || status == "verifying" }
    var stateLabel: String {
        ["searching":"正在检索相关片段", "verifying":"找到相关片段，正在核对", "completed":"本次检索已完成",
         "no_recordings":"还没有导入录像", "no_indexed_recordings":"当前范围没有可检索录像",
         "no_candidates":"没有找到可用候选", "failed":"检索未完成", "interrupted":"检索已中断"][status] ?? "检索状态更新中"
    }
}
struct VideoSearchImage: Decodable { var id: String; var image_ref: String; var url: String }
func videoTime(_ seconds: Double) -> String {
    let t = max(0, Int(seconds)); return String(format: "%02d:%02d", t / 60, t % 60)
}
func displayTime(_ timestamp: Double?) -> String {
    guard let timestamp, timestamp > 0 else { return "暂无观察" }
    return Date(timeIntervalSince1970: timestamp).formatted(date: .abbreviated, time: .standard)
}

struct RunProgress: Decodable { var completed: Int?; var total: Int?; var tool: String? }
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
    var tasks: [PersonalTask]?
}

struct PersonalTask: Codable, Equatable, Identifiable {
    var id: String; var title: String; var instruction: String; var conversationId: String
    var status: String; var reason: String; var createdAt: Double; var expiresAt: Double?
    var cameraId: String?; var eventType: String?
    var statusLabel: String { ["waiting_events":"等待新事件", "needs_setup":"待配置", "expired":"已到期", "cancelled":"已结束"][status] ?? "待确认" }
    var isOpen: Bool { status == "waiting_events" || status == "needs_setup" }
}

struct ProactiveSource: Codable, Identifiable, Equatable {
    var id: String; var type: String
    var name: String?; var title: String?; var reason: String?; var limitation: String?
    var observedAt: Double?; var skillId: String?; var evidenceId: String?; var sourceType: String?
    var cameraId: String?; var imageUrl: String?
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
