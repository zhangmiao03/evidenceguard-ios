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
                if !MobileServiceConfiguration.current.isInternalDemo { NavigationLink(value: AppRoute.officialSDK) { Label("官方摄像头接入",systemImage: "link") } }
                NavigationLink(value: AppRoute.personalAgent) { Label("助手记忆与提醒",systemImage: "sparkles") }
                NavigationLink(value: AppRoute.personalInbox) { Label("助手提醒",systemImage: "tray") }
                if MobileServiceConfiguration.current.isInternalDemo {
                    NavigationLink(value: AppRoute.demoScene) { Label("测试主动守护场景",systemImage: "play.rectangle") }
                }
                NavigationLink(value: AppRoute.notificationSettings) { Label("通知与提醒",systemImage: "bell") }
                NavigationLink(value: AppRoute.voiceSettings) { Label("语音与 AI",systemImage: "waveform") }
                NavigationLink(value: AppRoute.settings) { Label(MobileServiceConfiguration.current.isInternalDemo ? "连接状态" : "服务连接",systemImage: "network") }
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
            if MobileServiceConfiguration.current.isInternalDemo {
                Section {
                    Label(store.isConnected ? "已自动连接" : "正在恢复连接", systemImage: store.isConnected ? "checkmark.circle.fill" : "network")
                        .foregroundStyle(store.isConnected ? Brand.green : Brand.muted)
                    Text("打开 App 即可使用，无需设置服务器或模型。").font(.subheadline).foregroundStyle(Brand.muted)
                    LabeledContent("助手", value: store.isConnected && store.data.agent.ready ? "可以对话" : "暂时不可用")
                    if let error = store.lastError { Text(error).font(.caption).foregroundStyle(.orange) }
                    Button { Task { checking = true; await store.refresh(); checking = false } } label: {
                        HStack { if checking { ProgressView() }; Text("重新连接") }
                    }.disabled(checking)
                }
                Section("内部演示") { Text("使用团队演示空间。设备与录像的测试来源会在页面标明，真实摄像头连接后再完成守护验收。").font(.subheadline) }
            } else {
            Section("云端服务") { TextField("服务地址",text: $address).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("settings.url"); SecureField("团队访问令牌", text: $accessToken).textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("settings.accessToken"); Text("公网服务使用 HTTPS 和团队访问令牌。令牌保存在当前手机 Keychain；本地未启用鉴权的服务可以留空。").font(.caption).foregroundStyle(Brand.muted); Button { Task { checking = true; let ok = await store.configure(address, accessToken: accessToken); feedback = ok ? "已连接到服务" : (store.errorMessage ?? store.lastError ?? "连接失败，请检查地址及服务状态"); checking = false } } label: { HStack { if checking { ProgressView() }; Text("保存并测试连接") } }.disabled(checking); if let feedback { Text(feedback).font(.caption) } }
            Section("AI 模型") { LabeledContent("配置",value: store.data.agent.provider); LabeledContent("状态",value: store.isConnected ? (store.data.agent.ready ? "服务端配置就绪" : "等待服务端配置") : "等待连接"); Text("API Key 仅存于服务端。模型请求失败会在对话中给出原因，不会回退成假回复。").font(.caption).foregroundStyle(Brand.muted) }
            Section("摄像头接入") { NavigationLink("配置官方 SDK 与检查设备", value: AppRoute.officialSDK); Text("已收到 ESIotKit v2.2.7，支持 T8171 / T8214。真机连接与画面能力仍需用主办方账号验收。").font(.caption).foregroundStyle(Brand.muted) }
            }
        }.pageStyle(MobileServiceConfiguration.current.isInternalDemo ? "连接状态" : "服务连接").onAppear { address = store.client.baseURL.absoluteString; accessToken = store.client.accessToken }.onChange(of: address) { _, value in if let url = URL(string: value) { accessToken = ServiceAccess.token(for: url) } }
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
    var body: some View {
        List {
            Section("数据流向") {
                Text("发送后，文字和任务上下文由云端模型处理。需要视觉判断时，相关画面或录像片段也会交给视觉模型分析。手机不保存模型密钥。")
                Text("当前是团队内部演示，任务、对话与录像保存在独立的演示空间，供团队共同测试。请使用测试素材。停止任务后，已有证据仍会保留。")
                Text("连接通过 HTTPS 自动建立。摄像头二维码只用于识别待添加设备；识别成功不代表已绑定或已获得设备控制权。真实设备仍需官方账号核验和守护验收。")
            }
        }.pageStyle("隐私与数据")
    }
}
struct HelpView: View {
    var body: some View { List { Section("如何创建守护") { Text("1. 在 AI 页按住说话或输入文字。\n2. 编辑转写并发送；根据 AI 追问补充信息。\n3. 打开草案，分别圈选两路区域和主视角目标。\n4. 检查触发条件，确认后启用。") }; Section("三种结果") { Text("已确认：有新鲜的观察依据。\n需要处理：已满足提醒条件。\n无法确认：遮挡、离线、过期或视角冲突，暂不判断。") }; Section("处理与停止") { Text("“我已处理”只发起复核，不能直接变成安全。“暂停”可恢复；“停止”结束当前任务。返回不会隐式启用草案。") } }.pageStyle("帮助与支持") }
}
struct CameraListView: View {
    @EnvironmentObject var store: AppStore
    var body: some View { List { NavigationLink(value: AppRoute.addDevice) { Label("扫描添加设备", systemImage: "qrcode.viewfinder") }; if store.data.cameras.isEmpty { Text("暂无已连接设备。添加设备后完成绑定与画面验证。"); }; ForEach(store.data.cameras) { camera in NavigationLink(value: AppRoute.camera(camera.id)) { VStack(alignment: .leading,spacing: 6) { Text(camera.name).font(.headline); Text("\(camera.model) · \(camera.connectionLabel)").font(.caption).foregroundStyle(Brand.muted); Text(camera.adapter.contains("fixture") ? "测试适配器" : camera.adapter).font(.caption2) } } } }.pageStyle("我的设备").refreshable { await store.refresh() } }
}
struct CameraDetailView: View {
    @EnvironmentObject var store: AppStore
    let id: String
    var body: some View { ScrollView { VStack(alignment: .leading,spacing: 16) {
        ConnectionBanner()
        if let camera = store.camera(id) {
            if camera.adapter.hasPrefix("official-relay/") {
                NavigationLink("打开实时视频与 Agent", destination: RegisteredLiveCameraView(deviceID: id)).buttonStyle(.borderedProminent)
            }
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
