import SwiftUI
import AuthenticationServices
import EventKit

struct ConnectedApp: Decodable, Identifiable {
    var id: String; var name: String; var configured: Bool; var connected: Bool; var scope: String
}
struct ConnectorAuthorization: Decodable { var url: String; var state: String; var callbackScheme: String }
struct SharedPhoneItem: Codable, Identifiable {
    var kind: String; var title: String; var date: String?
    var id: String { "\(kind)|\(date ?? "")|\(title)" }
}
struct SharedPhoneContext: Codable {
    var items: [SharedPhoneItem]; var truncated: Bool?; var expiresAt: Double?
}
struct CameraObservation: Decodable, Identifiable {
    var cameraId: String; var name: String; var enabled: Bool; var intervalSeconds: Int
    var status: String; var reason: String; var lastAttemptAt: Double?
    var id: String { cameraId }
}

@MainActor private final class ConnectorSignIn: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows).first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
    func authorize(_ request: ConnectorAuthorization) async throws -> String {
        guard let url = URL(string: request.url), url.scheme == "https",
              ["accounts.google.com", "accounts.feishu.cn"].contains(url.host ?? ""),
              request.callbackScheme == "com.zhangmiao.evidenceguard.connect" else {
            throw APIProblem(message: "授权地址无效，请稍后再试")
        }
        return try await withCheckedThrowingContinuation { continuation in
            session = ASWebAuthenticationSession(url: url, callbackURLScheme: request.callbackScheme) { [weak self] callback, error in
                Task { @MainActor in self?.session = nil }
                if let error { continuation.resume(throwing: error); return }
                guard let callback, callback.scheme == request.callbackScheme, callback.host == "oauth",
                      let parts = URLComponents(url: callback, resolvingAgainstBaseURL: false) else {
                    continuation.resume(throwing: APIProblem(message: "授权回调无效")); return
                }
                let values = parts.queryItems ?? []
                guard values.first(where: { $0.name == "state" })?.value == request.state,
                      values.first(where: { $0.name == "error" })?.value?.isEmpty != false,
                      let code = values.first(where: { $0.name == "code" })?.value, !code.isEmpty else {
                    continuation.resume(throwing: APIProblem(message: "授权未完成，请重新连接")); return
                }
                continuation.resume(returning: code)
            }
            session?.presentationContextProvider = self
            if session?.start() != true {
                session = nil
                continuation.resume(throwing: APIProblem(message: "暂时无法打开授权页面"))
            }
        }
    }
}

struct ConnectedAppsView: View {
    @EnvironmentObject private var store: AppStore
    @StateObject private var signIn = ConnectorSignIn()
    @State private var apps: [ConnectedApp] = []
    @State private var busy = false
    @State private var message: String?
    var body: some View {
        List {
            Section {
                Text("连接后，你可以直接问 anker：最近有哪些重要邮件，或某个飞书群在讨论什么。读取的内容会交给云端助手处理。")
            }
            ForEach(apps) { app in
                Section(app.name) {
                    LabeledContent("连接状态", value: app.connected ? "已连接" : (app.configured ? "未连接" : "团队正在准备接入"))
                    Text(app.scope).font(.caption).foregroundStyle(Brand.muted)
                    if app.configured {
                        Button(app.connected ? "重新授权" : "连接 \(app.name)") {
                            perform {
                                let request = try await store.client.authorizeConnector(app.id)
                                let code = try await signIn.authorize(request)
                                apps = try await store.client.completeConnector(app.id, state: request.state, code: code)
                                message = "\(app.name) 已连接，可以回到助手提问了。"
                            }
                        }
                    }
                    if app.connected {
                        Button("断开连接", role: .destructive) {
                            perform { apps = try await store.client.disconnectConnector(app.id); message = "连接已断开。也可以到该平台的账号设置中撤销应用授权。" }
                        }
                    }
                }
            }
            Section("手机里的信息") {
                NavigationLink { PhoneContextView() } label: { Label("日历与提醒事项", systemImage: "calendar") }
                Text("先在手机预览，再选择共享。anker 无法直接读取其他 App 的聊天、短信或通知。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            Section {
                Text("连接只提供读取能力，不会发送邮件或群消息。邮件和群消息不会自动写入个人记忆。断开连接会删除服务保存的授权令牌；已进入聊天的内容仍保留在聊天记录里。")
                    .font(.caption).foregroundStyle(Brand.muted)
                if busy { ProgressView("正在处理…") }
                if let message { Text(message).font(.subheadline) }
                Button("刷新连接状态") { perform { apps = try await store.client.connectedApps() } }
            }
        }.disabled(busy).pageStyle("连接应用")
            .task { do { apps = try await store.client.connectedApps() } catch { message = error.localizedDescription } }
    }
    private func perform(_ operation: @escaping @MainActor () async throws -> Void) {
        guard !busy else { return }; busy = true; message = nil
        Task { defer { busy = false }; do { try await operation() } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin { message = "已取消连接。" } catch { message = error.localizedDescription } }
    }
}

struct PhoneContextView: View {
    @EnvironmentObject private var store: AppStore
    @State private var eventStore = EKEventStore()
    @State private var items: [SharedPhoneItem] = []
    @State private var truncated = false
    @State private var previewed = false
    @State private var busy = false
    @State private var message: String?
    var body: some View {
        List {
            Section {
                Text("选择要读取的内容，预览后再共享给 anker。只读取标题和日期，不读取备注、参与人或附件。")
                Button("预览未来 7 天的日历") { perform { try await loadCalendar() } }
                Button("预览未完成的提醒事项") { perform { try await loadReminders() } }
                Text("iOS 会请求日历或提醒事项的完整访问权限。本 App 只读取你在这里选择的内容，不添加或修改条目。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            if previewed {
                Section("即将共享 · \(items.count) 条") {
                    if items.isEmpty { Text("当前范围没有条目。") }
                    ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                        VStack(alignment: .leading) { Text(item.title); if let date = item.date { Text(date).font(.caption).foregroundStyle(Brand.muted) } }
                    }.onDelete { items.remove(atOffsets: $0) }
                    if truncated { Text("条目较多，只显示前 20 条。可以左滑移除不想共享的内容。") }
                    Button("共享给 anker，24 小时内可读") {
                        perform { try await store.client.sharePhone(items, truncated: truncated); message = "已共享。回到助手即可提问；这份快照不会自动更新。" }
                    }
                }
            }
            Section {
                Button("移除已共享的手机快照", role: .destructive) {
                    perform { try await store.client.removePhoneContext(); items = []; previewed = false; message = "已移除快照；已进入聊天的内容仍在聊天记录里。" }
                }
                if busy { ProgressView() }
                if let message { Text(message) }
                Text("共享会覆盖上一份快照。标题和日期加密保存在云端，24 小时后不再供助手读取；不自动存入长期记忆。可以随时在系统设置撤销权限。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
        }.disabled(busy).pageStyle("手机信息")
    }
    @MainActor private func loadCalendar() async throws {
        guard try await eventStore.requestFullAccessToEvents() else { throw APIProblem(message: "未获得日历权限。可以在系统设置中调整。") }
        let start = Date(), end = Calendar.current.date(byAdding: .day, value: 7, to: Date())!
        let events = eventStore.events(matching: eventStore.predicateForEvents(withStart: start, end: end, calendars: nil)).sorted { $0.startDate < $1.startDate }
        items = events.prefix(20).map { SharedPhoneItem(kind: "calendar", title: String(($0.title ?? "未命名日程").prefix(300)), date: $0.startDate.ISO8601Format()) }
        truncated = events.count > 20; previewed = true
    }
    @MainActor private func loadReminders() async throws {
        guard try await eventStore.requestFullAccessToReminders() else { throw APIProblem(message: "未获得提醒事项权限。可以在系统设置中调整。") }
        let reminders: [EKReminder] = await withCheckedContinuation { continuation in
            eventStore.fetchReminders(matching: eventStore.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: nil)) { continuation.resume(returning: $0 ?? []) }
        }
        let sorted = reminders.sorted { ($0.dueDateComponents?.date ?? .distantFuture) < ($1.dueDateComponents?.date ?? .distantFuture) }
        items = sorted.prefix(20).map { SharedPhoneItem(kind: "reminder", title: String(($0.title ?? "未命名提醒").prefix(300)), date: $0.dueDateComponents?.date?.ISO8601Format()) }
        truncated = sorted.count > 20; previewed = true
    }
    private func perform(_ operation: @escaping @MainActor () async throws -> Void) {
        guard !busy else { return }; busy = true; message = nil
        Task { defer { busy = false }; do { try await operation() } catch { message = error.localizedDescription } }
    }
}

struct CameraObservationSettingsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var cameras: [CameraObservation] = []
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        List {
            Section {
                Text("anker 会按间隔取一张画面，结合已有记录判断是否值得提醒。两台摄像头分别设置，设备事件仍由事件同步单独接收。")
                Text("目前需要 App 在前台保持官方摄像头连接。手机锁屏或采集端离线时，云端会记录取样失败，不能继续观察。全天候接收还需接入设备云事件或常在线采集端。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            if cameras.isEmpty { Text("先到摄像头账号连接设备，再开启定时观察。") }
            ForEach(cameras) { camera in
                Section(camera.name) {
                    Toggle("定时观察", isOn: Binding(get: { camera.enabled }, set: { save(camera, enabled: $0, interval: camera.intervalSeconds) }))
                    Picker("取样间隔", selection: Binding(get: { camera.intervalSeconds }, set: { save(camera, enabled: camera.enabled, interval: $0) })) {
                        Text("每 5 分钟").tag(300); Text("每 15 分钟").tag(900); Text("每 30 分钟").tag(1800); Text("每小时").tag(3600)
                    }
                    Text(camera.reason).font(.subheadline)
                    if let at = camera.lastAttemptAt { Text("最近尝试：\(Date(timeIntervalSince1970: at).formatted())").font(.caption).foregroundStyle(Brand.muted) }
                }
            }
            Section {
                Text("取样与事件分析共用每台每天 100 次的模型额度；间隔较短可能提前用完。设置在家庭空间共享。通知仍遵循免打扰和频率限制，不会看到人就无限重复推送。")
                    .font(.caption).foregroundStyle(Brand.muted)
                NavigationLink("设置手机通知与主动提醒", value: AppRoute.notificationSettings)
                Button("刷新观察状态") { Task { await load() } }
                if busy { ProgressView() }
                if let error { Text(error).foregroundStyle(.orange) }
            }
        }.disabled(busy).pageStyle("定时观察").task { await load() }
    }
    private func load() async {
        busy = true; defer { busy = false }
        do { cameras = try await store.client.cameraObservations(); error = nil } catch { self.error = error.localizedDescription }
    }
    private func save(_ camera: CameraObservation, enabled: Bool, interval: Int) {
        guard !busy else { return }; busy = true
        Task { defer { busy = false }; do { cameras = try await store.client.saveObservation(camera.id, enabled: enabled, interval: interval); error = nil } catch { self.error = error.localizedDescription } }
    }
}
