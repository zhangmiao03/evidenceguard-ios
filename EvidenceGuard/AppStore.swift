import Combine
import Foundation

@MainActor final class AppStore: ObservableObject {
    @Published var data = Bootstrap.empty
    @Published var isConnected = false
    @Published var lastError: String?
    @Published var errorMessage: String?
    @Published var toast: String?
    @Published var selectedTab = 0
    @Published var tabPaths: [[AppRoute]] = Array(repeating: [], count: 5)
    @Published var conversationDrafts: [String: String] = [:]
    var path: [AppRoute] {
        get { tabPaths[selectedTab] }
        set { tabPaths[selectedTab] = newValue }
    }
    @Published var editor: VisualSkill?
    var editorRegionCameraID: String?
    func openEditor(_ skill: VisualSkill, regionCameraID: String? = nil) {
        editorRegionCameraID = regionCameraID
        editor = skill
    }
    @Published var selectedCameraID = "cam-a"
    @Published var busy = false
    var client: APIClient
    let officialSDK = OfficialSDKConnection()
    let generalConversation: String
    private var polling = false
    init() {
        let defaults = UserDefaults.standard
        let base = defaults.string(forKey: "serviceURL") ?? APIClient.defaultBaseURL.absoluteString
        client = APIClient(baseURL: URL(string: base) ?? APIClient.defaultBaseURL)
        generalConversation = defaults.string(forKey: "conversationID") ?? "chat-\(UUID().uuidString)"
        defaults.set(generalConversation, forKey: "conversationID")
    }
    var selectedCamera: CameraDevice? { data.cameras.first { $0.id == selectedCameraID } ?? data.cameras.first }
    func camera(_ id: String) -> CameraDevice? { data.cameras.first { $0.id == id } }
    func skill(_ id: String) -> VisualSkill? { data.skills.first { $0.id == id } }
    var onlineCount: Int { data.cameras.filter { $0.fresh && isConnected }.count }
    func openAI(prompt: String = "", skillID: String? = nil) {
        let id = skillID.map { "skill-chat-\($0)" } ?? generalConversation
        if !prompt.isEmpty { conversationDrafts[id] = prompt }
        path.append(.conversation(skillID.map { "skill-chat-\($0)" } ?? generalConversation, skillID))
    }
    func poll() async {
        guard !polling else { return }; polling = true
        defer { polling = false }
        while !Task.isCancelled {
            await refresh()
            do { try await Task.sleep(for: .seconds(2)) } catch { break }
        }
    }
    func refresh() async {
        guard client.baseURL.host != "unconfigured.invalid" else {
            isConnected = false; lastError = "请在“我的 → 服务连接”设置云端 HTTPS 地址。"; return
        }
        do {
            data = try await client.bootstrap(); isConnected = true; lastError = nil
        } catch is CancellationError { }
        catch let problem as APIProblem { isConnected = false; lastError = problem.message }
        catch { isConnected = false; lastError = "服务暂时未连接，已显示的记录不代表当前状态。" }
    }
    func configure(_ url: String, accessToken: String? = nil) async -> Bool {
        errorMessage = nil
        guard let parsed = URL(string: url.trimmingCharacters(in: .whitespacesAndNewlines)), ["http", "https"].contains(parsed.scheme), parsed.host != nil, parsed.user == nil, parsed.password == nil, parsed.query == nil, parsed.fragment == nil, ["", "/"].contains(parsed.path) else {
            errorMessage = "请输入完整的 http:// 或 https:// 服务地址。"; return false
        }
        #if !DEBUG
        guard parsed.scheme == "https" else { errorMessage = "测试分发版本需要可访问的 HTTPS 服务地址。"; return false }
        #endif
        if let accessToken {
            do { try ServiceAccess.save(accessToken.trimmingCharacters(in: .whitespacesAndNewlines), for: parsed) }
            catch { errorMessage = error.localizedDescription; return false }
        }
        client = APIClient(baseURL: parsed); data = .empty
        UserDefaults.standard.set(parsed.absoluteString, forKey: "serviceURL")
        await refresh(); return isConnected
    }
    func perform(_ action: () async throws -> Void) async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do { try await action(); await refresh() } catch { errorMessage = error.localizedDescription }
    }
    func change(_ id: String, action: String) async {
        await perform { _ = try await client.lifecycle(id, action: action); toast = action == "pause" ? "守护已暂停" : action == "resume" ? "已恢复，等待新观察" : "任务已停止" }
    }
    func recheck(_ id: String, acknowledged: Bool = false) async {
        await perform { _ = try await client.recheck(id, acknowledged: acknowledged); toast = "已请求新画面，复核完成前保持无法确认" }
    }
}
