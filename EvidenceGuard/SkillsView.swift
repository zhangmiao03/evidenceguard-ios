import SwiftUI

struct CameraSkillsView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View { OfficialCameraHomeView(connection: store.officialSDK) }
}

private struct OfficialCameraHomeView: View {
    @EnvironmentObject private var store: AppStore
    @ObservedObject var connection: OfficialSDKConnection
    private var events: [SDKEventRecord] { store.data.cameraEvents?.events ?? [] }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                ConnectionBanner()
                HStack {
                    Text("我的摄像头").font(.headline)
                    Spacer()
                    NavigationLink("连接摄像头", value: AppRoute.officialSDK).font(.subheadline)
                        .accessibilityIdentifier("cameraSkills.connect")
                }
                if connection.devices.filter(\.isCompetitionCamera).isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Image(systemName: "video.badge.plus").font(.largeTitle).foregroundStyle(Brand.blue)
                        Text("等你连接第一台摄像头").font(.title3.weight(.semibold))
                        Text("连接后，在这里看门铃、人物和包裹等设备事件。").foregroundStyle(Brand.muted)
                        NavigationLink("连接摄像头", value: AppRoute.officialSDK).buttonStyle(.borderedProminent)
                    }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                        .background(.white.opacity(0.8)).clipShape(RoundedRectangle(cornerRadius: 22))
                } else {
                    VStack(spacing: 12) {
                        ForEach(connection.devices.filter(\.isCompetitionCamera)) { device in
                            NavigationLink { OfficialSDKInspectionView(connection: connection, camera: device) } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: "video").font(.title2).foregroundStyle(Brand.blue)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(device.name).font(.headline)
                                        Text(device.model + " · " + (device.online.map { $0 ? "在线" : "离线" } ?? "状态待确认"))
                                            .font(.caption).foregroundStyle(Brand.muted)
                                    }
                                    Spacer(); Image(systemName: "chevron.right").font(.caption)
                                }.padding(16).background(.white.opacity(0.8)).clipShape(RoundedRectangle(cornerRadius: 18))
                            }.buttonStyle(.plain)
                            NavigationLink { OfficialLiveCameraView(camera: device) } label: {
                                Label("查看直播", systemImage: "play.circle")
                            }.accessibilityIdentifier("cameraSkills.live." + device.sn)
                        }
                    }
                    Toggle("App 打开时同步新事件", isOn: Binding(
                        get: { connection.syncEnabled(for: store.client) },
                        set: { connection.setEventSync($0, client: store.client) }))
                        .accessibilityIdentifier("cameraSkills.sync")
                    Text(connection.syncMessage).font(.caption).foregroundStyle(Brand.muted)
                    Text("切换页面后继续同步；锁屏后暂停。收到的新事件按你的通知偏好处理。")
                        .font(.caption).foregroundStyle(Brand.muted)
                }
                HStack { Text("最近事件").font(.headline); Spacer(); NavigationLink("提醒设置", value: AppRoute.notificationSettings).font(.subheadline) }
                if events.isEmpty {
                    Text("还没有收到摄像头事件。").foregroundStyle(Brand.muted).padding(.vertical, 12)
                }
                ForEach(events) { event in
                    NavigationLink(value: AppRoute.evidence(event.id)) {
                        HStack(alignment: .top, spacing: 12) {
                            if let url = store.client.absoluteURL(event.imageUrl) {
                                AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { Color.gray.opacity(0.1) }
                                    .frame(width: 64, height: 64).clipShape(RoundedRectangle(cornerRadius: 12))
                            } else { Image(systemName: "video").frame(width: 64, height: 64).background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius: 12)) }
                            VStack(alignment: .leading, spacing: 5) {
                                Text(event.label).font(.headline)
                                Text(event.deviceName + " · " + displayTime(Double(event.startMs) / 1_000)).font(.caption).foregroundStyle(Brand.muted)
                                Text(event.reviewStatus == "completed" ? "设备检测 · 查看图片分析" : "设备检测 · 图片待分析").font(.caption).foregroundStyle(Brand.muted)
                            }
                            Spacer(minLength: 0); Image(systemName: "chevron.right").font(.caption)
                        }.padding(16).background(.white.opacity(0.8)).clipShape(RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain).accessibilityIdentifier("cameraSkills.event." + event.id)
                }
                if store.data.cameraEvents?.truncated == true { Text("显示最近 100 条已同步事件。").font(.caption).foregroundStyle(Brand.muted) }
            }.padding(20)
        }.agentPageStyle("摄像头 Skill", largeTitle: true)
            .refreshable { await store.refresh() }
    }
}

struct CameraTestToolsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var creatingDraft = false
    private var camera: CameraDevice? { store.camera(store.selectedCameraID) ?? store.data.cameras.first }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ConnectionBanner()
                HStack {
                    Text("选择摄像头").font(.headline)
                    Spacer()
                    NavigationLink("管理设备", value: AppRoute.cameras)
                        .font(.subheadline).accessibilityIdentifier("cameraSkills.devices")
                }
                if let camera {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(store.data.cameras) { device in
                                Button { store.selectedCameraID = device.id } label: {
                                    HStack(spacing: 10) {
                                        Image(systemName: device.id == camera.id ? "checkmark.circle.fill" : "video")
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(device.name).font(.subheadline.weight(.semibold))
                                            Text(device.connectionLabel).font(.caption)
                                        }
                                    }.padding(14)
                                        .foregroundStyle(device.id == camera.id ? Brand.blue : Brand.muted)
                                        .background(device.id == camera.id ? Color.white : Color.white.opacity(0.4))
                                        .clipShape(RoundedRectangle(cornerRadius: 18))
                                }.buttonStyle(.plain).accessibilityIdentifier("cameraSkills.camera." + device.id)
                                    .accessibilityAddTraits(device.id == camera.id ? .isSelected : [])
                            }
                        }
                    }.disabled(creatingDraft)
                    NavigationLink(value: AppRoute.camera(camera.id)) {
                        CameraFrame(camera: camera)
                    }.buttonStyle(.plain).accessibilityLabel("查看\(camera.name)的画面")
                        .accessibilityIdentifier("cameraSkills.preview")
                    VStack(spacing: 0) {
                        Button { Task { await createDraft(camera: camera.id) } } label: {
                            capabilityRow("圈选守护", detail: creatingDraft ? "正在创建草案…" : "选对象、定条件，确认后启用", icon: "square.dashed")
                        }.disabled(creatingDraft || store.busy || !store.isConnected)
                            .accessibilityIdentifier("cameraSkills.create")
                        Divider().padding(.leading, 58)
                        NavigationLink(value: AppRoute.recordings) {
                            capabilityRow("录像资料", detail: "查看已保存的录像和分析结果", icon: "play.rectangle")
                        }.accessibilityIdentifier("cameraSkills.recordings")
                    }.buttonStyle(.plain).background(.white.opacity(0.83)).clipShape(RoundedRectangle(cornerRadius: 22))
                    Text("创建的守护会出现在“任务”，进度和提醒在那里查看。")
                        .font(.caption).foregroundStyle(Brand.muted)
                } else {
                    EmptyState(title: "先添加一台摄像头", detail: "连接后，可以查看画面、圈选对象并设置守护。", icon: "video.badge.plus")
                    NavigationLink("添加设备", value: AppRoute.addDevice).buttonStyle(PrimaryAction())
                }
            }.padding(20)
        }.agentPageStyle("摄像头 Skill", largeTitle: true)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink(value: AppRoute.addDevice) { Image(systemName: "plus") }
                        .accessibilityLabel("添加摄像头").accessibilityIdentifier("cameraSkills.addDevice")
                }
            }.refreshable { await store.refresh() }
    }

    private func capabilityRow(_ title: String, detail: String, icon: String) -> some View {
        HStack(spacing: 14) {
            Image(systemName: icon).font(.title3).foregroundStyle(Brand.blue).frame(width: 26)
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(.headline).foregroundStyle(Brand.dark)
                Text(detail).font(.caption).foregroundStyle(Brand.muted)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(Brand.muted)
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
    }

    private func createDraft(camera: String) async {
        guard !creatingDraft, !store.busy, store.isConnected else { return }
        creatingDraft = true
        defer { creatingDraft = false }
        do {
            let draft = try await store.client.createDraft(camera: camera, conversation: store.generalConversation,
                prompt: "请选择画面中的观察对象并完善提醒条件", replacesID: nil)
            await store.refresh()
            store.openEditor(draft, regionCameraID: camera)
        } catch { store.errorMessage = error.localizedDescription }
    }
}

struct TasksView: View {
    @EnvironmentObject private var store: AppStore
    @State private var section = "tasks"
    private var archived: [VisualSkill] { store.data.skills.filter { !["active", "draft", "paused"].contains($0.status) } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                ConnectionBanner()
                HStack(spacing: 12) {
                    NavigationLink(value: AppRoute.alerts) {
                        Label("需要关注", systemImage: "bell")
                    }.accessibilityIdentifier("skills.alerts")
                    Spacer()
                    NavigationLink(value: AppRoute.evidenceList(nil)) {
                        Label("证据", systemImage: "doc.text.image")
                    }.accessibilityIdentifier("skills.evidence")
                }.font(.subheadline).padding(14).background(.white.opacity(0.7)).clipShape(RoundedRectangle(cornerRadius: 18))
                Picker("任务分类", selection: $section) {
                    Label("任务", systemImage: "checklist").tag("tasks")
                    Label("定时", systemImage: "clock").tag("scheduled")
                }.pickerStyle(.segmented).accessibilityIdentifier("skills.sections")
                if section == "tasks" {
                    if store.data.skills.isEmpty {
                        EmptyState(title: "想让摄像头帮你关注什么？", detail: "告诉助手你的需求，一起确认对象、区域和提醒条件。", icon: "video")
                    }
                    taskGroup("运行中", status: "active")
                    taskGroup("待确认", status: "draft")
                    taskGroup("已暂停", status: "paused")
                    if !archived.isEmpty {
                        DisclosureGroup("已结束 · \(archived.count)") {
                            VStack(spacing: 12) { ForEach(archived) { taskRow($0) } }.padding(.top, 10)
                        }.font(.subheadline).tint(Brand.muted)
                    }
                    Button { beginTask() } label: { Label("告诉助手一个新任务", systemImage: "plus.bubble") }
                        .font(.subheadline).padding(.vertical, 6).accessibilityIdentifier("skills.create")
                } else { scheduledTasks }
            }.padding(20)
        }.agentPageStyle("任务", largeTitle: true)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { beginTask() } label: { Image(systemName: "plus") }
                        .accessibilityLabel("新建任务").accessibilityIdentifier("skills.new")
                }
            }.refreshable { await store.refresh() }
    }
    @ViewBuilder private func taskGroup(_ title: String, status: String) -> some View {
        let items = store.data.skills.filter { $0.status == status }.sorted { $0.createdAt > $1.createdAt }
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text("\(title) · \(items.count)").font(.headline).foregroundStyle(Brand.dark)
                VStack(spacing: 0) {
                    ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                        taskRow(item)
                        if index < items.count - 1 { Divider().padding(.horizontal, 16) }
                    }
                }.background(.white.opacity(0.83)).clipShape(RoundedRectangle(cornerRadius: 22))
            }
        }
    }
    private func taskRow(_ skill: VisualSkill) -> some View {
        NavigationLink(value: AppRoute.skill(skill.id)) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: skill.status == "active" ? "play.circle" : skill.status == "draft" ? "square.and.pencil" : "checklist")
                    .foregroundStyle(Brand.blue).frame(width: 24).padding(.top, 2)
                VStack(alignment: .leading, spacing: 7) {
                    Text(skill.name).font(.headline).foregroundStyle(Brand.dark)
                    Text(skill.status == "draft" ? skill.prompt : skill.resultReason)
                        .font(.subheadline).foregroundStyle(Brand.muted).lineLimit(1)
                    HStack(spacing: 6) {
                        Text(store.isConnected ? skill.resultLabel : "等待连接")
                            .foregroundStyle(skill.result == "needs_attention" ? .orange : Brand.blue)
                        Text("·")
                        Text(skill.replay != nil ? "录像测试" : skill.devices.contains(where: { store.camera($0)?.adapter.contains("fixture") == true }) ? "合成测试" : skill.devices.compactMap { store.camera($0)?.name }.joined(separator: "、"))
                    }.font(.caption).foregroundStyle(Brand.muted).lineLimit(1)

                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(Brand.muted).padding(.top, 4)
            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
        }.buttonStyle(.plain).accessibilityIdentifier("skill.\(skill.id)")
    }
    @ViewBuilder private var scheduledTasks: some View {
        if let preferences = store.data.personal?.preferences {
            VStack(alignment: .leading, spacing: 14) {
                Label("每日守护概况", systemImage: "sun.max").font(.headline)
                Text(preferences.dailySummary ? "每天 \(preferences.summaryHour):00" : "尚未开启")
                    .font(.title3.weight(.medium))
                if preferences.dailySummary && !preferences.enabled {
                    Text("已暂停：主动提醒总开关已关闭").font(.caption).foregroundStyle(.orange)
                }
                Text("汇总已保存的观察与待处理事项，发到助手主对话。")
                    .font(.subheadline).foregroundStyle(Brand.muted)
                Text("时区：\(preferences.timezone) · 应用内提醒").font(.caption).foregroundStyle(Brand.muted)
                NavigationLink("设置时间与免打扰", value: AppRoute.personalAgent).font(.subheadline.bold())
                    .accessibilityIdentifier("skills.scheduleSettings")
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(.white.opacity(0.83)).clipShape(RoundedRectangle(cornerRadius: 22))
            Text("当前支持每日概况；摄像头任务按各自规则持续或单次执行，暂不支持预约启停。")
                .font(.caption).foregroundStyle(Brand.muted)
        } else { Text("正在读取定时设置…").font(.subheadline).foregroundStyle(Brand.muted) }
    }
    private func beginTask() {
        let draft = store.conversationDrafts[store.generalConversation] ?? ""
        store.openAI(prompt: draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                     ? "我想创建一项摄像头 Skill，请先帮我确认观察对象和提醒条件。" : draft)
    }
}

struct SkillDetailView: View {
    @EnvironmentObject var store: AppStore
    var id: String
    @State private var stopping = false
    @State private var events: [RunEvent] = []
    @State private var eventsError: String?
    @State private var trialReports: [SkillTrial] = []
    @State private var conflicts: [CameraOccupancy] = []
    @State private var showConflict = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ConnectionBanner()
                if let skill = store.skill(id) {
                    VStack(alignment: .leading, spacing: 12) { Text(skill.name).font(.title2.bold()); StatusBadge(text: store.isConnected ? skill.resultLabel : "等待连接", value: store.isConnected ? skill.result : "unknown"); Text(skill.resultReason).font(.subheadline); Text("最近观察：\(displayTime(skill.lastObservedAt))").font(.caption).foregroundStyle(Brand.muted) }.frame(maxWidth: .infinity, alignment: .leading).padding(18).cardStyle()
                    if skill.status == "draft" {
                        Button("继续设置守护") { store.openEditor(skill) }.buttonStyle(PrimaryAction()).accessibilityIdentifier("watch.continue")
                    }
                    if let replay = skill.replay {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("录像回放测试", systemImage: "film").font(.headline)
                            Text("已到达 \(videoTime(skill.replayState?.cursor ?? 0)) · 模型观察 \(skill.replayState?.modelCalls ?? 0) 次").font(.subheadline)
                            Text("不是实时家庭画面；模型判断可能有误，请核验提醒片段。").font(.caption).foregroundStyle(.orange)
                            NavigationLink(value: AppRoute.video(replay.recordingId, skill.replayState?.cursor ?? 0)) { Text("查看回放源录像") }
                            if skill.status == "active" {
                                Button(skill.replayState?.online == false ? "恢复回放输入" : "模拟输入断流") {
                                    Task { await store.perform { _ = try await store.client.replayTransport(id, online: skill.replayState?.online == false) } }
                                }.buttonStyle(.bordered)
                            }
                        }.padding(16).cardStyle()
                    }
                    if skill.replay == nil { ForEach(skill.devices, id: \.self) { cameraID in NavigationLink(value: AppRoute.camera(cameraID)) { CameraFrame(camera: store.camera(cameraID)) }.buttonStyle(.plain) } }
                    DisclosureGroup("守护规则与采样说明") { VStack(alignment: .leading, spacing: 12) { Text(skill.prompt); Text("需求补充：" + (skill.rules?.description ?? "等待完善规则")).font(.subheadline); Text(skill.rules?.consecutiveFrames != nil ? "历史按帧规则，仅保留过去的结果；重新创建时使用秒数配置" : "看不清时保留判断 · \(skill.rules?.sampleEvery ?? 3) s 检测 · 确认跨度 \(skill.rules?.confirmationSpan ?? 6) s · \(skill.replay != nil ? "有限录像回放" : skill.mode == "once" ? "一次性任务" : "持续守护")").font(.caption).foregroundStyle(Brand.muted) } }.padding(16).cardStyle()
                    if skill.replay != nil && skill.alert == "open" {
                        Button("标记已核验（保留证据）") {
                            Task { await store.perform { _ = try await store.client.acknowledgeReplay(id) } }
                        }.buttonStyle(.bordered)
                    }
                    NavigationLink { DeploymentPreparationView(id: skill.id, revision: skill.revision) } label: { Label("设备适配与真机验收准备", systemImage: "checklist") }
                    NavigationLink(value: AppRoute.evidenceList(id)) { Label("查看此任务的证据", systemImage: "doc.text.image") }
                    Button { store.openAI(prompt: "", skillID: id) } label: { Label("与 AI 继续沟通", systemImage: "bubble.left.and.bubble.right") }.buttonStyle(PrimaryAction())
                    ForEach(trialReports.prefix(3)) { trial in
                        NavigationLink { SkillTrialReportView(id: trial.id) } label: { Label("试跑报告 · " + trial.label, systemImage: "checklist") }
                    }
                    if !events.isEmpty {
                        DisclosureGroup("最近运行记录") {
                            VStack(alignment: .leading, spacing: 12) {
                            ForEach(events.suffix(6).reversed()) { event in
                                HStack(alignment: .top) { Text(event.label).font(.subheadline); Spacer(); Text(displayTime(event.at)).font(.caption2).foregroundStyle(Brand.muted) }
                            }
                            }
                        }.padding(16).cardStyle()
                    }
                    if let eventsError { Text(eventsError).font(.caption).foregroundStyle(.orange) }
                    if skill.status == "active" {
                        if skill.replay == nil { Button("重新观察") { Task { await store.recheck(id) } }.buttonStyle(.bordered)
                        if skill.alert == "open" { Button("我已处理，请复核") { Task { await store.recheck(id, acknowledged: true) } }.buttonStyle(.borderedProminent) }
                        }
                        Button("暂停守护") { Task { await store.change(id, action: "pause") } }.buttonStyle(.bordered)
                    }
                    if skill.status == "paused" && skill.needsTimingReview != true { Button("恢复守护") { Task { await resume() } }.buttonStyle(.borderedProminent) }
                    if ["active", "paused"].contains(skill.status) { Button("修改规则") { store.openAI(prompt: "我想调整这项守护规则：", skillID: id) }.buttonStyle(.bordered) }
                    if ["active", "paused", "draft"].contains(skill.status) { Button(skill.status == "draft" ? "丢弃草案" : "停止任务", role: .destructive) { stopping = true }.buttonStyle(.bordered) }
                } else { EmptyState(title: "没有找到任务", detail: "返回列表刷新后重试。") }
            }.padding(16).disabled(store.busy)
        }.pageStyle("守护详情")
        .task(id: id) {
            trialReports = (try? await store.client.trials(id)) ?? []
            while !Task.isCancelled {
                do { events = try await store.client.skillEvents(id); eventsError = nil }
                catch { if !Task.isCancelled { eventsError = "运行记录暂未同步" } }
                do { try await Task.sleep(for: .seconds(2)) } catch { break }
            }
        }
        .confirmationDialog("停止后需重新创建任务", isPresented: $stopping, titleVisibility: .visible) { Button("确认停止", role: .destructive) { Task { await store.change(id, action: "stop") } }; Button("取消", role: .cancel) {} }
        .alert("恢复守护需要切换摄像头", isPresented: $showConflict) {
            Button("暂停占用任务并恢复", role: .destructive) { Task { await resume(switchFrom: Dictionary(uniqueKeysWithValues: conflicts.map { ($0.skillId, $0.executionEpoch) })) } }
            Button("保持暂停", role: .cancel) {}
        } message: { Text("将暂停：\(conflicts.map(\.name).joined(separator: "、"))。这些任务会释放全部绑定摄像头。恢复后会重新建立观察基线。") }
    }
    private func resume(switchFrom: [String: String] = [:]) async {
        guard !store.busy else { return }
        store.busy = true; defer { store.busy = false }
        do {
            _ = try await store.client.lifecycle(id, action: "resume", switchFrom: switchFrom)
            await store.refresh(); store.toast = "已恢复，正在重新建立观察基线"
        } catch let problem as APIProblem where !problem.conflicts.isEmpty {
            conflicts = problem.conflicts; showConflict = true
        } catch { store.errorMessage = error.localizedDescription }
    }
}
struct AlertsView: View {
    @EnvironmentObject var store: AppStore
    private var items: [VisualSkill] { store.data.skills.filter { ($0.alert == "open" && $0.status != "stopped") || ($0.status == "active" && $0.result != "confirmed") } }
    var body: some View { ScrollView { VStack(spacing: 14) { ConnectionBanner(); if items.isEmpty { EmptyState(title: "暂无待处理事项", detail: "新告警与无法确认的任务会显示在这里。", icon: "bell") }; ForEach(items) { s in NavigationLink(value: AppRoute.skill(s.id)) { SkillRow(skill: s) }.buttonStyle(.plain) } }.padding(16) }.pageStyle("需要关注") }
}


struct ContractSummary: View {
    var contract: SkillContract
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("先满足：" + contract.precondition)
            Text("何时提醒：" + contract.trigger)
            Text("时间条件：" + contract.temporal)
            Text("看不清时：" + contract.unknown)
            Text("保留证据：" + contract.evidence)
            Text("何时结束：" + contract.completion)
        }.font(.caption).foregroundStyle(Brand.muted)
    }
}
struct SkillTrialReportView: View {
    @EnvironmentObject var store: AppStore
    var id: String
    @State private var report: SkillTrial?
    @State private var error: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let report {
                    Text(report.label).font(.title2.bold())
                    Text(report.summary)
                    if report.stale { Text("草案或模型已变化，此报告不能用于启用当前规则。").foregroundStyle(.orange) }
                    Text("草案版本 \(report.revision) · \(report.elapsedSeconds.map { String(format: "%.1f 秒", $0) } ?? "处理中") · 失败 \(report.failureCount) 次").font(.caption)
                    Text("人工预期：" + (["explore":"探索，不作为验收", "alert":"应该提醒", "no_alert":"不应提醒"][report.expectedOutcome ?? "explore"] ?? "未标注")).font(.subheadline)
                    Text(report.canConfirm ? "本段符合人工预期 · 仅限回放" : "尚不能作为启用依据").foregroundStyle(report.canConfirm ? .green : .orange)
                    Text(report.wouldAlert ? "本次会形成提醒" : "本次未形成提醒").font(.headline)
                    if let source = report.sourceRecordingId {
                        NavigationLink { RecordingPlayerView(id: source, offset: 0) } label: { Label("播放完整测试录像，核对人工预期", systemImage: "play.rectangle") }
                    }
                    if report.videoUrl != nil {
                        NavigationLink { RecordingPlayerView(id: report.id, offset: max(0,(report.eventTime ?? 0) - (report.clipStart ?? 0)), trialEvidence: true) } label: { Label("播放试跑触发片段", systemImage: "play.circle") }
                    }
                    ContractSummary(contract: report.contract)
                    ForEach(Array(report.observations.enumerated()), id: \.offset) { _, observation in
                        VStack(alignment: .leading, spacing: 6) {
                            Text("采样 \(String(format: "%.0f", observation.start)) s · \(observation.label)").font(.headline)
                            Text(observation.summary).font(.subheadline)
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(14).cardStyle()
                    }
                    ForEach(report.limitations, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
                } else { ProgressView("加载试跑报告…") }
                if let error { Text(error).foregroundStyle(.orange) }
            }.padding(16)
        }.pageStyle("试跑报告")
        .task(id: id) {
            repeat {
                do { report = try await store.client.trial(id); error = nil }
                catch { if !Task.isCancelled { self.error = error.localizedDescription }; break }
                if report?.running != true { break }
                do { try await Task.sleep(for: .seconds(2)) } catch { break }
            } while !Task.isCancelled
        }
    }
}

struct DeploymentPreparationView: View {
    @EnvironmentObject var store: AppStore
    var id: String
    var revision: Int
    @State private var plan: DeploymentPlan?
    @State private var error: String?
    @State private var saving = false
    var body: some View {
        Form {
            if let plan {
                Section("发布前需要完成") {
                    Text(plan.summary).font(.headline)
                    Text("每 \(plan.sampleIntervalSeconds) s 检测 · 确认跨度 \(plan.confirmationSeconds) s")
                    Text(plan.note).font(.caption).foregroundStyle(.secondary)
                }
                ForEach(plan.cameras) { camera in
                    Section(camera.name) {
                        Text(camera.verdict).foregroundStyle(.orange)
                        Text(camera.candidateUse)
                        Text(camera.reason).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Section("需要你配合的准备") {
                    ForEach(plan.actions) { action in
                        Toggle(action.instruction, isOn: Binding(get: { action.completed }, set: { value in
                            Task {
                                saving = true; defer { saving = false }
                                do { self.plan = try await store.client.prepareSite(id, revision: revision, action: action.id, completed: value); error = nil }
                                catch { self.error = error.localizedDescription }
                            }
                        })).disabled(saving).accessibilityIdentifier("acceptance." + action.id)
                    }
                }
                Section("待解决") { ForEach(plan.blockers, id: \.self) { Text($0).foregroundStyle(.orange) } }
                Section { Label("真机发布尚未就绪", systemImage: "lock"); Text("准备记录与录像试跑都不能替代真机验收。设备接口就绪后仍需取得实际测试证据。").font(.caption).foregroundStyle(.secondary) }
            } else { ProgressView("加载验收准备…") }
            if let error { Text(error).foregroundStyle(.orange) }
        }.navigationTitle("真机验收准备").navigationBarTitleDisplayMode(.inline)
        .task { do { plan = try await store.client.deployment(id) } catch { self.error = error.localizedDescription } }
    }
}
