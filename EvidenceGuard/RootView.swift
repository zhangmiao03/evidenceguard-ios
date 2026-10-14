import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var push = PushNotifications.shared
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
        .task { await store.poll() }
        .task(id: store.client.baseURL) {
            push.attach(store.client)
            routePush()
            while !Task.isCancelled {
                if scenePhase == .active { await push.setActive(true) }
                do { try await Task.sleep(for: .seconds(30)) } catch { break }
            }
        }
        .onChange(of: scenePhase) { _, phase in Task { await push.setActive(phase == .active) } }
        .onChange(of: push.pending) { _, _ in routePush() }
        .onChange(of: store.editor == nil) { _, _ in routePush() }
        .sheet(item: $store.editor, onDismiss: { store.editorRegionCameraID = nil }) { skill in CreateSkillView(skill: skill, initialRegionCameraID: store.editorRegionCameraID).environmentObject(store) }
        .alert("操作未完成", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) { Button("知道了") { store.errorMessage = nil } } message: { Text(store.errorMessage ?? "") }
        .overlay(alignment: .top) {
            if showFeedback, let toast = store.toast { Text(toast).font(.subheadline).padding(14).background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius: 14)).padding().onTapGesture { store.toast = nil }.task(id: toast) { try? await Task.sleep(for: .seconds(3)); store.toast = nil } }
        }
    }
    private func routePush() {
        guard let tap = push.pending, store.editor == nil else { return }
        store.selectedTab = .assistant
        store.tabPaths[AppTab.assistant.rawValue].append(.pushDelivery(tap.id, tap.scope))
        push.pending = nil
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
