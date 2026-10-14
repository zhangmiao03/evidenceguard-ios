import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        SDKWorkspaceContainer(connection: store.officialSDK) { ProductRootView() }
            .task { await store.poll() }
    }
}

private struct ProductRootView: View {
    @EnvironmentObject private var store: AppStore
    @AppStorage("showFeedback") private var showFeedback = true
    var body: some View {
        TabView(selection: $store.selectedTab) {
            tab(0) { HomeView() }.tabItem { Label("首页", systemImage: "house.fill") }.tag(0)
            tab(1) { SkillsView() }.tabItem { Label("Skill", systemImage: "square.3.layers.3d") }.tag(1)
            tab(2) { TeachAIView() }.tabItem { Label("AI", systemImage: "sparkles") }.badge(store.unreadAssistantCount).tag(2)
            tab(3) { EvidenceView() }.tabItem { Label("证据", systemImage: "doc.text.image") }.tag(3)
            tab(4) { ProfileView() }.tabItem { Label("我的", systemImage: "person.fill") }.tag(4)
        }
        .tint(Brand.blue)
        .sheet(item: $store.editor, onDismiss: { store.editorRegionCameraID = nil }) { skill in CreateSkillView(skill: skill, initialRegionCameraID: store.editorRegionCameraID).environmentObject(store) }
        .alert("操作未完成", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) { Button("知道了") { store.errorMessage = nil } } message: { Text(store.errorMessage ?? "") }
        .overlay(alignment: .top) {
            if showFeedback, let toast = store.toast { Text(toast).font(.subheadline).padding(14).background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius: 14)).padding().onTapGesture { store.toast = nil }.task(id: toast) { try? await Task.sleep(for: .seconds(3)); store.toast = nil } }
        }
    }
    private func tab<Content: View>(_ index: Int, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack(path: $store.tabPaths[index]) {
            content().navigationDestination(for: AppRoute.self) { route in
                destination(route).toolbar(.hidden, for: .tabBar)
            }
        }
    }
    @ViewBuilder private func destination(_ route: AppRoute) -> some View {
        switch route {
        case .demoScene: DemoSceneView()
        case .skill(let id): SkillDetailView(id: id)
        case .evidence(let id): EvidenceDetailView(id: id)
        case .evidenceList(let skill): EvidenceView(skillID: skill)
        case .cameras: CameraListView()
        case .addDevice: AddDeviceView()
        case .personalAgent: PersonalAgentView()
        case .personalInbox: PersonalInboxView()
        case .camera(let id): CameraDetailView(id: id)
        case .alerts: AlertsView()
        case .conversation(let id, let skill): ConversationView(conversationID: id, skillID: skill)
        case .evidenceConversation(let id): ConversationView(conversationID: "evidence-" + id, skillID: nil, historyEvidenceID: id)
        case .settings: ServiceSettingsView()
        case .officialSDK: OfficialSDKSettingsView(connection: store.officialSDK)
        case .notificationSettings: NotificationSettingsView()
        case .voiceSettings: VoiceSettingsView()
        case .privacy: PrivacyView()
        case .help: HelpView()
        case .profile: EditProfileView()
        case .recordings: RecordingLibraryView()
        case .replayVideo(let id, let offset): RecordingPlayerView(id: id, offset: offset, replayEvidence: true)
        case .video(let id, let offset): RecordingPlayerView(id: id, offset: offset)
        }
    }

}

private struct SDKWorkspaceContainer<Content: View>: View {
    @EnvironmentObject private var store: AppStore
    @ObservedObject var connection: OfficialSDKConnection
    @State private var guide = false
    @ViewBuilder var content: () -> Content
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: connection.officialDemoController == nil ? "shield.lefthalf.filled" : "wrench.and.screwdriver")
                Text(connection.officialDemoController == nil ? "EvidenceGuard" : "官方 SDK 原版").font(.subheadline.bold())
                Spacer()
                Button { guide = true } label: { Image(systemName: "checklist") }.accessibilityLabel("硬件检查指引")
                Button(connection.officialDemoController == nil ? "切换官方 SDK" : "返回本项目") {
                    if connection.officialDemoController == nil {
                        if connection.canDiscover { Task { await connection.enterOfficialWorkspace() } }
                        else { guide = true }
                    } else {
                        Task {
                            await connection.leaveOfficialWorkspace()
                            store.tabPaths = Array(repeating: [], count: 5)
                            store.selectedTab = 4; store.tabPaths[4] = [.officialSDK]
                            await store.refresh()
                        }
                    }
                }.font(.caption.bold()).buttonStyle(.bordered)
                    .accessibilityIdentifier("workspace.switch")
            }.padding(.horizontal, 16).padding(.vertical, 7).background(.regularMaterial)
                .disabled(connection.switchingWorkspace || store.editor != nil)
            if connection.switchingWorkspace {
                HStack { ProgressView(); Text(connection.workspaceMessage).font(.caption) }.padding(10)
            }
            if let controller = connection.officialDemoController {
                OfficialDemoControllerView(controller: controller).ignoresSafeArea(.keyboard)
                    .allowsHitTesting(!connection.switchingWorkspace)
            } else { content().allowsHitTesting(!connection.switchingWorkspace) }
        }
        .tint(Brand.blue)
        .sheet(isPresented: $guide) { OfficialWorkspaceGuide(connection: connection) }
    }
}

private struct OfficialDemoControllerView: UIViewControllerRepresentable {
    let controller: UIViewController
    func makeUIViewController(context: Context) -> UIViewController { controller }
    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}

private struct OfficialWorkspaceGuide: View {
    @ObservedObject var connection: OfficialSDKConnection
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                Section("工作区切换") {
                    Text(connection.buildStatus)
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
            }.navigationTitle("官方 SDK 检查指引").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
    }
}
