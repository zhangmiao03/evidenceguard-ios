import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var store: AppStore
    @AppStorage("profileName") private var name = "小安"
    var body: some View {
        List {
            Section {
                NavigationLink(value: AppRoute.profile) { HStack(spacing: 14) { Image("DogAvatar").resizable().scaledToFill().frame(width: 54,height: 54).clipShape(Circle()); VStack(alignment: .leading,spacing: 4) { Text(name).font(.title3.bold()); Text("让生活更安心").font(.subheadline).foregroundStyle(Brand.muted) }; Spacer(); Text("编辑").font(.caption) }.padding(.vertical,8) }
            }
            Section("快捷指令") {
                Button("看看我关注的任务现在怎么样") { store.openAI(prompt: "看看我关注的任务现在怎么样") }
                Button("查询最近的观察记录") { store.openAI(prompt: "查询最近的观察记录") }
                NavigationLink("查看摄像头画面", value: AppRoute.cameras)
            }
            Section {
                NavigationLink(value: AppRoute.cameras) { Label("我的设备",systemImage: "video") }
                NavigationLink(value: AppRoute.officialSDK) { Label("官方摄像头接入",systemImage: "link") }
                NavigationLink(value: AppRoute.notificationSettings) { Label("通知与提醒",systemImage: "bell") }
                NavigationLink(value: AppRoute.voiceSettings) { Label("语音与 AI",systemImage: "waveform") }
                NavigationLink(value: AppRoute.settings) { Label("服务连接",systemImage: "network") }
                NavigationLink(value: AppRoute.privacy) { Label("隐私与数据",systemImage: "hand.raised") }
                NavigationLink(value: AppRoute.help) { Label("帮助与支持",systemImage: "questionmark.circle") }
            }
        }.contentMargins(.top, 12, for: .scrollContent).scrollContentBackground(.hidden).pageStyle("我的")
    }
}
struct EditProfileView: View {
    @AppStorage("profileName") private var name = "小安"
    @State private var draft = ""
    @Environment(\.dismiss) var dismiss
    var body: some View { Form { Section("本机昵称") { TextField("昵称",text: $draft); Text("此资料保存在当前手机，不代表已创建云端账号。").font(.caption).foregroundStyle(Brand.muted) }; Button("保存") { name = String(draft.trimmingCharacters(in: .whitespacesAndNewlines).prefix(30)); dismiss() }.disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }.pageStyle("编辑资料").onAppear { draft = name } }
}
struct ServiceSettingsView: View {
    @EnvironmentObject var store: AppStore
    @State private var address = ""
    @State private var accessToken = ""
    @State private var checking = false
    @State private var feedback: String?
    var body: some View {
        Form {
            Section("云端服务") { TextField("服务地址",text: $address).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("settings.url"); SecureField("团队访问令牌", text: $accessToken).textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("settings.accessToken"); Text("公网服务使用 HTTPS 和团队访问令牌。令牌保存在当前手机 Keychain；本地未启用鉴权的服务可以留空。").font(.caption).foregroundStyle(Brand.muted); Button { Task { checking = true; let ok = await store.configure(address, accessToken: accessToken); feedback = ok ? "已连接到服务" : (store.errorMessage ?? store.lastError ?? "连接失败，请检查地址及服务状态"); checking = false } } label: { HStack { if checking { ProgressView() }; Text("保存并测试连接") } }.disabled(checking); if let feedback { Text(feedback).font(.caption) } }
            Section("AI 模型") { LabeledContent("配置",value: store.data.agent.provider); LabeledContent("状态",value: store.isConnected ? (store.data.agent.ready ? "服务端配置就绪" : "等待服务端配置") : "等待连接"); Text("API Key 仅存于服务端。模型请求失败会在对话中给出原因，不会回退成假回复。").font(.caption).foregroundStyle(Brand.muted) }
            Section("摄像头接入") { NavigationLink("配置官方 SDK 与检查设备", value: AppRoute.officialSDK); Text("已收到 ESIotKit v2.2.7，支持 T8171 / T8214。真机连接与画面能力仍需用主办方账号验收。").font(.caption).foregroundStyle(Brand.muted) }
        }.pageStyle("服务连接").onAppear { address = store.client.baseURL.absoluteString; accessToken = store.client.accessToken }.onChange(of: address) { _, value in if let url = URL(string: value) { accessToken = ServiceAccess.token(for: url) } }
    }
}
struct NotificationSettingsView: View {
    @AppStorage("showFeedback") var feedback = true
    var body: some View { Form { Section { Toggle("应用内操作反馈",isOn: $feedback); Text("关闭后仍在详情页保留操作结果和错误。后台远程推送尚未接入；新告警可在首页“需要关注”查看。").font(.caption).foregroundStyle(Brand.muted) }; NavigationLink("查看待处理事项", value: AppRoute.alerts) }.pageStyle("通知与提醒") }
}
struct VoiceSettingsView: View {
    var body: some View { Form { Section("语音输入") { Text("按住录音 → 松开转写 → 编辑文字 → 发送给 AI。空录音、权限被拒或识别失败都不会创建任务。"); Text("优先使用设备端中文识别；设备不支持时由 Apple 语音服务处理。录音不保存到本应用，发送给 Agent 的是你确认后的文字。").font(.caption).foregroundStyle(Brand.muted); Button("打开系统权限设置") { if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } } }; Section { NavigationLink("检查 AI 服务", value: AppRoute.settings) } }.pageStyle("语音与 AI") }
}
struct PrivacyView: View {
    var body: some View { List { Section("数据流向") { Text("确认发送后，文字与任务上下文会交由已配置的模型服务处理。需要视觉判断时，助手请求所选摄像头的新画面，并将图片交由模型分析。模型提供方与视觉模型以“服务连接”显示的实际配置为准；录像检索可把片段交给已配置的视觉与 Embedding 服务处理。"); Text("任务、对话、执行事件及导入录像保存在你连接的服务端。云端测试环境使用团队共享的数据空间，持有团队访问令牌的成员可以查看已有记录。停止任务后保留既有证据便于回顾。"); Text("手机端不包含模型密钥；团队访问令牌保存在本机 Keychain。公网服务使用 HTTPS 和访问鉴权。真实摄像头 SDK 联调与守护验收仍需完成。") } }.pageStyle("隐私与数据") }
}
struct HelpView: View {
    var body: some View { List { Section("如何创建守护") { Text("1. 在 AI 页按住说话或输入文字。\n2. 编辑转写并发送；根据 AI 追问补充信息。\n3. 打开草案，分别圈选两路区域和主视角目标。\n4. 检查触发条件，确认后启用。") }; Section("三种结果") { Text("已确认：有新鲜的观察依据。\n需要处理：已满足提醒条件。\n无法确认：遮挡、离线、过期或视角冲突，暂不判断。") }; Section("处理与停止") { Text("“我已处理”只发起复核，不能直接变成安全。“暂停”可恢复；“停止”结束当前任务。返回不会隐式启用草案。") } }.pageStyle("帮助与支持") }
}
struct CameraListView: View {
    @EnvironmentObject var store: AppStore
    var body: some View { List { if store.data.cameras.isEmpty { Text("暂无设备，先连接云端服务。"); NavigationLink("服务连接",value: AppRoute.settings) }; ForEach(store.data.cameras) { camera in NavigationLink(value: AppRoute.camera(camera.id)) { VStack(alignment: .leading,spacing: 6) { Text(camera.name).font(.headline); Text("\(camera.model) · \(camera.connectionLabel)").font(.caption).foregroundStyle(Brand.muted); Text(camera.adapter.contains("fixture") ? "测试适配器" : camera.adapter).font(.caption2) } } } }.pageStyle("我的设备").refreshable { await store.refresh() } }
}
struct CameraDetailView: View {
    @EnvironmentObject var store: AppStore
    let id: String
    var body: some View { ScrollView { VStack(alignment: .leading,spacing: 16) {
        ConnectionBanner()
        if let camera = store.camera(id) {
            CameraFrame(camera: camera)
            Text(camera.name).font(.title2.bold()); Text("\(camera.model) · \(camera.connectionLabel)").foregroundStyle(Brand.muted)
            Text("采集时间：\(displayTime(camera.lastCapturedAt))").font(.caption)
            Text(camera.evidence).font(.subheadline)
            ForEach(camera.capabilities.keys.sorted(),id: \.self) { key in HStack { Text(capabilityName(key)); Spacer(); Text(capabilityValue(camera.capabilities[key] ?? "unknown")).foregroundStyle(Brand.muted) } }
            Button { store.selectedCameraID = id; store.openAI() } label: { Label("围绕这个画面交代任务",systemImage: "sparkles") }.buttonStyle(PrimaryAction())
            Button("重新加载画面") { Task { await store.refresh() } }.buttonStyle(.bordered)
        } else { EmptyState(title: "设备信息未就绪",detail: "返回设备列表刷新后重试。") }
    }.padding(16) }.pageStyle("摄像头详情") }
    private func capabilityName(_ key: String) -> String { ["liveSnapshot":"新鲜截图", "storedSnapshot":"历史截图", "liveStream":"实时视频", "eventPush":"设备事件", "ptz":"云台控制"][key] ?? key }
    private func capabilityValue(_ key: String) -> String { ["supported":"支持", "unsupported":"不支持", "unknown":"待验证"][key] ?? key }
}
