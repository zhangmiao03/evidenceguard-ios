import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var store: AppStore
    @AppStorage("profileName") private var name = "小安"
    var body: some View {
        List {
            Section {
                NavigationLink(value: AppRoute.profile) { HStack(spacing: 14) { Image("DogAvatar").resizable().scaledToFill().frame(width: 54,height: 54).clipShape(Circle()); VStack(alignment: .leading,spacing: 4) { Text(name).font(.title3.bold()); Text("让生活更安心").font(.subheadline).foregroundStyle(Brand.muted) }; Spacer(); Text("编辑").font(.caption) }.padding(.vertical,8) }
            }
            Section("助手") {
                NavigationLink(value: AppRoute.notificationSettings) { Label("通知与提醒", systemImage: "bell") }
                    .accessibilityIdentifier("profile.notifications")
                NavigationLink(value: AppRoute.voiceSettings) { Label("语音输入", systemImage: "waveform") }
            }
            Section("设置与帮助") {
                NavigationLink(value: AppRoute.settings) { Label(MobileServiceConfiguration.current.isInternalDemo ? "连接状态" : "服务连接", systemImage: "network") }
                NavigationLink(value: AppRoute.privacy) { Label("隐私与数据", systemImage: "hand.raised") }
                NavigationLink(value: AppRoute.help) { Label("使用帮助", systemImage: "questionmark.circle") }
            }
            Section("测试与联调") {
                if MobileServiceConfiguration.current.isInternalDemo {
                    NavigationLink(value: AppRoute.demoScene) { Label("合成场景演示", systemImage: "play.rectangle") }
                }
                if !MobileServiceConfiguration.current.isInternalDemo {
                    NavigationLink(value: AppRoute.officialSDK) { Label("官方摄像头接入", systemImage: "link") }
                }
                NavigationLink(value: AppRoute.personalInbox) { Label("提醒记录", systemImage: "tray") }
            }
        }.contentMargins(.top, 12, for: .scrollContent).scrollContentBackground(.hidden).agentPageStyle("我的", largeTitle: true)
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
    @EnvironmentObject var store: AppStore
    var body: some View { NotificationSettingsContent(settings: store.reminderSettings) }
}

private struct NotificationSettingsContent: View {
    @EnvironmentObject var store: AppStore
    @ObservedObject var settings: ReminderSettings
    @ObservedObject private var push = PushNotifications.shared
    @AppStorage("showFeedback") var feedback = true
    private func preference<Value>(_ key: WritableKeyPath<PersonalPreferences, Value>) -> Binding<Value> {
        Binding(get: { settings.preferences[keyPath: key] }, set: { settings.update(key, to: $0) })
    }
    private var phoneStatus: String {
        if !push.wanted { return "已关闭" }
        if !push.allowed { return "等待系统允许" }
        if push.status?.serverReady == false { return "服务正在准备" }
        return push.status?.enabled == true ? "已开启" : "正在连接"
    }
    var body: some View {
        Form {
            Section("手机通知") {
                Toggle("手机推送", isOn: Binding(get: { push.wanted }, set: { wanted in
                    Task { if wanted { await push.enable() } else { await push.disable() } }
                })).disabled(push.busy).accessibilityIdentifier("notifications.phone")
                LabeledContent("状态", value: phoneStatus)
                if push.authorization == .denied {
                    Button("前往系统设置允许通知") { openSystemSettings() }
                }
                if !push.wanted && push.status?.enabled == true { Text("正在同步关闭，请保持网络连接。").font(.caption).foregroundStyle(Brand.muted) }
                Text("离开 App 后接收提醒、耗时任务结果和待确认草案。首次开启会弹出 iOS 授权窗口；锁屏只显示简短提示。").font(.caption).foregroundStyle(Brand.muted)
                if let error = push.error { Text(error).foregroundStyle(.orange).font(.caption) }
            }
            Section("助手主动提醒") {
                Toggle("摄像头事件与后续变化", isOn: preference(\.enabled))
                    .accessibilityIdentifier("notifications.proactive")
                Toggle("每日守护概况", isOn: preference(\.dailySummary))
                    .disabled(!settings.preferences.enabled).accessibilityIdentifier("notifications.daily")
                if settings.preferences.dailySummary && settings.preferences.enabled {
                    Stepper("每日 \(settings.preferences.summaryHour):00", value: preference(\.summaryHour), in: 0...23)
                        .accessibilityIdentifier("notifications.summaryHour")
                }
                Text("根据已接收的事件、守护记录和待处理事项提醒你。开启提醒不会自动启动摄像头守护。").font(.caption).foregroundStyle(Brand.muted)
            }.disabled(!settings.loaded || settings.loading)
            Section("免打扰") {
                Stepper("开始：\(settings.preferences.quietStart):00", value: preference(\.quietStart), in: 0...23)
                    .accessibilityIdentifier("notifications.quietStart")
                Stepper("结束：\(settings.preferences.quietEnd):00", value: preference(\.quietEnd), in: 0...23)
                    .accessibilityIdentifier("notifications.quietEnd")
                Text("使用手机当前时区。免打扰期间暂存，之后重新核对；起止相同则全天允许提醒。普通提醒每天最多 6 条，间隔至少 5 分钟。").font(.caption).foregroundStyle(Brand.muted)
            }.disabled(!settings.loaded || settings.loading)
            Section {
                if settings.loading || settings.saving {
                    Label(settings.saving ? "正在保存更改…" : "正在读取设置…", systemImage: "arrow.triangle.2.circlepath")
                } else if let error = settings.error {
                    Text(error).foregroundStyle(.orange)
                    Button("重试") { if settings.loaded { settings.retry() } else { Task { await settings.load(store) } } }
                } else {
                    Label(settings.savedOnce ? "已自动保存" : "调整后自动保存", systemImage: settings.savedOnce ? "checkmark.circle" : "arrow.triangle.2.circlepath")
                }
            }.font(.caption).foregroundStyle(Brand.muted).accessibilityIdentifier("notifications.saveState")
            Section {
                NavigationLink("查看提醒记录", value: AppRoute.personalInbox)
                DisclosureGroup("提醒依据与后台检查") {
                    Text("没有运行中的守护时，助手不会假装正在看现场。摄像头接入和具体守护仍需在摄像头 Skill 中设置。").font(.caption)
                    if store.data.personal?.activity?.isEmpty ?? true { Text("暂无待检查事项。").font(.caption).foregroundStyle(Brand.muted) }
                    ForEach(Array((store.data.personal?.activity ?? []).prefix(5))) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.statusLabel).font(.subheadline)
                            Text(item.reason).font(.caption).foregroundStyle(Brand.muted)
                        }
                    }
                }
            }
            Section {
                DisclosureGroup("测试通知与连接检查") {
                    LabeledContent("系统权限", value: push.permissionLabel)
                    Button("向这台手机发送测试通知") { Task { await push.test() } }
                        .disabled(push.busy || !push.allowed || push.status?.enabled != true || push.status?.serverReady != true)
                    if let message = push.feedback { Text(message).font(.subheadline) }
                    if let status = push.status { LabeledContent("最近一次", value: status.deliveryLabel) }
                    Text("测试通知不受免打扰时段限制。手机网络和系统专注模式会影响显示。").font(.caption).foregroundStyle(Brand.muted)
                    Button("刷新通知状态") { Task { await push.sync() } }.disabled(push.busy)
                }
                Toggle("应用内操作反馈", isOn: $feedback)
            }
        }.pageStyle("通知与提醒").task {
            push.attach(store.client)
            async let phone: Void = push.sync()
            await settings.load(store)
            await phone
        }
    }
    private func openSystemSettings() { if let url = URL(string: UIApplication.openNotificationSettingsURLString) { UIApplication.shared.open(url) } }
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
    var body: some View { List { Section("如何创建守护") { Text("1. 在助手中输入或说出需求。\n2. 打开草案，确认对象与区域。\n3. 检查条件和可用能力，完成必要测试。\n4. 确认后开始；未就绪时保留草案。") }; Section("三种结果") { Text("已确认：有新鲜的观察依据。\n需要处理：已满足提醒条件。\n无法确认：遮挡、离线、过期或视角冲突，暂不判断。") }; Section("处理与停止") { Text("“我已处理”只发起复核，不能直接变成安全。“暂停”可恢复；“停止”结束当前任务。返回不会隐式启用草案。") } }.pageStyle("帮助与支持") }
}
struct CameraListView: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        List {
            Section {
                ConnectionBanner()
                NavigationLink(value: AppRoute.addDevice) { Label("添加设备", systemImage: "qrcode.viewfinder") }
                    .accessibilityIdentifier("devices.add")
            }
            Section("我的摄像头") {
                if store.data.cameras.isEmpty { Text("添加摄像头后，在助手中告诉我想关注什么。").foregroundStyle(Brand.muted) }
                ForEach(store.data.cameras) { camera in
                    NavigationLink(value: AppRoute.camera(camera.id)) {
                        HStack(spacing: 12) {
                            Image(systemName: "video").foregroundStyle(Brand.blue).frame(width: 32)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(camera.name).font(.headline)
                                Text(camera.model + " · " + camera.connectionLabel).font(.caption).foregroundStyle(Brand.muted)
                                if camera.adapter.contains("fixture") { Text("合成测试设备").font(.caption2).foregroundStyle(.orange) }
                            }
                        }.padding(.vertical, 7)
                    }.accessibilityIdentifier("devices." + camera.id)
                }
            }
            Section {
                NavigationLink(value: AppRoute.recordings) { Label("录像库", systemImage: "film") }
            }
        }.scrollContentBackground(.hidden).pageStyle("设备").refreshable { await store.refresh() }
    }
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
