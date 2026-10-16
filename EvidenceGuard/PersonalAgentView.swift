import SwiftUI

struct MemoryView: View {
    @EnvironmentObject private var store: AppStore
    @State private var filter = "all"
    @State private var adding = false
    @State private var pendingRemoval: PersonalMemory?
    @State private var showRemoval = false
    private var memories: [PersonalMemory] {
        (store.data.personal?.memories ?? []).filter { $0.expiresAt.map { $0 > Date().timeIntervalSince1970 } ?? true }
            .sorted { $0.createdAt > $1.createdAt }
    }
    private var filtered: [PersonalMemory] {
        memories.filter { filter == "all" || (filter == "temporary" ? $0.expiresAt != nil : $0.expiresAt == nil) }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                ConnectionBanner()
                VStack(alignment: .leading, spacing: 14) {
                    Text("我记下的事").font(.title3.bold())
                    Text("记下你的关注点和沟通偏好，下次对话时继续使用。")
                        .font(.subheadline).foregroundStyle(Brand.muted)
                    Button { adding = true } label: {
                        HStack { Label("添加一条记忆", systemImage: "plus"); Spacer(); Image(systemName: "chevron.right").font(.caption) }
                            .font(.subheadline.weight(.medium)).padding(15).background(.white.opacity(0.8)).clipShape(RoundedRectangle(cornerRadius: 16))
                    }.buttonStyle(.plain).foregroundStyle(Brand.blue).accessibilityIdentifier("memory.add")
                    Text("手动添加的临时情况可设置为 24 小时有效。")
                        .font(.caption).foregroundStyle(Brand.muted)
                }.padding(20).background(Brand.paleBlue.opacity(0.86)).clipShape(RoundedRectangle(cornerRadius: 24))
                if let automatic = store.data.personal?.automaticMemory {
                    VStack(alignment: .leading, spacing: 10) {
                        Toggle("聊天后自动整理记忆", isOn: Binding(get: { automatic.enabled }, set: { value in
                            Task { await store.perform { store.data.personal = try await store.client.configureMemory(value) } }
                        })).disabled(store.busy || !store.isConnected).accessibilityIdentifier("memory.automatic")
                        Text(automatic.reason).font(.caption).foregroundStyle(Brand.muted)
                        Text("仅整理你明确说出的偏好和家庭信息；关闭后已有记忆仍保留。").font(.caption).foregroundStyle(Brand.muted)
                        if automatic.status == "failed" {
                            Button("重试记忆整理") { Task { await store.perform { store.data.personal = try await store.client.retryMemory() } } }
                                .disabled(store.busy || !store.isConnected)
                        }
                    }.padding(18).background(.white.opacity(0.85)).clipShape(RoundedRectangle(cornerRadius: 22))
                }
                HStack {
                    Text("已保存的记忆").font(.headline)
                    Spacer()
                    Text("\(memories.count) 条").font(.caption).foregroundStyle(Brand.muted)
                }
                Picker("记忆类型", selection: $filter) {
                    Text("全部").tag("all"); Text("长期").tag("longterm"); Text("临时").tag("temporary")
                }.pickerStyle(.segmented).accessibilityIdentifier("memory.filter")
                if filtered.isEmpty {
                    Text(memories.isEmpty ? "还没有保存的记忆。可以先告诉我：你最关心什么，或希望我怎样回复。" : "这里还没有这类记忆。")
                        .font(.subheadline).foregroundStyle(Brand.muted).padding(20)
                        .frame(maxWidth: .infinity, alignment: .leading).background(.white.opacity(0.78)).clipShape(RoundedRectangle(cornerRadius: 22))
                }
                ForEach(filtered) { item in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label(item.expiresAt == nil ? "长期记忆" : "临时记忆", systemImage: item.expiresAt == nil ? "bookmark" : "clock")
                                .font(.caption.weight(.medium)).foregroundStyle(Brand.blue)
                            Spacer()
                            Menu {
                                Button("移除这条记忆", role: .destructive) { pendingRemoval = item; showRemoval = true }
                            } label: { Image(systemName: "ellipsis").frame(width: 32, height: 32) }
                                .accessibilityLabel("管理这条记忆").disabled(store.busy || !store.isConnected)
                        }
                        Text(item.content).font(.body).textSelection(.enabled)
                        Text(item.source == "conversation" ? "来源：对话自动整理" : "来源：手动添加").font(.caption).foregroundStyle(Brand.muted)
                        if let quote = item.sourceQuote {
                            DisclosureGroup("查看用户原话") { Text(quote).font(.caption).textSelection(.enabled) }
                        }
                        Text(item.expiresAt.map { "有效至 " + displayTime($0) } ?? "保存于 " + displayTime(item.createdAt))
                            .font(.caption).foregroundStyle(Brand.muted)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(.white.opacity(0.85)).clipShape(RoundedRectangle(cornerRadius: 22))
                        .accessibilityIdentifier("memory.item.\(item.id)")
                }
                Text("当前为团队演示空间，请使用测试信息。记忆不会自动启用或修改摄像头任务。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }.padding(20)
        }.agentPageStyle("记忆", largeTitle: true)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { adding = true } label: { Image(systemName: "plus") }
                        .accessibilityLabel("添加记忆").accessibilityIdentifier("memory.new")
                }
            }
            .sheet(isPresented: $adding) { MemoryComposerView() }
            .alert("移除这条记忆？", isPresented: $showRemoval, presenting: pendingRemoval) { item in
                Button("移除", role: .destructive) {
                    Task { await store.perform { store.data.personal = try await store.client.forget(item.id); store.toast = "已移除这条记忆" } }
                }
                Button("取消", role: .cancel) {}
            } message: { item in Text(item.content) }
            .refreshable { await store.refresh() }
    }
}

private struct MemoryComposerView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var content = ""
    @State private var temporary = false
    @State private var saving = false
    @State private var error: String?
    @State private var discard = false
    private var cleaned: String { content.trimmingCharacters(in: .whitespacesAndNewlines) }
    var body: some View {
        NavigationStack {
            Form {
                Section("希望助手记住什么") {
                    TextField("例如：回复简洁一些，先说需要我做什么", text: $content, axis: .vertical)
                        .lineLimit(4...8).accessibilityIdentifier("memory.content")
                    Text("\(content.count)/500").font(.caption).foregroundStyle(content.count > 500 ? .orange : Brand.muted)
                }
                Section("保存多久") {
                    Toggle("仅保留 24 小时", isOn: $temporary).accessibilityIdentifier("memory.temporary")
                    Text(temporary ? "适合今天的临时安排，到期后不再用于后续对话。" : "保存为长期记忆，之后可在记忆页移除。")
                        .font(.caption).foregroundStyle(Brand.muted)
                }
                Section { Text("点击“确认记住”后才会保存。当前为团队演示空间，请勿填写敏感个人信息。").font(.caption).foregroundStyle(Brand.muted) }
                if let error { Section { Text(error).foregroundStyle(.orange).font(.subheadline) } }
            }.navigationTitle("添加记忆").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("取消") { if cleaned.isEmpty { dismiss() } else { discard = true } }.disabled(saving)
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button { Task { await save() } } label: { if saving { ProgressView() } else { Text("确认记住") } }
                            .disabled(cleaned.isEmpty || content.count > 500 || saving || store.busy || !store.isConnected)
                            .accessibilityIdentifier("memory.save")
                    }
                }.interactiveDismissDisabled(!cleaned.isEmpty || saving)
                .confirmationDialog("放弃这条尚未保存的记忆？", isPresented: $discard, titleVisibility: .visible) {
                    Button("放弃", role: .destructive) { dismiss() }; Button("继续编辑", role: .cancel) {}
                }
        }
    }
    private func save() async {
        saving = true; error = nil; defer { saving = false }
        do {
            store.data.personal = try await store.client.remember(cleaned, temporary: temporary)
            store.toast = "已记住，可在记忆页管理"; dismiss()
        } catch { self.error = error.localizedDescription }
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
                    NavigationLink("通知与提醒", value: AppRoute.personalAgent).font(.caption)
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
                            Button("回到助手继续追问") {
                                store.selectConversation(store.generalConversation)
                                store.openAI()
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
                NavigationLink("通知与提醒", value: AppRoute.personalAgent)
                Button("回到助手继续处理") { store.openAI() }
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
    private var limitations: [String] {
        var values: [String] = []
        for source in message.sources {
            if let value = source.limitation, !value.isEmpty, !values.contains(value) { values.append(value) }
        }
        return values
    }
    private var testSource: Bool { message.sources.contains { ["fixture", "replay", "synthetic_demo"].contains($0.sourceType ?? "") } }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(message.title).font(.headline)
                Spacer()
                if !message.read { Circle().fill(Brand.blue).frame(width: 7, height: 7) }
            }
            if message.body != message.title { Text(message.body).font(.body).textSelection(.enabled) }
            Text(displayTime(message.createdAt)).font(.caption2).foregroundStyle(Brand.muted)
            Label(testSource ? "测试 / 回放资料" : "事件记录", systemImage: "clock")
                .font(.caption).foregroundStyle(Brand.muted)
            DisclosureGroup("查看来源") {
                VStack(alignment: .leading, spacing: 8) {
                    Text(message.why).font(.caption)
                    ForEach(limitations, id: \.self) { Text($0).font(.caption2).foregroundStyle(Brand.muted) }
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
            HStack {
                if let evidence = message.sources.compactMap(\.evidenceId).first {
                    NavigationLink("查看证据", value: AppRoute.evidence(evidence)).buttonStyle(.borderedProminent)
                } else if let skill = message.skillId {
                    NavigationLink("查看守护", value: AppRoute.skill(skill)).buttonStyle(.borderedProminent)
                }
                Button("接着聊") { respond("read"); onReply() }
                Spacer(minLength: 0)
                if message.feedback == "handled" { Text("已处理此提醒").font(.caption).foregroundStyle(Brand.muted) }
                else {
                    Menu {
                        Button("我已处理") { respond("handled") }
                        Button("1 小时后再提醒") { respond("snooze") }
                        Button("不再提醒此事件") { respond("dismiss") }
                    } label: { Image(systemName: "ellipsis") }.accessibilityLabel("处理提醒")
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
