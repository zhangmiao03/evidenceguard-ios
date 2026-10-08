import SwiftUI

struct SkillsView: View {
    @EnvironmentObject var store: AppStore
    @State private var filter = "all"
    private var filtered: [VisualSkill] { store.data.skills.filter { filter == "all" || $0.status == filter } }
    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                ConnectionBanner()
                Picker("任务筛选", selection: $filter) { Text("全部").tag("all"); Text("运行中").tag("active"); Text("待确认").tag("draft"); Text("已暂停").tag("paused") }.pickerStyle(.segmented)
                if filtered.isEmpty { EmptyState(title: "这里还没有 Skill", detail: "可先用文字或语音向 AI 描述需求。", icon: "square.3.layers.3d") }
                ForEach(filtered) { skill in NavigationLink(value: AppRoute.skill(skill.id)) { SkillRow(skill: skill) }.buttonStyle(.plain).accessibilityIdentifier("skill.\(skill.id)") }
                Button { store.openAI() } label: { Label("创建新技能", systemImage: "plus") }.buttonStyle(PrimaryAction())
            }.padding(16)
        }.pageStyle("我的 Skill").refreshable { await store.refresh() }
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
                    VStack(alignment: .leading, spacing: 12) { Text("守护规则").font(.headline); Text(skill.prompt); Text("需求补充：" + (skill.rules?.description ?? "等待完善规则")).font(.subheadline); Text(skill.rules?.consecutiveFrames != nil ? "历史按帧规则，仅保留过去的结果；重新创建时使用秒数配置" : "看不清时保留判断 · \(skill.rules?.sampleEvery ?? 3) s 检测 · 确认跨度 \(skill.rules?.confirmationSpan ?? 6) s · \(skill.replay != nil ? "有限录像回放" : skill.mode == "once" ? "一次性任务" : "持续守护")").font(.caption).foregroundStyle(Brand.muted) }.padding(16).cardStyle()
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
                        VStack(alignment: .leading, spacing: 12) {
                            Text("最近运行记录").font(.headline)
                            ForEach(events.suffix(6).reversed()) { event in
                                HStack(alignment: .top) { Text(event.label).font(.subheadline); Spacer(); Text(displayTime(event.at)).font(.caption2).foregroundStyle(Brand.muted) }
                            }
                        }.padding(16).cardStyle()
                    }
                    if let eventsError { Text(eventsError).font(.caption).foregroundStyle(.orange) }
                    if skill.status == "draft" { Button("检查并编辑草案") { store.editor = skill }.buttonStyle(.borderedProminent) }
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
        }.pageStyle("Skill 详情")
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
