import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    @AppStorage("showFeedback") private var showFeedback = true
    var body: some View {
        TabView(selection: $store.selectedTab) {
            tab(0) { HomeView() }.tabItem { Label("首页", systemImage: "house.fill") }.tag(0)
            tab(1) { SkillsView() }.tabItem { Label("Skill", systemImage: "square.3.layers.3d") }.tag(1)
            tab(2) { TeachAIView() }.tabItem { Label("AI", systemImage: "sparkles") }.tag(2)
            tab(3) { EvidenceView() }.tabItem { Label("证据", systemImage: "doc.text.image") }.tag(3)
            tab(4) { ProfileView() }.tabItem { Label("我的", systemImage: "person.fill") }.tag(4)
        }
        .tint(Brand.blue)
        .task { await store.poll() }
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
        case .skill(let id): SkillDetailView(id: id)
        case .evidence(let id): EvidenceDetailView(id: id)
        case .evidenceList(let skill): EvidenceView(skillID: skill)
        case .cameras: CameraListView()
        case .camera(let id): CameraDetailView(id: id)
        case .alerts: AlertsView()
        case .conversation(let id, let skill): ConversationView(conversationID: id, skillID: skill)
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
