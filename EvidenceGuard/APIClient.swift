import Foundation
import Security

enum ServiceAccess {
    private static func query(_ url: URL) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "com.evidenceguard.cloud-access",
         kSecAttrAccount as String: "\(url.scheme ?? "")://\(url.host ?? ""):\(url.port ?? (url.scheme == "https" ? 443 : 80))"]
    }
    static func token(for url: URL) -> String {
        if let token = MobileServiceConfiguration.current.demoToken(for: url) { return token }
        var q = query(url); q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }
    static func save(_ token: String, for url: URL) throws {
        let q = query(url)
        let status: OSStatus
        if token.isEmpty {
            status = SecItemDelete(q as CFDictionary)
        } else {
            let attributes: [String: Any] = [kSecValueData as String: Data(token.utf8), kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
            let update = SecItemUpdate(q as CFDictionary, attributes as CFDictionary)
            status = update == errSecItemNotFound ? SecItemAdd(q.merging(attributes) { _, new in new } as CFDictionary, nil) : update
        }
        guard status == errSecSuccess || (token.isEmpty && status == errSecItemNotFound) else { throw APIProblem(message: "无法保存团队访问令牌，请解锁手机后重试。") }
        for cookie in HTTPCookieStorage.shared.cookies(for: url.appendingPathComponent("api")) ?? [] where cookie.name == "eg_media" {
            HTTPCookieStorage.shared.deleteCookie(cookie)
        }
    }
}

private struct ConflictBody: Decodable { var conflicts: [CameraOccupancy] }
struct APIProblem: LocalizedError {
    let message: String
    var conflicts: [CameraOccupancy] = []
    var statusCode: Int? = nil
    var errorDescription: String? { message }
}
private struct TrialRequestBody: Encodable { var revision: Int; var expectedOutcome: String }
private struct PreparationRequestBody: Encodable { var revision: Int; var action: String; var completed: Bool }
struct APIClient {
    static var defaultBaseURL: URL {
        if let url = MobileServiceConfiguration.current.origin { return url }
        #if DEBUG
        return URL(string: "http://127.0.0.1:8790")!
        #else
        return URL(string: "https://unconfigured.invalid")!
        #endif
    }
    var baseURL: URL
    private let transport: URLSession
    private let observations: OpsDelivery
    private var pinnedAccessToken: String?
    var accessToken: String { pinnedAccessToken ?? ServiceAccess.token(for: baseURL) }
    func scoped() -> APIClient { var copy = self; copy.pinnedAccessToken = accessToken; return copy }
    init(baseURL: URL = APIClient.defaultBaseURL, transport: URLSession = .shared, observations: OpsDelivery = .shared) {
        self.baseURL = baseURL; self.transport = transport; self.observations = observations
    }
    func connectedApps() async throws -> [ConnectedApp] { try await get("/api/connectors") }
    func authorizeConnector(_ provider: String) async throws -> ConnectorAuthorization { try await send("/api/connectors/\(provider)/authorize", body: [String:String]()) }
    func completeConnector(_ provider: String, state: String, code: String) async throws -> [ConnectedApp] { try await send("/api/connectors/\(provider)/complete", body: ["state": state, "code": code]) }
    func disconnectConnector(_ provider: String) async throws -> [ConnectedApp] { try await send("/api/connectors/\(provider)", method: "DELETE", body: Optional<String>.none) }
    func sharePhone(_ items: [SharedPhoneItem], truncated: Bool) async throws {
        struct Result: Decodable { var status: String }
        let _: Result = try await send("/api/phone-context", body: SharedPhoneContext(items: items, truncated: truncated))
    }
    func removePhoneContext() async throws {
        struct Result: Decodable { var status: String }
        let _: Result = try await send("/api/phone-context", method: "DELETE", body: Optional<String>.none)
    }
    func cameraObservations() async throws -> [CameraObservation] { try await get("/api/camera-observation") }
    func saveObservation(_ id: String, enabled: Bool, interval: Int) async throws -> [CameraObservation] {
        struct Options: Encodable { var enabled: Bool; var intervalSeconds: Int }
        return try await send("/api/camera-observation/\(id)", method: "PUT", body: Options(enabled: enabled, intervalSeconds: interval))
    }
    func pushStatus() async throws -> PushStatus { try await send("/api/push/status", method: "GET", body: Optional<String>.none, push: true) }
    func registerPush(token: String) async throws -> PushStatus {
        let environment = Bundle.main.object(forInfoDictionaryKey: "EGAPNSEnvironment") as? String ?? ""
        guard ["development", "production"].contains(environment), let topic = Bundle.main.bundleIdentifier else { throw APIProblem(message: "此版本缺少通知配置，请更新 App。") }
        return try await send("/api/push/device", method: "PUT", body: ["token":token,"environment":environment,"topic":topic], push: true)
    }
    func disablePush() async throws -> PushStatus { try await send("/api/push/device", method: "DELETE", body: Optional<String>.none, push: true) }
    func pushPresence(active: Bool) async throws {
        struct Result: Decodable { var status: String }
        let _: Result = try await send("/api/push/presence", method: "PUT", body: ["active":active], push: true)
    }
    func testPush() async throws {
        struct Result: Decodable { var id: String }
        let _: Result = try await send("/api/push/test", body: [String:String](), push: true)
    }
    func openPush(_ id: String) async throws -> PushDestination {
        guard UUID(uuidString: id) != nil else { throw APIProblem(message: "通知无效") }
        return try await send("/api/push/deliveries/\(id)/open", body: [String:String](), push: true)
    }
    func ingestSDKEvents(_ events: [SDKCloudEvent], review: Bool) async throws -> SDKImportReceipt {
        struct Body: Encodable { var events: [SDKCloudEvent]; var reviewRequested: Bool }
        return try await send("/api/sdk/events", body: Body(events: events, reviewRequested: review))
    }
    func registerSDKDevices(_ cameras: [SDKDiscoveredCamera]) async throws {
        struct Device: Encodable { var deviceSn: String; var model: String; var deviceName: String }
        struct Body: Encodable { var devices: [Device] }
        struct Receipt: Decodable { var cameraIds: [String] }
        let _: Receipt = try await send("/api/sdk/devices", body: Body(devices: cameras.filter(\.isCompetitionCamera).map {
            Device(deviceSn: $0.sn, model: $0.model, deviceName: $0.name)
        }))
    }
    func capability(_ id: String) async throws -> SkillCapability { try await get("/api/skills/\(id)/capability") }
    func trials(_ id: String) async throws -> [SkillTrial] { try await get("/api/skills/\(id)/trials") }
    func trial(_ id: String) async throws -> SkillTrial { try await get("/api/skill-trials/\(id)") }
    func deployment(_ id: String) async throws -> DeploymentPlan { try await get("/api/skills/\(id)/deployment") }
    func prepareSite(_ id: String, revision: Int, action: String, completed: Bool) async throws -> DeploymentPlan { try await send("/api/skills/\(id)/deployment/preparation", body: PreparationRequestBody(revision: revision, action: action, completed: completed)) }
    func startTrial(_ skill: VisualSkill, expectedOutcome: String) async throws -> SkillTrial { try await send("/api/skills/\(skill.id)/trials", body: TrialRequestBody(revision: skill.revision, expectedOutcome: expectedOutcome)) }
    func cancelTrial(_ id: String) async throws -> SkillTrial { try await send("/api/skill-trials/\(id)/cancel", body: [String:String]()) }
    func trialRecording(_ id: String) async throws -> VideoRecording { try await get("/api/skill-trials/\(id)/recording") }
    func personalSettings() async throws -> PersonalSnapshot { try await get("/api/personal") }
    func memoryOptions(enabled: Bool) async throws -> PersonalSnapshot {
        try await send("/api/personal/memory-options?enabled=\(enabled)", method: "PUT", body: [String:String]())
    }
    func retryMemory() async throws -> PersonalSnapshot { try await send("/api/personal/memory-retry", body: [String:String]()) }
    func savePreferences(_ value: PersonalPreferences) async throws -> PersonalSnapshot { try await send("/api/personal/preferences", method: "PUT", body: value) }
    func remember(_ content: String, temporary: Bool) async throws -> PersonalSnapshot {
        struct Body: Encodable { var content: String; var temporary: Bool }
        return try await send("/api/personal/memories", body: Body(content: content, temporary: temporary))
    }
    func forget(_ id: String) async throws -> PersonalSnapshot { try await send("/api/personal/memories/\(id)", method: "DELETE", body: Optional<String>.none) }
    func readNotice(_ id: String) async throws -> PersonalSnapshot { try await send("/api/personal/inbox/\(id)/read", body: [String:String]()) }
    func bootstrap() async throws -> Bootstrap { try await get("/api/bootstrap") }
    func demoScenes() async throws -> DemoSceneSnapshot { try await get("/api/demo/scenes") }
    func startDemoScene(requestID: String, scenario: String) async throws -> DemoScene {
        try await send("/api/demo/scenes", body: ["requestId": requestID, "scenario": scenario])
    }
    func bindPersonalConversation(_ id: String) async throws {
        struct Result: Decodable { var status: String }
        let _: Result = try await send("/api/personal/conversation", method: "PUT", body: ["conversationId": id])
    }
    func messageFeedback(_ id: String, action: String) async throws -> PersonalSnapshot {
        try await send("/api/personal/messages/\(id)/feedback", body: ["action": action])
    }
    func assistantMessage(_ id: String) async throws -> AssistantMessage { try await get("/api/personal/messages/\(id)") }
    func conversation(_ id: String) async throws -> [AgentRun] { try await get("/api/agent/conversations/\(id)") }
    func conversations() async throws -> [ConversationSummary] { try await get("/api/agent/conversations") }
    func newConversation(requestID: String) async throws -> ConversationSummary {
        try await send("/api/agent/conversations", body: ["requestId": requestID])
    }
    func renameConversation(_ id: String, title: String) async throws -> ConversationSummary {
        try await send("/api/agent/conversations/\(id)", method: "PATCH", body: ["title": title])
    }
    func events(_ id: String) async throws -> [RunEvent] { try await get("/api/runs/\(id)/events") }
    func skillEvents(_ id: String) async throws -> [RunEvent] { try await get("/api/skills/\(id)/events") }
    func recording(_ id: String) async throws -> VideoRecording { try await get("/api/recordings/\(id)") }
    func replayRecording(_ id: String) async throws -> VideoRecording { try await get("/api/replay-evidence/\(id)") }
    func acknowledgeReplay(_ id: String) async throws -> VisualSkill { try await send("/api/skills/\(id)/replay-acknowledge", body: [String: String]()) }
    func replayTransport(_ id: String, online: Bool) async throws -> VisualSkill { try await send("/api/skills/\(id)/replay-transport", body: ["online": online]) }
    func indexRecording(_ id: String) async throws -> VideoRecording { try await send("/api/recordings/\(id)/index", body: [String: String]()) }
    func uploadRecording(_ file: URL, camera: String, recordedAt: Double?) async throws -> VideoRecording {
        let resource = file.startAccessingSecurityScopedResource()
        defer { if resource { file.stopAccessingSecurityScopedResource() } }
        let size = (try file.resourceValues(forKeys: [.fileSizeKey])).fileSize ?? 0
        guard size > 0 && size <= 150_000_000 else { throw APIProblem(message: "请选择不超过 150 MB 的录像") }
        var url = URLComponents(url: baseURL.appendingPathComponent("api/recordings"), resolvingAgainstBaseURL: true)!
        url.queryItems = [URLQueryItem(name: "cameraId", value: camera), URLQueryItem(name: "title", value: file.deletingPathExtension().lastPathComponent)]
        if let recordedAt { url.queryItems?.append(URLQueryItem(name: "recordedAt", value: String(recordedAt))) }
        var request = URLRequest(url: url.url!); request.httpMethod = "POST"; request.timeoutInterval = 120
        try authorize(&request)
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await transport.upload(for: request, fromFile: file)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw APIProblem(message: json?["detail"] as? String ?? "录像上传失败，请重试")
        }
        return try JSONDecoder().decode(VideoRecording.self, from: data)
    }
    func start(message: String, conversation: String, skill: String?, camera: String?, requestID: String, executionMode: String = "live", historyFilter: HistoryFilter? = nil, replyToMessageID: String? = nil) async throws -> AgentRun {
        struct Body: Encodable { var message: String; var conversationId: String; var requestId: String; var skillId: String?; var cameraId: String?; var executionMode: String; var historyFilter: HistoryFilter?; var replyToMessageId: String?; var clientPlatform = "ios" }
        return try await send("/api/agent/runs", body: Body(message: message, conversationId: conversation, requestId: requestID, skillId: skill, cameraId: camera, executionMode: executionMode, historyFilter: historyFilter, replyToMessageId: replyToMessageID), traceID: requestID)
    }
    func cancel(_ id: String) async throws -> AgentRun { try await send("/api/runs/\(id)/cancel", body: [String: String]()) }
    func createDraft(camera: String, conversation: String, prompt: String, replacesID: String?) async throws -> VisualSkill {
        struct Body: Encodable { var cameraId: String; var conversationId: String; var prompt: String; var replacesId: String? }
        return try await send("/api/skills/drafts", body: Body(cameraId: camera, conversationId: conversation, prompt: prompt, replacesId: replacesID))
    }
    func save(_ skill: VisualSkill) async throws -> VisualSkill {
        struct Edit: Encodable { var revision: Int; var name: String; var prompt: String; var target: SkillTarget; var regions: [String: ROI]; var devices: [String]; var rules: SkillRules; var replay: ReplayConfig? }
        return try await send("/api/skills/\(skill.id)", method: "PATCH", body: Edit(revision: skill.revision, name: skill.name, prompt: skill.prompt, target: skill.target, regions: skill.regions, devices: skill.devices, rules: skill.rules ?? SkillRules(), replay: skill.replay))
    }
    func confirm(_ skill: VisualSkill, fixture: Bool, replay: Bool = false, trialId: String? = nil, trialReviewed: Bool = false, switchFrom: [String: String] = [:]) async throws -> VisualSkill {
        struct Body: Encodable { var revision: Int; var fixtureAcknowledged: Bool; var replayAcknowledged: Bool; var trialId: String?; var trialReviewed: Bool; var switchFrom: [String: String] }
        return try await send("/api/skills/\(skill.id)/confirm", body: Body(revision: skill.revision, fixtureAcknowledged: fixture, replayAcknowledged: replay, trialId: trialId, trialReviewed: trialReviewed, switchFrom: switchFrom))
    }
    func lifecycle(_ id: String, action: String, switchFrom: [String: String] = [:]) async throws -> VisualSkill {
        struct Body: Encodable { var action: String; var switchFrom: [String: String] }
        return try await send("/api/skills/\(id)/lifecycle", body: Body(action: action, switchFrom: switchFrom))
    }
    func recheck(_ id: String, acknowledged: Bool) async throws -> VisualSkill { try await send("/api/skills/\(id)/recheck", body: ["acknowledged": acknowledged]) }
    func absoluteURL(_ path: String?) -> URL? {
        guard let path else { return nil }; return URL(string: path, relativeTo: baseURL)?.absoluteURL
    }
    private func get<T: Decodable>(_ path: String) async throws -> T { try await send(path, method: "GET", body: Optional<String>.none) }
    func registeredCameras() async throws -> [RegisteredCamera] { try await get("/api/devices") }
    func importDevices(account: String, environment: String, cameras: [SDKDiscoveredCamera]) async throws -> [RegisteredCamera] {
        struct Item: Encodable { var sn: String; var model: String; var name: String }
        struct Body: Encodable { var accountId: String; var environment: String; var platform = "ios"; var devices: [Item] }
        return try await send("/api/devices/import", body: Body(accountId: account, environment: environment, devices: cameras.map { Item(sn: $0.sn, model: $0.model, name: $0.name.isEmpty ? $0.model : $0.name) }))
    }
    func startMedia(_ deviceID: String, traceID: String? = nil) async throws -> LiveSession {
        try await send("/api/media-sessions", body: ["deviceId":deviceID,"platform":"ios"], traceID: traceID)
    }
    func liveHeartbeat(_ session: LiveSession, state: String, sequence: Int, age: Int?) async throws {
        struct Body: Encodable { var state: String; var sequence: Int; var frameAgeMs: Int? }
        let _: LiveAcknowledgement = try await send("/api/media-sessions/\(session.id)/heartbeat", body: Body(state: state, sequence: sequence, frameAgeMs: age), mediaSession: session)
    }
    func liveCommands(_ session: LiveSession) async throws -> [LiveCaptureCommand] {
        try await send("/api/media-sessions/\(session.id)/commands", method:"GET", body: Optional<String>.none, mediaSession:session)
    }
    func uploadLiveFrame(_ session: LiveSession, body: LiveFrameUpload, traceID: String? = nil) async throws {
        let _: LiveAcknowledgement = try await send("/api/media-sessions/\(session.id)/frames", body:body, mediaSession:session, traceID: traceID ?? body.requestId)
    }
    func stopMedia(_ session: LiveSession) async throws {
        let _: LiveAcknowledgement = try await send("/api/media-sessions/\(session.id)/stop", body:[String:String](), mediaSession:session)
    }
    func captureLive(_ deviceID: String) async throws -> CameraCapture {
        try await send("/api/devices/\(deviceID)/capture", body:[String:String]())
    }
    func agentRun(_ id: String) async throws -> AgentRun { try await get("/api/runs/\(id)") }
    func hardware(_ path: String, body: HardwareValue? = nil, executor: HardwareExecutorSession? = nil) async throws -> HardwareValue {
        try await send("/api/hardware/" + path, method: body == nil ? "GET" : "POST", body: body, executor: executor)
    }
    private func send<T: Decodable, B: Encodable>(_ path: String, method: String = "POST", body: B?, mediaSession: LiveSession? = nil, push: Bool = false, traceID: String? = nil, executor: HardwareExecutorSession? = nil) async throws -> T {
        var req = URLRequest(url: URL(string: path, relativeTo: baseURL)!.absoluteURL)
        try authorize(&req)
        let trace = traceID ?? mediaSession?.traceId ?? UUID().uuidString
        req.setValue(trace, forHTTPHeaderField: "X-EG-Trace-ID")
        let started = ProcessInfo.processInfo.systemUptime
        let track = method != "GET" && !path.hasSuffix("/heartbeat") && !path.hasSuffix("/presence")
        var outcome = "failed"
        defer {
            if track {
                let route = path.components(separatedBy: "?")[0].replacingOccurrences(of: "/(?:[a-fA-F0-9-]{20,}|live-[a-z0-9]+|sdk-[a-z0-9]+)(?=/|$)", with: "/:id", options: .regularExpression)
                observe(name: outcome == "completed" ? "api.completed" : "api.failed", traceID: trace, status: outcome,
                        durationMS: (ProcessInfo.processInfo.systemUptime - started) * 1000, route: route)
            }
        }
        if let mediaSession { req.setValue(mediaSession.token, forHTTPHeaderField: "X-EG-Media-Session") }
        if let executor { req.setValue(executor.token, forHTTPHeaderField: "X-EG-Executor-Token") }
        if push {
            guard baseURL.scheme == "https" || ["localhost", "127.0.0.1", "::1"].contains(baseURL.host ?? "") else { throw APIProblem(message: "手机通知需要安全的服务连接。") }
            req.setValue(try PushBinding.secret(for: baseURL), forHTTPHeaderField: "X-EG-Push-Key")
        }
        req.httpMethod = method; req.timeoutInterval = 30
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body { req.httpBody = try JSONEncoder().encode(body) }
        let data: Data
        let response: URLResponse
        do { (data, response) = try await transport.data(for: req) }
        catch let error as URLError {
            if error.code == .cancelled { throw CancellationError() }
            let message: String
            switch error.code {
            case .notConnectedToInternet, .networkConnectionLost: message = "网络暂时断开，恢复后会自动重连。输入的消息仍然保留。"
            case .timedOut: message = "连接超时，请稍后重试。输入的消息仍然保留。"
            default: message = "暂时无法连接服务，正在自动重试。"
            }
            throw APIProblem(message: message)
        }
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            if (response as? HTTPURLResponse)?.statusCode == 401, MobileServiceConfiguration.current.isInternalDemo {
                throw APIProblem(message: "演示版本的连接授权已失效，请更新测试版本或联系团队。无需自行配置。")
            }
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let conflicts = (try? JSONDecoder().decode(ConflictBody.self, from: data))?.conflicts ?? []
            throw APIProblem(message: json?["detail"] as? String ?? "服务请求未完成，请检查连接后重试。", conflicts: conflicts, statusCode: (response as? HTTPURLResponse)?.statusCode)
        }
        do { let value = try JSONDecoder().decode(T.self, from: data); outcome = "completed"; return value }
        catch { throw APIProblem(message: "当前版本无法读取服务返回的数据，请更新测试版本。") }
    }
    private func authorize(_ request: inout URLRequest) throws {
        guard let url = request.url, MobileServiceConfiguration.sameOrigin(baseURL, url) else {
            throw APIProblem(message: "请求地址不属于当前服务，已停止发送。")
        }
        request.setValue(MobileServiceConfiguration.installationID, forHTTPHeaderField: "X-EG-Installation-ID")
        if baseURL.scheme == "https" || ["127.0.0.1", "localhost", "::1"].contains(baseURL.host ?? "") {
            request.setValue(try PushBinding.secret(for: baseURL), forHTTPHeaderField: "X-EG-Private-Key")
        }
        let token = accessToken
        guard !token.isEmpty else { return }
        guard baseURL.scheme == "https" || ["127.0.0.1", "localhost", "::1"].contains(baseURL.host ?? "") else {
            throw APIProblem(message: "团队访问令牌只能通过 HTTPS 发送，请检查服务地址。")
        }
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }

    // The dashboard secret never enters the mobile app. This narrow endpoint
    // accepts only client-reported metadata and cannot write model/prompt data.
    func observe(name: String, traceID: String, parentSpanID: String? = nil, status: String = "observed", durationMS: Double? = nil, deviceID: String? = nil, requestID: String? = nil, route: String? = nil) {
        struct Event: Encodable {
            var id = UUID().uuidString; var spanId = UUID().uuidString; var platform = "ios"
            var appVersion = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown") + "/" + (Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown")
            var name: String; var traceId: String; var parentSpanId: String?; var status: String
            var durationMs: Double?; var deviceId: String?; var requestId: String?; var route: String?
        }
        var request = URLRequest(url: baseURL.appendingPathComponent("api/ops/client-events"))
        guard (try? authorize(&request)) != nil else { return }
        request.httpMethod = "POST"; request.timeoutInterval = 2.5
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode([Event(name: name, traceId: traceID, parentSpanId: parentSpanID, status: status,
            durationMs: durationMS, deviceId: deviceID, requestId: requestID, route: route)])
        guard request.httpBody != nil else { return }
        Task(priority: .background) { await observations.send(request) }
    }
}
