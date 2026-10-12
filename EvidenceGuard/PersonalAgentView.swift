import SwiftUI

struct PersonalAgentView: View {
    @EnvironmentObject private var store: AppStore
    @State private var preferences = PersonalPreferences()
    @State private var memory = ""
    @State private var temporary = false
    @State private var loaded = false
    var body: some View {
        Form {
            Section("主动提醒") {
                Toggle("关注摄像头事件与后续变化", isOn: $preferences.enabled)
                Toggle("每日守护概况", isOn: $preferences.dailySummary).disabled(!preferences.enabled)
                Stepper("每日 \(preferences.summaryHour):00", value: $preferences.summaryHour, in: 0...23).disabled(!preferences.dailySummary || !preferences.enabled)
                Stepper("免打扰开始：\(preferences.quietStart):00", value: $preferences.quietStart, in: 0...23)
                Stepper("免打扰结束：\(preferences.quietEnd):00", value: $preferences.quietEnd, in: 0...23)
                Text("使用手机当前时区：\(TimeZone.current.identifier)。助手根据摄像头已有观察和证据主动检查，消息会进入 AI 对话与提醒列表。此版仅应用内通知；不会在锁屏时弹出系统推送。免打扰期间暂存，之后重新核对；起止相同则全天允许提醒。").font(.caption).foregroundStyle(Brand.muted)
                Button("保存提醒偏好") {
                    preferences.timezone = TimeZone.current.identifier
                    let values = preferences
                    Task { await store.perform { store.data.personal = try await store.client.savePreferences(values); store.toast = "提醒偏好已保存" } }
                }.disabled(!loaded || !store.isConnected || store.busy)
                if let error = store.data.personal?.lastError { Text(error).foregroundStyle(.orange) }
            }
            Section("摄像头优先的主动守护") {
                if MobileServiceConfiguration.current.isInternalDemo {
                    NavigationLink("用测试场景验证主动提醒", value: AppRoute.demoScene)
                }
                Label("事件变化 → 核对证据 → 按提醒偏好展示", systemImage: "video")
                Text("助手关注已接收的摄像头事件、Skill 观察记录和未处理事项，不会另外抢占摄像头。模型评估信息价值，免打扰、每天最多6条普通提醒、至少5分钟间隔和同类合并由固定规则执行。每日概况需单独开启。没有正在运行的守护时，不会假装正在看现场。").font(.caption).foregroundStyle(Brand.muted)
                Text("助手只建议或请求你配合；启用、替换 Skill 仍需要你确认。飞书、日历暂未接入。").font(.caption).foregroundStyle(Brand.muted)
            }
            Section("最近的后台检查") {
                if store.data.personal?.activity?.isEmpty ?? true {
                    Text("尚无待检查事项。开启主动提醒后，摄像头任务产生新变化时会显示在这里。").foregroundStyle(Brand.muted)
                }
                ForEach(Array((store.data.personal?.activity ?? []).prefix(8))) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.statusLabel).font(.subheadline.bold())
                        Text(item.reason).font(.caption).foregroundStyle(Brand.muted)
                    }
                }
            }
            Section("告诉助手需要记住什么") {
                TextField("例如：回复简洁一些，先说需要我做什么", text: $memory, axis: .vertical).lineLimit(2...4)
                Toggle("仅保留 24 小时", isOn: $temporary)
                Text("当天心情等临时情况可开启 24 小时有效期。只保存你主动确认的内容，不从摄像头推断心情。当前仍是团队演示空间，请使用测试信息。").font(.caption).foregroundStyle(Brand.muted)
                Button("确认记住") {
                    let content = memory.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task { await store.perform { store.data.personal = try await store.client.remember(content, temporary: temporary); memory = ""; store.toast = "已记住，可随时移除" } }
                }.disabled(memory.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || memory.count > 500 || !store.isConnected || store.busy)
            }
            Section("已确认的记忆") {
                if store.data.personal?.memories.isEmpty ?? true { Text("尚未保存记忆").foregroundStyle(Brand.muted) }
                ForEach(store.data.personal?.memories ?? []) { item in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.content)
                        Text(item.expiresAt.map { "有效至 " + displayTime($0) } ?? "保留至你主动移除").font(.caption).foregroundStyle(Brand.muted)
                        Button("移除这条记忆", role: .destructive) { Task { await store.perform { store.data.personal = try await store.client.forget(item.id) } } }.font(.caption).disabled(store.busy)
                    }
                }
            }
            Section { NavigationLink("查看助手提醒", value: AppRoute.personalInbox) }
        }.pageStyle("助手记忆与提醒")
            .task { await store.refresh(); if let snapshot = store.data.personal { preferences = snapshot.preferences; loaded = true } }
            .onChange(of: store.data.personal?.revision) { _, _ in
                if !loaded, let snapshot = store.data.personal { preferences = snapshot.preferences; loaded = true }
            }
    }
}

struct DemoSceneView: View {
    @EnvironmentObject private var store: AppStore
    @State private var snapshot: DemoSceneSnapshot?
    @State private var scenario = "parcel_absent"
    @State private var starting = false
    @State private var requestID: String?
    @State private var requestScenario: String?
    @State private var error: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Label("主动守护 · 测试场景", systemImage: "sparkles").font(.title2.bold())
                    Text("三张合成图片模拟 0s、3s、6s 的门廊状态。实际调用视觉模型和助手，再由免打扰、评分、频率规则决定是否提醒。测试不会绑定设备或启用真实 Skill。").font(.subheadline).foregroundStyle(Brand.muted)
                }
                VStack(alignment: .leading, spacing: 12) {
                    Picker("测试场景", selection: $scenario) {
                        Text("包裹离区").tag("parcel_absent")
                        Text("区域遮挡").tag("occluded")
                        Text("没有变化").tag("unchanged")
                    }.pickerStyle(.segmented).disabled(starting || snapshot?.scenes.first?.isRunning == true)
                    Text("观察目标：门廊纸箱。关注区域是蓝框；这里只比较离散样本，不确认拿走动作或责任人。").font(.caption).foregroundStyle(Brand.muted)
                    if store.data.personal?.preferences.enabled != true {
                        Button("开启应用内主动提醒") {
                            var p = store.data.personal?.preferences ?? PersonalPreferences()
                            p.enabled = true; p.timezone = TimeZone.current.identifier
                            Task { await store.perform { store.data.personal = try await store.client.savePreferences(p) } }
                        }.buttonStyle(.bordered).disabled(!store.isConnected || store.busy)
                        Text("提醒未开启时仍能测试视觉核验，只保留证据。").font(.caption).foregroundStyle(Brand.muted)
                    }
                    NavigationLink("查看免打扰和提醒偏好", value: AppRoute.personalAgent).font(.caption)
                    Button { Task { await start() } } label: {
                        Label(starting ? "正在提交…" : "开始测试", systemImage: "play.fill").frame(maxWidth: .infinity)
                    }.buttonStyle(PrimaryAction()).disabled(starting || snapshot?.enabled != true || !store.isConnected || snapshot?.scenes.first?.isRunning == true)
                    Text("每台手机每天最多 6 次测试。此处无强制推送或预设模型答案。").font(.caption2).foregroundStyle(Brand.muted)
                }.padding(16).cardStyle()
                if let error { Text(error).font(.subheadline).foregroundStyle(.orange) }
                if snapshot?.enabled == false { Text("当前服务未启用测试场景，请联系团队更新测试版。").foregroundStyle(.orange) }
                ForEach(snapshot?.scenes ?? []) { scene in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack { Text(scene.title).font(.headline); Spacer(); if scene.isRunning { ProgressView() } }
                        Text(scene.label).font(.caption.bold()).foregroundStyle(Brand.blue)
                        Text(scene.policyReason ?? scene.reason).font(.subheadline)
                        if let score = scene.valueScore { Text("信息价值 \(score)/100 · \(scene.deliveryLabel)").font(.caption).foregroundStyle(Brand.muted) }
                        if let draft = scene.assistantDraft, scene.policyStatus == "digest" {
                            GroupBox("助手草稿 · 尚未发出") { Text(draft).font(.subheadline).frame(maxWidth: .infinity, alignment: .leading) }
                        }
                        ForEach(scene.samples) { sample in
                            NavigationLink(value: AppRoute.evidence(sample.id)) {
                                VStack(alignment: .leading, spacing: 5) {
                                    EvidenceImage(url: store.client.absoluteURL(sample.imageUrl))
                                    Label("模拟 \(sample.relativeSeconds)s · 查看证据", systemImage: "photo").font(.caption)
                                }
                            }.buttonStyle(.plain)
                        }
                        if scene.policyStatus == "sent" || scene.policyStatus == "merged" {
                            Button("进入助手主对话，继续追问") {
                                store.selectConversation(store.generalConversation)
                                store.tabPaths[2] = []; store.selectedTab = 2
                            }.buttonStyle(.borderedProminent)
                        }
                        Text("合成测试 · 生成于 \(displayTime(scene.createdAt)) · 非真实摄像头采集时间").font(.caption2).foregroundStyle(Brand.muted)
                    }.padding(16).cardStyle()
                }
            }.padding(16)
        }.pageStyle("测试主动守护")
        .task {
            while !Task.isCancelled {
                do { snapshot = try await store.client.demoScenes(); error = nil }
                catch { if !Task.isCancelled { self.error = "测试状态暂未同步，请稍后重试。" } }
                do { try await Task.sleep(for: .seconds(2)) } catch { break }
            }
        }
    }
    private func start() async {
        starting = true; defer { starting = false }
        if requestScenario != scenario { requestID = nil }
        let id = requestID ?? UUID().uuidString; requestID = id; requestScenario = scenario
        do {
            _ = try await store.client.startDemoScene(requestID: id, scenario: scenario)
            requestID = nil; error = nil
            snapshot = try await store.client.demoScenes(); await store.refresh()
        } catch { self.error = error.localizedDescription }
    }
}

struct PersonalInboxView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        List {
            Section {
                NavigationLink("提醒偏好与记忆", value: AppRoute.personalAgent)
                Button("进入 AI 对话继续处理") { store.selectedTab = 2; store.tabPaths[2] = [] }
            }
            if store.data.personal?.inbox.isEmpty ?? true {
                Text("暂时没有助手提醒。开启后，新的任务事件、未处理事项的后续提醒和每日概况会出现在这里。")
                    .foregroundStyle(Brand.muted)
            }
            ForEach(store.data.personal?.inbox ?? []) { notice in
                VStack(alignment: .leading, spacing: 8) {
                    HStack { Text(notice.title).font(.headline); if !notice.read { Circle().fill(Brand.blue).frame(width: 7, height: 7) } }
                    Text(notice.body).font(.subheadline)
                    Text("\(notice.kindLabel) · \(displayTime(notice.createdAt))").font(.caption).foregroundStyle(Brand.muted)
                    if let id = notice.skillId { NavigationLink("查看任务和证据", value: AppRoute.skill(id)) }
                    if !notice.read { Button("标记已读") { Task { await store.perform { store.data.personal = try await store.client.readNotice(notice.id) } } }.disabled(store.busy) }
                }.padding(.vertical, 8)
            }
        }.pageStyle("助手提醒").refreshable { await store.refresh() }
    }
}

struct ProactiveMessageCard: View {
    @EnvironmentObject private var store: AppStore
    let message: AssistantMessage
    var onReply: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("助手主动提醒", systemImage: "sparkles").font(.caption.bold()).foregroundStyle(Brand.blue)
                Spacer()
                if !message.read { Circle().fill(Brand.blue).frame(width: 7, height: 7) }
            }
            Text(message.title).font(.headline)
            Text(message.body).textSelection(.enabled)
            Text(displayTime(message.createdAt)).font(.caption2).foregroundStyle(Brand.muted)
            DisclosureGroup("为什么提醒我") {
                VStack(alignment: .leading, spacing: 8) {
                    Text(message.why).font(.caption)
                    ForEach(message.sources) { source in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(source.name ?? source.title ?? source.reason ?? "已记录的摄像头观察").font(.caption)
                            if let at = source.observedAt { Text("记录于 " + displayTime(at)).font(.caption2).foregroundStyle(Brand.muted) }
                            if let id = source.evidenceId { NavigationLink("查看这条证据", value: AppRoute.evidence(id)).font(.caption) }
                            if let limitation = source.limitation { Text(limitation).font(.caption2).foregroundStyle(Brand.muted) }
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.font(.caption).tint(Brand.muted)
            if let skill = message.skillId { NavigationLink("查看任务与画面", value: AppRoute.skill(skill)).font(.subheadline) }
            HStack {
                Button("继续沟通") { respond("read"); onReply() }.buttonStyle(.borderedProminent)
                if message.feedback == "handled" { Text("已处理此提醒").font(.caption).foregroundStyle(Brand.muted) }
                else {
                    Menu("处理提醒") {
                        Button("我已处理") { respond("handled") }
                        Button("1 小时后再提醒") { respond("snooze") }
                        Button("不再提醒此事件") { respond("dismiss") }
                    }
                }
            }.disabled(store.busy)
            if message.feedback == "handled" { Text("已记下你的反馈；摄像头告警仍以新观察为准。").font(.caption2).foregroundStyle(Brand.muted) }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(.white).clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Brand.blue.opacity(0.15), lineWidth: 1))
            .accessibilityIdentifier("chat.proactive.\(message.id)")
    }
    private func respond(_ action: String) {
        Task { await store.perform { store.data.personal = try await store.client.messageFeedback(message.id, action: action) } }
    }
}
