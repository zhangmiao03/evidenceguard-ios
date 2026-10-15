import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        SDKWorkspaceContainer(connection: store.officialSDK) { ProductRootView() }
            .task { await store.poll() }
    }
}

private struct ProductRootView: View {
    @Environment(\.scenePhase) private var scenePhase
    @EnvironmentObject private var store: AppStore
    @AppStorage("showFeedback") private var showFeedback = true
    var body: some View {
        TabView(selection: $store.selectedTab) {
            tab(.assistant) { TeachAIView() }.tabItem { Label("助手", systemImage: "bubble.left.and.bubble.right.fill") }.badge(store.unreadAssistantCount).tag(AppTab.assistant)
            tab(.cameraSkills) { CameraSkillsView() }.tabItem { Label("摄像头Skill", systemImage: "video.fill") }.tag(AppTab.cameraSkills)
            tab(.tasks) { TasksView() }.tabItem { Label("任务", systemImage: "checklist") }.tag(AppTab.tasks)
            tab(.memory) { MemoryView() }.tabItem { Label("记忆", systemImage: "brain.head.profile") }.tag(AppTab.memory)
            tab(.profile) { ProfileView() }.tabItem { Label("我的", systemImage: "person.crop.circle") }.tag(AppTab.profile)
        }
        .tint(Brand.blue)
        .background { SDKEventSyncWorker(connection: store.officialSDK, client: store.client,
                                        active: scenePhase == .active) { await store.refresh() } }
        .background { HardwareExecutorWorker(connection: store.officialSDK, client: store.client, active: scenePhase == .active) }
        .sheet(item: $store.editor, onDismiss: { store.editorRegionCameraID = nil }) { skill in CreateSkillView(skill: skill, initialRegionCameraID: store.editorRegionCameraID).environmentObject(store) }
        .alert("操作未完成", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) { Button("知道了") { store.errorMessage = nil } } message: { Text(store.errorMessage ?? "") }
        .overlay(alignment: .top) {
            if showFeedback, let toast = store.toast { Text(toast).font(.subheadline).padding(14).background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius: 14)).padding().onTapGesture { store.toast = nil }.task(id: toast) { try? await Task.sleep(for: .seconds(3)); store.toast = nil } }
        }
    }
    private func tab<Content: View>(_ tab: AppTab, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack(path: $store.tabPaths[tab.rawValue]) {
            content().navigationDestination(for: AppRoute.self) { route in
                destination(route).toolbar(.hidden, for: .tabBar)
            }
        }
    }
    @ViewBuilder private func destination(_ route: AppRoute) -> some View {
        switch route {
        case .connectedApps: ConnectedAppsView()
        case .cameraObservation: CameraObservationSettingsView()
        case .pushDelivery(let id, let scope): PushDeliveryView(id: id, scope: scope)
        case .pushConversation(let id, let skill, let mode): ConversationView(conversationID: id, skillID: skill, initialMode: mode)
        case .demoScene: DemoSceneView()
        case .skill(let id): SkillDetailView(id: id)
        case .evidence(let id): EvidenceDetailView(id: id)
        case .evidenceList(let skill): EvidenceView(skillID: skill)
        case .cameras: CameraListView()
        case .addDevice: AddDeviceView()
        case .personalAgent: NotificationSettingsView()
        case .personalInbox: PersonalInboxView()
        case .camera(let id): CameraDetailView(id: id)
        case .alerts: AlertsView()
        case .conversation(let id, let skill): ConversationView(conversationID: id, skillID: skill)
        case .evidenceConversation(let id): ConversationView(conversationID: "evidence-" + id, skillID: nil, historyEvidenceID: id)
        case .settings: ServiceSettingsView()
        case .officialSDK: OfficialSDKSettingsView(connection: store.officialSDK)
        case .cameraEvents: CameraSkillsView()
        case .notificationSettings: NotificationSettingsView()
        case .voiceSettings: VoiceSettingsView()
        case .privacy: PrivacyView()
        case .help: HelpView()
        case .profile: EditProfileView()
        case .account: ProfileView()
        case .recordings: RecordingLibraryView()
        case .replayVideo(let id, let offset): RecordingPlayerView(id: id, offset: offset, replayEvidence: true)
        case .video(let id, let offset): RecordingPlayerView(id: id, offset: offset)
        }
    }

}

private struct SDKWorkspaceContainer<Content: View>: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject var connection: OfficialSDKConnection
    @ObservedObject private var push = PushNotifications.shared
    @State private var returningToProduct = false
    @ViewBuilder var content: () -> Content
    var body: some View {
        VStack(spacing: 0) {
            // The vendor workspace is an explicit developer destination. Product
            // pages retain their own navigation without a global mode switch.
            if connection.officialDemoController != nil {
                HStack {
                    Label("摄像头调试", systemImage: "wrench.and.screwdriver").font(.subheadline.bold())
                    Spacer()
                    Button("返回设置") {
                        Task {
                            returningToProduct = true
                            await connection.leaveOfficialWorkspace()
                            store.tabPaths[AppTab.cameraSkills.rawValue] = []
                            store.selectedTab = .profile
                            store.tabPaths[AppTab.profile.rawValue] = [.settings]
                            returningToProduct = false
                            routePush()
                            await store.refresh()
                        }
                    }.font(.caption.bold()).buttonStyle(.bordered)
                        .accessibilityIdentifier("workspace.return")
                }.padding(.horizontal, 16).padding(.vertical, 7).background(.regularMaterial)
                    .disabled(connection.switchingWorkspace || returningToProduct)
            }
            if connection.switchingWorkspace {
                HStack { ProgressView(); Text(connection.workspaceMessage).font(.caption) }.padding(10)
            }
            if let controller = connection.officialDemoController {
                OfficialDemoControllerView(controller: controller).ignoresSafeArea(.keyboard)
                    .allowsHitTesting(!connection.switchingWorkspace)
            } else { content().allowsHitTesting(!connection.switchingWorkspace) }
        }
        .tint(Brand.blue)
        // Stay attached while the product tabs are replaced by the official UI.
        .task(id: store.client.baseURL) {
            push.attach(store.client)
            routePush()
            while !Task.isCancelled {
                if scenePhase == .active { await push.setActive(true) }
                do { try await Task.sleep(for: .seconds(30)) } catch { break }
            }
        }
        .onChange(of: scenePhase) { _, phase in
            routePush()
            Task { await push.setActive(phase == .active) }
        }
        .onChange(of: push.pending) { _, _ in routePush() }
        .onChange(of: store.editor == nil) { _, _ in routePush() }
        .onChange(of: connection.workspaceError) { _, _ in routePush() }
        .onChange(of: connection.switchingWorkspace) { _, _ in routePush() }
        .onChange(of: connection.officialDemoController == nil) { _, _ in routePush() }
        .alert("暂时无法打开官方页面", isPresented: Binding(
            get: { connection.workspaceError != nil },
            set: { if !$0 { connection.workspaceError = nil } }
        )) {
            Button("知道了") { connection.workspaceError = nil }
        } message: { Text(connection.workspaceError ?? "") }
    }
    private func routePush() {
        PushNavigation.consume(&push.pending, selection: &store.selectedTab, paths: &store.tabPaths,
            productVisible: connection.officialDemoController == nil && !connection.switchingWorkspace && !returningToProduct,
            presentationBlocked: connection.workspaceError != nil || store.editor != nil || scenePhase != .active)
    }
}

private struct OfficialDemoControllerView: UIViewControllerRepresentable {
    let controller: UIViewController
    func makeUIViewController(context: Context) -> UIViewController { controller }
    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}

struct OfficialSDKDeveloperView: View {
    @ObservedObject var connection: OfficialSDKConnection
    var body: some View {
        List {
                Section("开发调试") {
                    Text("用于核对配网、绑定和设备设置。日常聊天、任务与提醒不需要打开此页面。")
                    Text(connection.buildStatus).font(.caption).foregroundStyle(Brand.muted)
                    Button("打开官方设备调试页") { Task { await connection.enterOfficialWorkspace() } }
                        .disabled(!connection.canDiscover || connection.switchingWorkspace)
                        .accessibilityIdentifier("settings.openOfficialWorkspace")
                    Text("官方模式加载赛事 Demo 的完整 SampleApp 导航，用于绑定、配网、直播与设备配置。返回后重新查询并同步设备；不会自动恢复直播。")
                    Text("切换的是界面与会话，不会下载或更换底层 SDK 二进制。官方模式采用自己的登录表单与缓存，请核对账号及 PR / QA。")
                }
                Section("T8171 · 云台摄像头") {
                    Label("添加设备：按型号完成官方配网和绑定", systemImage: "wifi")
                    Label("直播：声音、对讲、截图、录像与重连", systemImage: "video")
                    Label("云台：方向、预置位、巡航及追踪设置", systemImage: "arrow.up.and.down.and.arrow.left.and.right")
                    Label("检测、画质、夜视、隐私区、电源与存储", systemImage: "slider.horizontal.3")
                }
                Section("T8214 · 门铃") {
                    Label("添加设备：门铃型号的官方配网和绑定", systemImage: "wifi")
                    Label("直播、镜头布局、门铃呼叫、对讲与快捷回复", systemImage: "bell")
                    Label("铃声、室内响铃、包裹/移动检测与通知", systemImage: "shippingbox")
                    Text("门铃不按云台方向、巡航和预置位验收。实际显示项由型号、固件和能力表决定。")
                }
                Section("两款设备共同检查") {
                    Text("事件 → 回放与下载；设置 → Wi-Fi、时间、分享、OTA、设备信息；Device Capability / Thing Test → 属性、动作和事件。")
                    Text("蓝牙、热点或二维码方式以该型号的添加流程为准。记录同网、跨网、离线、重新唤醒，以及不同账号/客户端并发时的实际结果。")
                    Text("原版页面存在不代表实机支持或测试通过。固件升级、删除/解绑、格式化存储和报警等操作，请逐项阅读官方页面的确认提示。")
                }
                Section("Web 对照") {
                    Text("Web 也可切换到资料包原版 Demo：鉴权表单、官方直播组件、重连和 AI 裸帧面板。当前交付的 Web Demo 没有手机端的完整配网及设置导航；未露出的项目在此 iOS 原版工作区核验。")
                }
        }.pageStyle("摄像头调试")
    }
}
