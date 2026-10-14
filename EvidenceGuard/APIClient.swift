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
    var accessToken: String { ServiceAccess.token(for: baseURL) }
    init(baseURL: URL = APIClient.defaultBaseURL) { self.baseURL = baseURL }
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
    func capability(_ id: String) async throws -> SkillCapability { try await get("/api/skills/\(id)/capability") }
    func trials(_ id: String) async throws -> [SkillTrial] { try await get("/api/skills/\(id)/trials") }
    func trial(_ id: String) async throws -> SkillTrial { try await get("/api/skill-trials/\(id)") }
    func deployment(_ id: String) async throws -> DeploymentPlan { try await get("/api/skills/\(id)/deployment") }
    func prepareSite(_ id: String, revision: Int, action: String, completed: Bool) async throws -> DeploymentPlan { try await send("/api/skills/\(id)/deployment/preparation", body: PreparationRequestBody(revision: revision, action: action, completed: completed)) }
    func startTrial(_ skill: VisualSkill, expectedOutcome: String) async throws -> SkillTrial { try await send("/api/skills/\(skill.id)/trials", body: TrialRequestBody(revision: skill.revision, expectedOutcome: expectedOutcome)) }
    func cancelTrial(_ id: String) async throws -> SkillTrial { try await send("/api/skill-trials/\(id)/cancel", body: [String:String]()) }
    func trialRecording(_ id: String) async throws -> VideoRecording { try await get("/api/skill-trials/\(id)/recording") }
    func personalSettings() async throws -> PersonalSnapshot { try await get("/api/personal") }
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
        let (data, response) = try await URLSession.shared.upload(for: request, fromFile: file)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw APIProblem(message: json?["detail"] as? String ?? "录像上传失败，请重试")
        }
        return try JSONDecoder().decode(VideoRecording.self, from: data)
    }
    func start(message: String, conversation: String, skill: String?, camera: String?, requestID: String, executionMode: String = "live", historyFilter: HistoryFilter? = nil, replyToMessageID: String? = nil) async throws -> AgentRun {
        struct Body: Encodable { var message: String; var conversationId: String; var requestId: String; var skillId: String?; var cameraId: String?; var executionMode: String; var historyFilter: HistoryFilter?; var replyToMessageId: String? }
        return try await send("/api/agent/runs", body: Body(message: message, conversationId: conversation, requestId: requestID, skillId: skill, cameraId: camera, executionMode: executionMode, historyFilter: historyFilter, replyToMessageId: replyToMessageID))
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
    func startMedia(_ deviceID: String) async throws -> LiveSession {
        try await send("/api/media-sessions", body: ["deviceId":deviceID,"platform":"ios"])
    }
    func liveHeartbeat(_ session: LiveSession, state: String, sequence: Int, age: Int?) async throws {
        struct Body: Encodable { var state: String; var sequence: Int; var frameAgeMs: Int? }
        let _: LiveAcknowledgement = try await send("/api/media-sessions/\(session.id)/heartbeat", body: Body(state: state, sequence: sequence, frameAgeMs: age), mediaSession: session)
    }
    func liveCommands(_ session: LiveSession) async throws -> [LiveCaptureCommand] {
        try await send("/api/media-sessions/\(session.id)/commands", method:"GET", body: Optional<String>.none, mediaSession:session)
    }
    func uploadLiveFrame(_ session: LiveSession, body: LiveFrameUpload) async throws {
        let _: LiveAcknowledgement = try await send("/api/media-sessions/\(session.id)/frames", body:body, mediaSession:session)
    }
    func stopMedia(_ session: LiveSession) async throws {
        let _: LiveAcknowledgement = try await send("/api/media-sessions/\(session.id)/stop", body:[String:String](), mediaSession:session)
    }
    func captureLive(_ deviceID: String) async throws -> CameraCapture {
        try await send("/api/devices/\(deviceID)/capture", body:[String:String]())
    }
    func agentRun(_ id: String) async throws -> AgentRun { try await get("/api/runs/\(id)") }
    private func send<T: Decodable, B: Encodable>(_ path: String, method: String = "POST", body: B?, mediaSession: LiveSession? = nil, push: Bool = false) async throws -> T {
        var req = URLRequest(url: URL(string: path, relativeTo: baseURL)!.absoluteURL)
        try authorize(&req)
        if let mediaSession { req.setValue(mediaSession.token, forHTTPHeaderField: "X-EG-Media-Session") }
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
        do { (data, response) = try await URLSession.shared.data(for: req) }
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
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw APIProblem(message: "当前版本无法读取服务返回的数据，请更新测试版本。") }
    }
    private func authorize(_ request: inout URLRequest) throws {
        guard let url = request.url, MobileServiceConfiguration.sameOrigin(baseURL, url) else {
            throw APIProblem(message: "请求地址不属于当前服务，已停止发送。")
        }
        request.setValue(MobileServiceConfiguration.installationID, forHTTPHeaderField: "X-EG-Installation-ID")
        let token = accessToken
        guard !token.isEmpty else { return }
        guard baseURL.scheme == "https" || ["127.0.0.1", "localhost", "::1"].contains(baseURL.host ?? "") else {
            throw APIProblem(message: "团队访问令牌只能通过 HTTPS 发送，请检查服务地址。")
        }
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
}
