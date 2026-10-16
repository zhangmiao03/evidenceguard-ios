import SwiftUI
import UserNotifications
import Security

struct PushStatus: Decodable {
    var serverReady: Bool
    var scope: String
    var registered: Bool
    var enabled: Bool
    var lastState: String?
    var lastReason: String?
    var acceptedAt: Double?
    var openedAt: Double?
    var workerError: String?
    var deliveryLabel: String {
        if openedAt != nil { return "已点开通知" }
        return ["pending":"等待发送", "retry":"等待重试或合适的提醒时间", "accepted":"Apple 已接受，等待手机接收", "failed":"本次发送未成功", "expired":"已过提醒时效", "cancelled":"已取消或无需重复提醒", "sending":"正在发送"][lastState ?? ""] ?? "尚无推送记录"
    }
}

struct PushDestination: Decodable {
    var kind: String
    var title: String
    var body: String
    var messageId: String?
    var skillId: String?
    var evidenceId: String?
    var conversationId: String?
    var executionMode: String?
    var draftId: String?
}

enum PushBinding {
    static func secret(for url: URL) throws -> String {
        // Bind proof to both installation and service. Never reuse a bearer token.
        let account = "\(url.scheme ?? "")://\(url.host ?? ""):\(url.port ?? (url.scheme == "https" ? 443 : 80))/\(MobileServiceConfiguration.installationID)"
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.evidenceguard.push-binding", kSecAttrAccount as String: account]
        var read = query
        read[kSecReturnData as String] = true; read[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(read as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data, let value = String(data: data, encoding: .utf8) { return value }
        guard status == errSecItemNotFound else {
            throw APIProblem(message: status == errSecInteractionNotAllowed ? "请解锁手机后重新同步通知。" : "本机通知授权暂不可用，请重新打开 App 或更新测试版本。")
        }
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw APIProblem(message: "无法创建本机通知授权，请重试。") }
        let value = bytes.map { String(format: "%02x", $0) }.joined()
        var saved = query
        saved[kSecValueData as String] = Data(value.utf8)
        saved[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        guard SecItemAdd(saved as CFDictionary, nil) == errSecSuccess else { throw APIProblem(message: "无法保存本机通知授权，请重试。") }
        return value
    }
}

@MainActor final class PushNotifications: ObservableObject {
    static let shared = PushNotifications()
    @Published var status: PushStatus?
    @Published var authorization: UNAuthorizationStatus = .notDetermined
    @Published var busy = false
    @Published var error: String?
    @Published var feedback: String?
    @Published var pending: PushTap? {
        didSet { UserDefaults.standard.set(try? JSONEncoder().encode(pending), forKey: "pendingPushTap") }
    }
    private var client: APIClient?
    private var token: String?
    private var registeredToken: String?
    private var active = true
    private var syncing = false
    private var syncAgain = false
    private var disablePending = false
    private var preferenceKey: String { "phoneNotifications:" + (client?.baseURL.absoluteString ?? "") }
    var wanted: Bool { UserDefaults.standard.bool(forKey: preferenceKey) }
    var allowed: Bool { [.authorized, .provisional, .ephemeral].contains(authorization) }
    var permissionLabel: String {
        switch authorization {
        case .authorized: return "已允许"
        case .provisional, .ephemeral: return "已允许安静通知"
        case .denied: return "系统通知已关闭"
        default: return "尚未允许"
        }
    }
    private init() {
        if let data = UserDefaults.standard.data(forKey: "pendingPushTap") { pending = try? JSONDecoder().decode(PushTap.self, from: data) }
    }
    func attach(_ client: APIClient) {
        if self.client?.baseURL != client.baseURL {
            status = nil; registeredToken = nil; error = nil
            self.client = client
        }
    }
    func received(_ data: Data) async {
        token = data.map { String(format: "%02x", $0) }.joined()
        registeredToken = nil
        await sync()
    }
    func registrationFailed() { error = "手机通知登记失败，请检查网络并重试。" }
    func tapped(_ userInfo: [AnyHashable: Any]) {
        guard let value = userInfo["eg"] as? [String: String], let id = value["deliveryId"], UUID(uuidString: id) != nil,
              let scope = value["scope"], scope.range(of: "^[a-z0-9-]{1,40}$", options: .regularExpression) != nil else { return }
        pending = PushTap(id: id, scope: scope)
    }
    func setActive(_ active: Bool) async {
        self.active = active
        await sync()
    }
    func enable() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        error = nil; feedback = nil
        do {
            _ = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            authorization = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
            guard allowed else { error = "请在系统设置中允许 EvidenceGuard 发送通知。"; return }
            UserDefaults.standard.set(true, forKey: preferenceKey)
            disablePending = false
            UIApplication.shared.registerForRemoteNotifications()
            await sync()
        } catch { self.error = "无法请求通知权限，请在系统设置中检查。" }
    }
    func disable() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        // Keep retrying server revocation if this request is interrupted/offline.
        UserDefaults.standard.set(false, forKey: preferenceKey)
        disablePending = true; registeredToken = nil
        await sync()
    }
    func sync() async {
        if syncing { syncAgain = true; return }
        guard let client else { return }
        syncing = true
        defer {
            syncing = false
            if syncAgain { syncAgain = false; Task { await self.sync() } }
        }
        authorization = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        do {
            var current = try await client.pushStatus()
            guard self.client?.baseURL == client.baseURL else { return }
            if !wanted || !allowed || disablePending {
                if current.enabled { current = try await client.disablePush() }
                disablePending = false; registeredToken = nil
            } else if let token, registeredToken != token || !current.enabled {
                current = try await client.registerPush(token: token)
                registeredToken = token
            } else if token == nil {
                UIApplication.shared.registerForRemoteNotifications()
            }
            if current.registered { try await client.pushPresence(active: active) }
            guard self.client?.baseURL == client.baseURL else { return }
            status = current; error = nil
        } catch {
            guard self.client?.baseURL == client.baseURL else { return }
            self.error = error.localizedDescription
        }
    }
    func test() async {
        guard !busy, let client else { return }; busy = true; defer { busy = false }
        do {
            try await client.testPush()
            feedback = "测试将在约 10 秒后发送。现在可回到主屏幕或锁屏，再点通知回来。"
            await sync()
        } catch { self.error = error.localizedDescription }
    }
}

@MainActor final class PushAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    static var orientation: UIInterfaceOrientationMask = .portrait
    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        Self.orientation
    }
    static func setOrientation(_ mask: UIInterfaceOrientationMask) {
        orientation = mask
        for scene in UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }) {
            scene.windows.first(where: \.isKeyWindow)?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
            scene.requestGeometryUpdate(.iOS(interfaceOrientations: mask)) { _ in }
        }
    }
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in await PushNotifications.shared.received(deviceToken) }
    }
    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in PushNotifications.shared.registrationFailed() }
    }
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let info = response.notification.request.content.userInfo
        Task { @MainActor in PushNotifications.shared.tapped(info); completionHandler() }
    }
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Foreground uses the assistant's own inbox; still retain the notification
        // in Notification Center so an explicit test can be opened.
        completionHandler([.list])
    }
}

struct PushDeliveryView: View {
    @EnvironmentObject var store: AppStore
    let id: String
    let scope: String
    @State private var result: PushDestination?
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        List {
            if let result {
                Section(result.title) { Text(result.body) }
                if result.kind == "test" { Label("已记录点开，测试完成", systemImage: "checkmark.circle.fill").foregroundStyle(Brand.green) }
                if let id = result.draftId { NavigationLink("查看待确认草案", value: AppRoute.skill(id)) }
                if let id = result.evidenceId { NavigationLink("查看证据", value: AppRoute.evidence(id)) }
                if let id = result.skillId { NavigationLink("查看任务", value: AppRoute.skill(id)) }
                if let id = result.conversationId { NavigationLink("回到对话", value: conversationRoute(id, result)) }
                if let id = result.messageId { Button("在助手对话中查看") { Task { await openMessage(id) } } }
                if result.kind == "message" { NavigationLink("查看提醒记录", value: AppRoute.personalInbox) }
            } else if loading { ProgressView("正在读取通知内容") }
            if let error { Text(error).foregroundStyle(.orange); Button("重试") { Task { await load() } } }
        }.pageStyle("通知详情").task { await load() }
    }
    private func load() async {
        guard !loading else { return }; loading = true; defer { loading = false }
        let client = store.client
        do {
            let status = try await client.pushStatus()
            guard status.scope == scope else { throw APIProblem(message: "这条通知来自其他服务空间，请切回原服务后查看。") }
            let target = try await client.openPush(id)
            guard store.client.baseURL == client.baseURL else { return }
            result = target; error = nil
            await store.refresh()
            await PushNotifications.shared.sync()
            guard store.client.baseURL == client.baseURL else { return }
            // Message identity takes priority over its evidence/task attachments.
            if let message = target.messageId {
                try await store.openAssistantMessage(message)
            } else if let draft = target.draftId, store.skill(draft) != nil {
                store.path.append(.skill(draft))
            } else if let evidence = target.evidenceId, store.data.evidence.contains(where: { $0.id == evidence }) {
                store.path.append(.evidence(evidence))
            } else if let conversation = target.conversationId {
                store.path.append(conversationRoute(conversation, target))
            } else if let skill = target.skillId, store.skill(skill) != nil {
                store.path.append(.skill(skill))
            }
        } catch { self.error = error.localizedDescription }
    }
    private func openMessage(_ id: String) async {
        do { try await store.openAssistantMessage(id); error = nil }
        catch { self.error = error.localizedDescription }
    }
    private func conversationRoute(_ id: String, _ result: PushDestination) -> AppRoute {
        let history = result.executionMode == "history"
        let base = history && id.hasSuffix("-history") ? String(id.dropLast(8)) : id
        return .pushConversation(base, result.skillId, history ? "history" : "live")
    }
}
