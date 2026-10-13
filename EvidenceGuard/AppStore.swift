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
    @Published var conversationDrafts: [String: String] = [:] { didSet { persistChat() } }
    var pendingChatRequests: [String: PendingChatRequest] = [:] { didSet { persistChat() } }
    @Published var conversations: [ConversationSummary] = []
    @Published var activeConversationID: String
    @Published var creatingConversation = false
    @Published var conversationListError: String?
    var conversationModes: [String: String] = [:] { didSet { persistChat() } }
    private var newConversationRequestID: String? { didSet { persistChat() } }
    private var chatStorageKey: String { "localChats:" + client.baseURL.absoluteString }
    private func persistChat() {
        let state = LocalChatState(drafts: conversationDrafts, pending: pendingChatRequests, modes: conversationModes, newConversationRequestID: newConversationRequestID)
        if let value = try? JSONEncoder().encode(state) { UserDefaults.standard.set(value, forKey: chatStorageKey) }
    }
    private func restoreChat() {
        guard let value = UserDefaults.standard.data(forKey: chatStorageKey), let state = try? JSONDecoder().decode(LocalChatState.self, from: value) else { return }
        conversationDrafts = state.drafts; pendingChatRequests = state.pending
        conversationModes = state.modes; newConversationRequestID = state.newConversationRequestID
    }
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
    private var personalOrigin: URL?
    var unreadAssistantCount: Int { data.personal?.messages?.filter { !$0.read }.count ?? 0 }
    init() {
        let defaults = UserDefaults.standard
        MobileServiceConfiguration.current.migrateLegacyChatState(in: defaults)
        let base = MobileServiceConfiguration.current.isInternalDemo ? APIClient.defaultBaseURL.absoluteString : (defaults.string(forKey: "serviceURL") ?? APIClient.defaultBaseURL.absoluteString)
        client = APIClient(baseURL: URL(string: base) ?? APIClient.defaultBaseURL)
        generalConversation = defaults.string(forKey: "conversationID") ?? "chat-\(UUID().uuidString)"
        defaults.set(generalConversation, forKey: "conversationID")
        activeConversationID = defaults.string(forKey: "activeChat:" + base) ?? generalConversation
        restoreChat()
    }
    var selectedCamera: CameraDevice? { data.cameras.first { $0.id == selectedCameraID } ?? data.cameras.first }
    func camera(_ id: String) -> CameraDevice? { data.cameras.first { $0.id == id } }
    func skill(_ id: String) -> VisualSkill? { data.skills.first { $0.id == id } }
    var onlineCount: Int { data.cameras.filter { $0.fresh && isConnected }.count }
    func selectConversation(_ id: String) {
        activeConversationID = id
        UserDefaults.standard.set(id, forKey: "activeChat:" + client.baseURL.absoluteString)
    }
    func reloadConversations() async {
        let origin = client.baseURL
        do {
            let items = try await client.conversations()
            guard client.baseURL == origin else { return }
            conversations = items; conversationListError = nil
        } catch {
            guard client.baseURL == origin else { return }
            conversationListError = "对话列表暂未同步，请重试。已有对话和草稿会保留。"
        }
    }
    @discardableResult func newConversation() async -> Bool {
        guard !creatingConversation else { return false }
        creatingConversation = true; defer { creatingConversation = false }
        let requestID = newConversationRequestID ?? UUID().uuidString
        let origin = client.baseURL
        newConversationRequestID = requestID
        do {
            let value = try await client.newConversation(requestID: requestID)
            guard client.baseURL == origin else { return false }
            if !conversations.contains(where: { $0.id == value.id }) { conversations.insert(value, at: 0) }
            newConversationRequestID = nil; selectConversation(value.id)
            return true
        } catch {
            if client.baseURL == origin { errorMessage = "新建对话失败：" + error.localizedDescription }
            return false
        }
    }
    func renameConversation(_ id: String, title: String) async {
        do {
            let value = try await client.renameConversation(id, title: title)
            if let index = conversations.firstIndex(where: { $0.id == id }) { conversations[index] = value }
        } catch { errorMessage = error.localizedDescription }
    }
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
            isConnected = false; lastError = MobileServiceConfiguration.current.isInternalDemo ? "此测试版本连接配置不完整，请联系团队更新。" : "请在“我的 → 服务连接”设置云端 HTTPS 地址。"; return
        }
        do {
            data = try await client.bootstrap(); isConnected = true; lastError = nil
            if personalOrigin != client.baseURL {
                do { try await client.bindPersonalConversation(generalConversation); personalOrigin = client.baseURL; await reloadConversations() }
                catch { data.personal?.lastError = "助手对话尚未完成同步，正在重试。" }
            }
        } catch is CancellationError { }
        catch let problem as APIProblem { isConnected = false; lastError = problem.message }
        catch { isConnected = false; lastError = "服务暂时未连接，已显示的记录不代表当前状态。" }
    }
    func configure(_ url: String, accessToken: String? = nil) async -> Bool {
        errorMessage = nil
        guard !MobileServiceConfiguration.current.isInternalDemo else { await refresh(); return isConnected }
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
        // Preserve each service's local state before changing namespaces.
        conversations = []
        let saved = UserDefaults.standard.data(forKey: "localChats:" + parsed.absoluteString).flatMap { try? JSONDecoder().decode(LocalChatState.self, from: $0) } ?? LocalChatState()
        conversationDrafts = saved.drafts; pendingChatRequests = saved.pending
        conversationModes = saved.modes; newConversationRequestID = saved.newConversationRequestID
        activeConversationID = UserDefaults.standard.string(forKey: "activeChat:" + parsed.absoluteString) ?? generalConversation
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
