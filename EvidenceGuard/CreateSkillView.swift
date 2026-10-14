import SwiftUI

struct CreateSkillView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) var dismiss
    @State var skill: VisualSkill
    var initialRegionCameraID: String? = nil
    @State private var regionEditor = false
    @State private var cameraID = ""
    @State private var saving = false
    @State private var error: String?
    @State private var exitWarning = false
    @State private var fixtureAcknowledged = false
    @State private var replayAcknowledged = false
    @State private var original: VisualSkill?
    @State private var conflicts: [CameraOccupancy] = []
    @State private var showConflict = false
    @State private var capability: SkillCapability?
    @State private var trial: SkillTrial?
    @State private var trialReviewed = false
    @State private var expectedOutcome = "explore"
    @State private var step = 0
    private var unchanged: Bool { original == skill }
    private var executionReady: Bool { unchanged && capability?.canActivate == true && (skill.replay == nil || (trial?.canConfirm == true && trialReviewed)) }
    private var rules: Binding<SkillRules> { Binding(get: { skill.rules ?? SkillRules() }, set: { skill.rules = $0 }) }
    private var valid: Bool { !skill.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && skill.prompt.count >= 2 && !skill.target.description.isEmpty && !skill.devices.isEmpty && skill.devices.contains(skill.target.cameraId) }
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 8) {
                        ForEach(Array(["对象", "条件", "确认"].enumerated()), id: \.offset) { index, name in
                            Button { step = index } label: {
                                Text("\(index + 1) · " + name).font(.subheadline.weight(.medium))
                                    .frame(maxWidth: .infinity).padding(.vertical, 8)
                                    .background(step == index ? Brand.paleBlue : Color.clear)
                                    .clipShape(Capsule())
                            }.buttonStyle(.plain).foregroundStyle(step == index ? Brand.blue : Brand.muted)
                                .disabled(index > step || saving).accessibilityIdentifier("draft.step.\(index)")
                        }
                    }
                    Text(step == 0 ? "先选对象和画面。保存草案不会开始守护。" : step == 1 ? "设置什么时候提醒，看不清时保留判断。" : "核对能力与数据来源，确认后才会开始测试。")
                        .font(.caption).foregroundStyle(Brand.muted)
                }
                if step == 0 { objectStep }
                else if step == 1 { conditionStep }
                else { confirmationStep }
                if let error { Section { Text(error).foregroundStyle(.orange).font(.subheadline) } }
            }
            .id(step)
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 8) {
                    if step < 2 {
                        Button {
                            if step == 0 { step = 1 }
                            else { Task { await prepare(); if error == nil { step = 2 } } }
                        } label: {
                            HStack { if saving { ProgressView() }; Text(step == 0 ? "下一步：提醒条件" : "保存草案，检查并确认") }.frame(maxWidth: .infinity)
                        }.buttonStyle(.borderedProminent).disabled(!valid || saving || (step == 1 && !store.isConnected)).accessibilityIdentifier("draft.next")
                    } else {
                        Button { Task { await save(activate: true) } } label: {
                            HStack { if saving { ProgressView() }; Text(skill.replay == nil ? "确认并开始标记测试" : "确认并开始回放") }.frame(maxWidth: .infinity)
                        }.buttonStyle(.borderedProminent).disabled(!valid || !executionReady || saving || !(skill.replay == nil ? fixtureAcknowledged : replayAcknowledged) || !store.isConnected).accessibilityIdentifier("draft.confirm")
                        if !executionReady { Text("完成上方能力检查与必要的试跑后才能开始。").font(.caption).foregroundStyle(Brand.muted) }
                    }
                }.padding(16).background(.regularMaterial)
            }
            .navigationTitle("设置守护").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("关闭") { if original != skill { exitWarning = true } else { dismiss() } }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) { Button("保存草案") { Task { await save(activate: false) } }.disabled(!valid || saving || !store.isConnected).accessibilityIdentifier("draft.save") }
            }
            .interactiveDismissDisabled(original != skill || saving)
            .confirmationDialog("要放弃尚未保存的修改吗？", isPresented: $exitWarning, titleVisibility: .visible) { Button("放弃修改并返回", role: .destructive) { dismiss() }; Button("继续编辑", role: .cancel) {} }
            .alert("摄像头正在执行其他守护", isPresented: $showConflict) {
                Button("暂停原任务并启用此任务", role: .destructive) {
                    Task { await save(activate: true, switchFrom: Dictionary(uniqueKeysWithValues: conflicts.map { ($0.skillId, $0.executionEpoch) })) }
                }
                Button("保留草案，不切换", role: .cancel) {
                    Task { await store.refresh() }; store.toast = "草案已保存，原任务继续运行"
                }
            } message: {
                Text("将暂停：\(conflicts.map(\.name).joined(separator: "、"))。原任务绑定的全部摄像头将被释放，暂停期间不会继续检测。当前草案已保存。")
            }
            .navigationDestination(isPresented: $regionEditor) {
                SkillRegionEditor(skill: $skill, initialCameraID: initialRegionCameraID ?? skill.target.cameraId)
            }
            .onAppear { if original == nil { original = skill; cameraID = skill.target.cameraId; regionEditor = initialRegionCameraID != nil } }
            .task {
                do { capability = try await store.client.capability(skill.id); trial = try await store.client.trials(skill.id).first }
                catch { self.error = error.localizedDescription }
            }
            .task(id: trial?.id) {
                while let current = trial, current.running, !Task.isCancelled {
                    do { try await Task.sleep(for: .seconds(2)); trial = try await store.client.trial(current.id) }
                    catch { if !Task.isCancelled { self.error = "试跑报告同步失败，可重新检查" }; break }
                }
            }
            .onChange(of: skill) { _, _ in trialReviewed = false }
        }
    }
    @ViewBuilder private var objectStep: some View {
        Section("你想关注什么") {
            TextField("守护名称", text: $skill.name).accessibilityIdentifier("draft.name")
            TextField("需求描述", text: $skill.prompt, axis: .vertical).lineLimit(2...5)
            TextField("观察对象", text: $skill.target.description)
        }
        Section("选择摄像头") {
            ForEach(store.data.cameras) { camera in
                Toggle(isOn: Binding(get: { skill.devices.contains(camera.id) }, set: { enabled in
                    if enabled { if !skill.devices.contains(camera.id) { skill.devices.append(camera.id); skill.regions[camera.id] = .initial } }
                    else if skill.devices.count > 1 {
                        skill.devices.removeAll { $0 == camera.id }; skill.regions.removeValue(forKey: camera.id)
                        if skill.target.cameraId == camera.id { skill.target.cameraId = skill.devices[0] }
                        if cameraID == camera.id { cameraID = skill.devices[0] }
                    }
                })) { VStack(alignment: .leading) {
                    Text(camera.name + " · " + camera.model)
                    Text(skill.replay == nil ? camera.connectionLabel : "录像绑定的摄像头").font(.caption).foregroundStyle(Brand.muted)
                    if let owner = store.data.skills.first(where: { $0.status == "active" && $0.devices.contains(camera.id) }) {
                        Text("正在执行：\(owner.name)").font(.caption).foregroundStyle(.orange)
                    } else { Text("暂无实时任务占用").font(.caption).foregroundStyle(Brand.muted) }
                } }.disabled(skill.replay != nil)
            }
            Picker("主观察视角", selection: $skill.target.cameraId) { ForEach(skill.devices, id: \.self) { id in Text(store.camera(id)?.name ?? id).tag(id) } }
        }
        Section("观察输入") {
            Picker("数据来源", selection: Binding(get: { skill.replay?.recordingId ?? "" }, set: { value in
                skill.replay = value.isEmpty ? nil : ReplayConfig(recordingId: value)
                if !value.isEmpty {
                    var updatedRules = skill.rules ?? SkillRules()
                    updatedRules.trigger = "leaves_region"; updatedRules.completion = "once"
                    updatedRules.saveEvidence = true
                    skill.rules = updatedRules
                }
                fixtureAcknowledged = false; replayAcknowledged = false
                if let recording = store.data.recordings?.first(where: { $0.id == value }) {
                    skill.devices = [recording.cameraId]; skill.target.cameraId = recording.cameraId
                    skill.regions = [recording.cameraId: .initial]; cameraID = recording.cameraId
                }
            })) {
                Text("合成摄像头测试标记").tag("")
                ForEach((store.data.recordings ?? []).filter { ($0.duration ?? 0) >= 2 && ($0.duration ?? 0) <= 60 }) { recording in
                    Text("回放：\(recording.title)").tag(recording.id)
                }
            }.accessibilityIdentifier("draft.replaySource")
            if skill.replay != nil {
                Text("按设置的秒数间隔提取采样图，判断区域内是否仍有目标。首次提醒或片尾结束；模型慢时回放会变慢。不是已接入的真机守护。")
                    .font(.caption).foregroundStyle(.orange)
            }
        }
        Section("画面与圈选") {
            Button { regionEditor = true } label: { Label("进入画面，圈选目标与关注区域", systemImage: "viewfinder") }.accessibilityIdentifier("draft.openRegion")
            Text("橙框标记要关注的物体，蓝框标记范围。完成圈选后返回本页继续设置条件；保存不会自动启用。").font(.caption).foregroundStyle(Brand.muted)
        }
    }
    @ViewBuilder private var conditionStep: some View {
        Section("可观察的任务类型") {
            Picker("任务类型", selection: Binding(get: { rules.wrappedValue.taskKind ?? "unspecified" }, set: { rules.wrappedValue.taskKind = $0 })) {
                Text("请选择具体类型").tag("unspecified")
                Text("包裹离开关注区域").tag("parcel_removal")
                Text("测试标记区域进出").tag("marker_region")
                Text("宠物行为（暂不支持）").tag("pet_activity")
                Text("车辆行为（暂不支持）").tag("vehicle_activity")
                Text("其他需求（暂不支持）").tag("custom")
            }.accessibilityIdentifier("draft.taskKind")
            DisclosureGroup("额外行为要求（暂不支持）") {
            TextField("额外行为持续时间（s，0 为无）", value: Binding(get: { rules.wrappedValue.durationSeconds ?? 0 }, set: { rules.wrappedValue.durationSeconds = max(0, $0) }), format: .number).keyboardType(.decimalPad)
            Text("这里指“宠物静止 N s”等额外行为要求，目前尚无执行器。包裹离区的检测间隔和确认跨度在下方设置。").font(.caption).foregroundStyle(Brand.muted)
            }
        }
        Section("何时提醒") {
            Picker("触发条件", selection: rules.trigger) { Text("离开区域").tag("leaves_region"); if skill.replay == nil { Text("进入区域").tag("enters_region"); Text("记录活动（执行待接入）").tag("record_activity") } }
            TextField("需求补充（不改变下方执行合同）", text: rules.description, axis: .vertical)
            Stepper("每隔 \(rules.wrappedValue.sampleEvery) s 检测", value: Binding(get: { rules.wrappedValue.sampleEvery }, set: { value in rules.wrappedValue.sampleEvery = value; rules.wrappedValue.confirmationSpan = max(value, rules.wrappedValue.confirmationSpan) }), in: 3...300).accessibilityIdentifier("draft.sampleInterval")
            Stepper("确认跨度：\(rules.wrappedValue.confirmationSpan) s", value: rules.confirmationSpan, in: rules.wrappedValue.sampleEvery...600).accessibilityIdentifier("draft.confirmationSpan")
            Text("例如每 3 s 检测、确认跨度 6 s：在 0、3、6 s 的采样均满足条件后确认。采样之间不可见，短暂动作可能漏过；报告时间是确认时刻，不是精确动作时刻。").font(.caption).foregroundStyle(Brand.muted)
            if skill.replay == nil {
                Picker("任务方式", selection: rules.completion) { Text("持续守护").tag("continuous"); Text("触发一次后完成").tag("once") }
            } else {
                Text("回放在首次提醒或片尾结束").font(.footnote).foregroundStyle(.secondary)
            }
            Text("无法确认时：保留判断、请求补充观察；不会把遮挡或离线视为物品离开。").font(.caption).foregroundStyle(Brand.muted)
        }
        Section {
            Text("每台摄像头同时运行一项守护；新规则确认前，原任务继续运行。")
                .font(.caption).foregroundStyle(Brand.muted)
        }
    }
    @ViewBuilder private var confirmationStep: some View {
        Section("将要测试的守护") {
            Text(skill.name).font(.headline)
            Text(skill.target.description)
            Text(skill.devices.compactMap { store.camera($0)?.name }.joined(separator: "、")).font(.caption).foregroundStyle(Brand.muted)
            Label(skill.replay == nil ? "合成标记测试 · 非真实现场" : "已存录像回放 · 非实时守护", systemImage: "info.circle")
                .font(.caption).foregroundStyle(.orange)
        }
        capabilitySection
        trialSection
        Section("测试执行范围") {
            if skill.replay != nil {
                Text("蓝框为录像中的关注区域，橙框为首帧目标。离散采样图会交给当前视觉模型；结果需人工核验，最多 20 次模型观察。暂停或断流后重建基线，不把缺失画面当成包裹消失。").font(.caption).foregroundStyle(Brand.muted)
                Toggle("我确认使用录像回放测试此规则", isOn: $replayAcknowledged).accessibilityIdentifier("draft.replayAck")
            } else {
                Text("当前合成摄像头执行器只识别编号 17 的测试标记；真实摄像头 SDK 尚待接入。").font(.caption).foregroundStyle(Brand.muted)
                Toggle("使用测试标记验证此规则", isOn: $fixtureAcknowledged).accessibilityIdentifier("draft.fixture")
            }
        }
        Section("真机验收与发布") {
            Text("门铃和屋檐摄像头需要实际视野、正反例与遮挡验收。离线试跑通过不会直接发布真机任务。").font(.caption).foregroundStyle(Brand.muted)
            if unchanged { NavigationLink { DeploymentPreparationView(id: skill.id, revision: skill.revision) } label: { Label("查看设备适配与配合事项", systemImage: "checklist") } }
            else { Text("保存草案后查看对应的验收准备。").font(.caption) }
        }
    }
    @ViewBuilder private var capabilitySection: some View {
        Section("执行能力检查") {
            if !unchanged { Text("内容已修改，请保存并重新检查能力。").foregroundStyle(.orange) }
            else if let capability {
                Text(capability.label).font(.headline)
                ForEach(capability.blockers, id: \.self) { Text($0).foregroundStyle(.orange) }
                if let contract = capability.contract { ContractSummary(contract: contract) }
                ForEach(capability.warnings, id: \.self) { Text($0).font(.caption).foregroundStyle(Brand.muted) }
            } else { Text("等待能力检查") }
            Button("保存并检查能力") { Task { await prepare() } }.disabled(saving || !valid || !store.isConnected).accessibilityIdentifier("draft.checkCapability")
        }
    }
    @ViewBuilder private var trialSection: some View {
        if skill.replay != nil {
            Section("启用前试跑") {
                Text("只读已存录像，不占用摄像头，不产生正式告警。修改草案后报告失效。").font(.caption).foregroundStyle(Brand.muted)
                Picker("人工预期（运行前选择）", selection: $expectedOutcome) {
                    Text("先探索，不作为验收").tag("explore")
                    Text("这段应该提醒").tag("alert")
                    Text("这段不应提醒").tag("no_alert")
                }.disabled(trial?.running == true)
                Button(trial?.running == true ? "试跑进行中" : "保存并试跑当前草案") { Task { await startTrial() } }
                    .disabled(saving || trial?.running == true || !valid || !store.isConnected).accessibilityIdentifier("draft.startTrial")
                if let trial {
                    Text(unchanged ? trial.label : "草案已变化，需重新试跑").font(.headline)
                    Text(trial.summary).font(.subheadline)
                    Text("已完成 \(trial.observations.count) 次观察 · 失败 \(trial.failureCount) 次").font(.caption)
                    NavigationLink { SkillTrialReportView(id: trial.id) } label: { Text("查看试跑报告与片段") }
                    if trial.running { Button("取消试跑") { Task { do { self.trial = try await store.client.cancelTrial(trial.id) } catch { self.error = error.localizedDescription } } } }
                    if unchanged && trial.canConfirm { Toggle("我已查看报告，理解当前仅为回放验证", isOn: $trialReviewed).accessibilityIdentifier("draft.trialReviewed") }
                }
            }
        }
    }
    private func persistDraft() async throws -> VisualSkill {
        if original != skill { let updated = try await store.client.save(skill); skill = updated; original = updated; trialReviewed = false }
        return skill
    }
    private func prepare() async {
        saving = true; error = nil; defer { saving = false }
        do { _ = try await persistDraft(); capability = try await store.client.capability(skill.id); trial = try await store.client.trials(skill.id).first; await store.refresh() }
        catch { self.error = error.localizedDescription }
    }
    private func startTrial() async {
        saving = true; error = nil; defer { saving = false }
        do {
            _ = try await persistDraft(); capability = try await store.client.capability(skill.id)
            guard capability?.canTrial == true else { error = capability?.blockers.joined(separator: "；"); return }
            trialReviewed = false; trial = try await store.client.startTrial(skill, expectedOutcome: expectedOutcome); await store.refresh()
        } catch { self.error = error.localizedDescription }
    }
    private func save(activate: Bool, switchFrom: [String: String] = [:]) async {
        saving = true; error = nil; defer { saving = false }
        do {
            let updated = try await persistDraft()
            let result = activate ? try await store.client.confirm(updated, fixture: fixtureAcknowledged, replay: replayAcknowledged, trialId: trial?.id, trialReviewed: trialReviewed, switchFrom: switchFrom) : updated
            await store.refresh(); dismiss(); store.editor = nil
            if activate && store.path.last != .skill(result.id) { store.path.append(.skill(result.id)) }
            store.toast = activate ? "任务已启用，等待首次新鲜观察" : "草案已保存，尚未启用"
        } catch let problem as APIProblem where !problem.conflicts.isEmpty {
            conflicts = problem.conflicts; showConflict = true; await store.refresh()
        } catch { self.error = error.localizedDescription }
    }
}

struct RegionCanvas: View {
    @EnvironmentObject var store: AppStore
    var camera: CameraDevice?
    @Binding var region: ROI
    var color: Color
    var previewURL: URL? = nil
    var previewAspect: Double = 16.0 / 9.0
    var otherRegion: ROI? = nil
    @State private var dragStart: ROI?
    var body: some View {
        Group {
            if let previewURL {
                AsyncImage(url: previewURL) { phase in
                    if let image = phase.image { image.resizable().aspectRatio(previewAspect, contentMode: .fit) }
                    else { Color.gray.opacity(0.1).aspectRatio(previewAspect, contentMode: .fit).overlay { Text(phase.error == nil ? "加载录像首帧…" : "首帧加载失败，请检查录像") } }
                }
            } else if let camera, camera.fresh, store.isConnected, let url = store.client.absoluteURL(camera.lastFrameUrl) {
                AsyncImage(url: url) { phase in
                    if let image = phase.image { image.resizable().scaledToFit() }
                    else { Color.gray.opacity(0.1).aspectRatio(1.6, contentMode: .fit).overlay { Text("画面加载中，框选尚未确认") } }
                }
            } else { CameraFrame(camera: camera, showLabel: false) }
        }.overlay { GeometryReader { proxy in
                if let otherRegion {
                    Rectangle().stroke(color == .orange ? Color.blue : Color.orange, style: StrokeStyle(lineWidth: 2, dash: [4,4]))
                        .frame(width: proxy.size.width * otherRegion.width, height: proxy.size.height * otherRegion.height)
                        .position(x: proxy.size.width * (otherRegion.x + otherRegion.width / 2), y: proxy.size.height * (otherRegion.y + otherRegion.height / 2)).allowsHitTesting(false)
                }
                Rectangle().fill(color.opacity(0.14)).overlay(Rectangle().stroke(color, style: StrokeStyle(lineWidth: 2, dash: [6, 4])))
                    .frame(width: proxy.size.width * region.width, height: proxy.size.height * region.height)
                    .position(x: proxy.size.width * (region.x + region.width / 2), y: proxy.size.height * (region.y + region.height / 2))
                    .gesture(DragGesture().onChanged { value in
                        if dragStart == nil { dragStart = region }; guard let start = dragStart else { return }
                        region.x = max(0, min(1 - region.width, start.x + value.translation.width / proxy.size.width))
                        region.y = max(0, min(1 - region.height, start.y + value.translation.height / proxy.size.height))
                    }.onEnded { _ in dragStart = nil })
            } }.accessibilityLabel("当前摄像头圈选区域，可通过下方滑块调整")
    }
}

struct SkillRegionEditor: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @Binding var skill: VisualSkill
    var initialCameraID: String
    @State private var cameraID = ""
    @State private var selection = "target"
    @State private var aspect = 1.6
    private var selectedID: String { cameraID.isEmpty ? initialCameraID : cameraID }
    private var region: Binding<ROI> { Binding(get: { selection == "target" ? skill.target.box : skill.regions[selectedID] ?? .initial }, set: { value in if selection == "target" { skill.target.box = value } else { skill.regions[selectedID] = value } }) }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Picker("摄像头", selection: $cameraID) { ForEach(skill.devices, id: \.self) { id in Text(store.camera(id)?.name ?? id).tag(id) } }
                Text(skill.replay == nil ? "当前摄像头画面 · 草案框待确认" : "录像首帧 · 草案框待确认").font(.headline)
                Picker("正在编辑", selection: $selection) {
                    if selectedID == skill.target.cameraId { Text("橙框 · 目标").tag("target") }
                    Text("蓝框 · 关注区域").tag("region")
                }.pickerStyle(.segmented).accessibilityIdentifier("region.selection")
                RegionCanvas(camera: store.camera(selectedID), region: region, color: selection == "target" ? .orange : .blue,
                    previewURL: skill.replay.flatMap { store.client.absoluteURL("/api/recordings/\($0.recordingId)/preview") }, previewAspect: aspect,
                    otherRegion: selection == "target" ? skill.regions[selectedID] : selectedID == skill.target.cameraId ? skill.target.box : nil)
                Text("拖动实线框移动位置；切换上方标签编辑另一个框。下方滑块可调整位置和大小。默认框只是起点，需要你确认。").font(.caption).foregroundStyle(.secondary)
                control("水平位置", value: Binding(get: { region.wrappedValue.x }, set: { region.wrappedValue.x = $0 }), range: 0...max(0.001, 1-region.wrappedValue.width))
                control("垂直位置", value: Binding(get: { region.wrappedValue.y }, set: { region.wrappedValue.y = $0 }), range: 0...max(0.001, 1-region.wrappedValue.height))
                control("框宽", value: Binding(get: { region.wrappedValue.width }, set: { var v = region.wrappedValue; v.width = $0; v.x = min(v.x,1-$0); region.wrappedValue = v }), range: 0.05...1)
                control("框高", value: Binding(get: { region.wrappedValue.height }, set: { var v = region.wrappedValue; v.height = $0; v.y = min(v.y,1-$0); region.wrappedValue = v }), range: 0.05...1)
                TextField("观察对象，例如门前的包裹", text: $skill.target.description).textFieldStyle(.roundedBorder)
                Button("完成圈选，继续编辑条件") { dismiss() }.buttonStyle(PrimaryAction()).accessibilityIdentifier("region.done")
                Text("圈选只修改草案。保存、试跑和启用需在下一页分别完成。").font(.caption).foregroundStyle(.secondary)
            }.padding(16)
        }.navigationTitle("圈选画面").navigationBarTitleDisplayMode(.inline)
        .onAppear { if cameraID.isEmpty { cameraID = skill.devices.contains(initialCameraID) ? initialCameraID : skill.target.cameraId; selection = cameraID == skill.target.cameraId ? "target" : "region" } }
        .onChange(of: cameraID) { _, value in selection = value == skill.target.cameraId ? "target" : "region" }
        .task { if let replay = skill.replay, let video = try? await store.client.recording(replay.recordingId) { aspect = video.aspectRatio ?? 1.6 } }
    }
    private func control(_ title: String, value: Binding<Double>, range: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading) { HStack { Text(title); Spacer(); Text(value.wrappedValue, format: .percent.precision(.fractionLength(0))).foregroundStyle(.secondary); Stepper(title, value: value, in: range, step: 0.01).labelsHidden().accessibilityIdentifier("region.adjust." + title) }; Slider(value: value, in: range).accessibilityLabel(title) }
    }
}
