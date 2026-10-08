import SwiftUI

struct TeachAIView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        ConversationView(conversationID: store.generalConversation, skillID: nil)
    }
}

struct ConversationView: View {
    @EnvironmentObject private var store: AppStore
    let conversationID: String
    let skillID: String?
    @State private var input = ""
    @State private var runs: [AgentRun] = []
    @State private var events: [RunEvent] = []
    @State private var sending = false
    @State private var error: String?
    @State private var syncError: String?
    @State private var voice = false
    @State private var showCamera = false
    @State private var cameraID = ""
    @State private var requestID: String?
    @State private var pendingMessage: String?
    @State private var historyFilter: HistoryFilter?
    @State private var rangeSheet = false
    @State private var executionMode = "live"
    @State private var creatingDraft = false
    private var conversationDrafts: [VisualSkill] {
        let ids = Set(runs.compactMap { $0.draft?.id } + [skillID].compactMap { $0 })
        return store.data.skills.filter { $0.status == "draft" && ($0.originConversationId == conversationID || ids.contains($0.id) || $0.replacesId.map { ids.contains($0) } == true) }
    }
    private var cameraDrafts: [VisualSkill] { conversationDrafts.filter { draft in selectedCamera.map { camera in draft.devices.contains(camera.id) } == true } }
    private func draftForCapture(_ capture: CameraCapture) -> VisualSkill? {
        guard executionMode == "live", capture.historical != true else { return nil }
        return conversationDrafts.first { $0.replay == nil && $0.devices.contains(capture.cameraId) }
    }
    private var effectiveConversationID: String { executionMode == "history" ? conversationID + "-history" : conversationID }
    @FocusState private var inputFocused: Bool
    private var availableCameras: [CameraDevice] {
        guard let skillID, let skill = store.skill(skillID) else { return store.data.cameras }
        return store.data.cameras.filter { skill.devices.contains($0.id) }
    }
    private var selectedCamera: CameraDevice? { cameraID == "all" ? nil : availableCameras.first { $0.id == cameraID } ?? availableCameras.first }
    private var activeRun: AgentRun? { runs.last { $0.isRunning } }
    private var canSend: Bool {
        !sending && activeRun == nil && !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && store.isConnected && store.data.agent.ready
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ConnectionBanner()
                    if let skillID, let skill = store.skill(skillID) {
                        NavigationLink(value: AppRoute.skill(skillID)) {
                            Label("正在讨论：\(skill.name)", systemImage: "shield")
                                .font(.subheadline).padding(12).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                    }
                    if showCamera && executionMode == "live" {
                        CameraFrame(camera: selectedCamera)
                        Text("需要看现场时，AI 会请求新画面，并显示设备与采集时间。")
                            .font(.caption).foregroundStyle(Brand.muted)
                    }
                    if runs.isEmpty { suggestions }
                    ForEach(runs) { run in
                        HStack {
                            Spacer(minLength: 36)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(run.message).textSelection(.enabled)
                                if run.executionMode == "history" {
                                    Text("\(run.cameraId.flatMap { store.camera($0)?.name } ?? "全部摄像头") · \(run.historyScope?.label ?? "按问题判断日期")")
                                        .font(.caption2).foregroundStyle(Brand.muted)
                                }
                            }.padding(14)
                                .background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius: 16))
                        }
                        reply(run)
                    }
                    if let syncError { Text(syncError).font(.caption).foregroundStyle(.orange) }
                    if let error { Text(error).font(.caption).foregroundStyle(.orange) }
                    Color.clear.frame(height: 1).id("bottom")
                }.padding(16)
            }
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .top, spacing: 0) { if executionMode == "live" { draftActions } }
            .safeAreaInset(edge: .bottom, spacing: 0) { composer }
            .onChange(of: runs.count) { _, _ in withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
            .onChange(of: activeRun?.status) { _, status in
                if status == nil { withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
        }
        .pageStyle(skillID == nil ? "AI 助手" : "任务对话")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if executionMode == "live" { Button { inputFocused = false; withAnimation { showCamera.toggle() } } label: {
                    Image(systemName: showCamera ? "video.fill" : "video")
                }.accessibilityLabel(showCamera ? "收起摄像头画面" : "查看摄像头画面") }
            }
        }
        .task(id: effectiveConversationID) {
            input = store.conversationDrafts[effectiveConversationID] ?? ""
            if cameraID.isEmpty { cameraID = skillID.flatMap { store.skill($0)?.target.cameraId } ?? store.selectedCameraID }
            while !Task.isCancelled {
                await reload()
                do { try await Task.sleep(for: .seconds(1)) } catch { break }
            }
        }
        .onChange(of: input) { _, value in store.conversationDrafts[effectiveConversationID] = value }
        .onDisappear { inputFocused = false }
        .sheet(isPresented: $rangeSheet) {
            HistoryRangeSheet(current: historyFilter) { historyFilter = $0; requestID = nil }
        }
        .sheet(isPresented: $voice) {
            NavigationStack {
                VoiceCaptureButton { text in
                    input = input.isEmpty ? text : input + "\n" + text
                    requestID = nil; voice = false; inputFocused = true
                }
                .padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
                .navigationTitle("说完后，先编辑再发送").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { voice = false } } }
            }.presentationDetents([.medium, .large])
        }
    }

    private var draftActions: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let draft = cameraDrafts.first {
                HStack {
                    Text("待编辑 · " + draft.name).font(.subheadline.bold()).lineLimit(1)
                    Spacer()
                    if cameraDrafts.count > 1 {
                        Menu("其他草案") { ForEach(cameraDrafts) { item in Button(item.name) { inputFocused = false; store.openEditor(item) } } }
                    }
                }
                HStack {
                    Button("编辑草案") { inputFocused = false; store.openEditor(draft) }.buttonStyle(.borderedProminent).accessibilityIdentifier("chat.editDraft")
                    Button("圈选画面") { inputFocused = false; store.openEditor(draft, regionCameraID: draft.target.cameraId) }.buttonStyle(.bordered).accessibilityIdentifier("chat.editRegion")
                    Spacer()
                    Button("新建") { Task { await createDraft(camera: selectedCamera?.id) } }.disabled(creatingDraft || selectedCamera == nil).accessibilityIdentifier("chat.newDraft")
                }
            } else {
                HStack {
                    Label("当前视角暂无待编辑草案", systemImage: "square.dashed").font(.caption)
                    Spacer()
                    Button(creatingDraft ? "创建中…" : "新建草案并圈选") { Task { await createDraft(camera: selectedCamera?.id) } }.font(.subheadline.bold()).disabled(creatingDraft || selectedCamera == nil).accessibilityIdentifier("chat.newDraft")
                }
            }
            Text("保存只保留草案；不会自动开始守护。").font(.caption2).foregroundStyle(Brand.muted)
        }.padding(.horizontal, 16).padding(.vertical, 8).background(.regularMaterial).disabled(!store.isConnected)
    }
    private func createDraft(camera: String?) async {
        guard let camera, !creatingDraft, store.isConnected else { return }
        creatingDraft = true; inputFocused = false; defer { creatingDraft = false }
        do {
            let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
            let prompt = String((text.isEmpty ? runs.last?.message ?? "请选择画面中的观察对象并完善提醒条件" : text).prefix(2000))
            let draft = try await store.client.createDraft(camera: camera, conversation: conversationID, prompt: prompt.count >= 2 ? prompt : "请选择画面中的观察对象并完善提醒条件", replacesID: skillID)
            await store.refresh()
            store.openEditor(draft, regionCameraID: camera)
        } catch { self.error = error.localizedDescription }
    }

    private var suggestions: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("你想关注什么？", systemImage: "sparkles").font(.title3.bold())
            Text(executionMode == "history" ? "可以查找已导入录像，也可以回顾已保存图片和事件。找到录像后，点击证据卡播放对应时间点；资料缺口会明确说明。" : "直接输入，或点麦克风说话。创建守护规则前，AI 会和你一起确认。")
                .font(.subheadline).foregroundStyle(Brand.muted)
            ForEach(executionMode == "history" ? ["查录像：包裹什么时候被拿走？找到片段并定位时间点。", "回顾今天已保存的观察记录，说明有哪些资料缺口。", "查找有人放下包裹的录像，说明动作的先后顺序。"] : skillID == nil ? ["看住这个箱子，离开区域时提醒我。", "我关心的任务现在怎么样？", "帮我找一下最近的观察记录。"] : ["请重新查看任务现场，并说明当前状态。", "解释一下这项守护的提醒条件。", "我想调整这项任务的提醒条件。"], id: \.self) { prompt in
                Button { input = prompt; requestID = nil; inputFocused = true } label: {
                    HStack { Text(prompt).multilineTextAlignment(.leading); Spacer(); Image(systemName: "arrow.up.left") }
                        .font(.subheadline).padding(13).frame(maxWidth: .infinity, alignment: .leading)
                        .background(.white).clipShape(RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain)
            }
        }.padding(.top, 8)
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 9) {
            Picker("执行方式", selection: Binding(get: { executionMode }, set: { value in
                store.conversationDrafts[effectiveConversationID] = input
                executionMode = value; runs = []; events = []; error = nil; syncError = nil
                requestID = nil; pendingMessage = nil; showCamera = false
                input = store.conversationDrafts[effectiveConversationID] ?? ""
                if value == "live" && cameraID == "all" { cameraID = availableCameras.first?.id ?? "" }
            })) {
                Text("实时守护").tag("live")
                Text("历史回顾").tag("history")
            }.pickerStyle(.segmented).disabled(sending).accessibilityIdentifier("chat.mode")
            Text(executionMode == "history" ? "只读已存资料 · 不占用实时守护 · 不取新画面" : "每台摄像头同时运行一个实时 Skill，启用前需确认")
                .font(.caption2).foregroundStyle(Brand.muted)
            HStack(spacing: 8) {
                if !availableCameras.isEmpty {
                    Menu {
                        Picker("观察视角", selection: $cameraID) {
                            if executionMode == "history" { Text("全部绑定摄像头").tag("all") }
                            ForEach(availableCameras) { camera in Text(camera.name).tag(camera.id) }
                        }
                    } label: {
                        Label(selectedCamera?.name ?? "全部摄像头", systemImage: "video")
                            .font(.caption).lineLimit(1)
                    }.accessibilityLabel("选择对话摄像头")
                }
                Spacer()
                if activeRun != nil { Text("回复中，可先编辑下一条").font(.caption2).foregroundStyle(Brand.muted) }
                else if executionMode == "live" { Button("请 AI 查看画面") { input = "请调用当前摄像头拍一张新画面，告诉我看到了什么。"; inputFocused = true }.font(.caption).accessibilityIdentifier("chat.inspect") }
                else {
                    Button("查录像") { input = "查录像：包裹什么时候被拿走？找到正确片段并定位时间点。"; requestID = nil; inputFocused = true }.font(.caption).accessibilityIdentifier("chat.findVideo")
                    NavigationLink(value: AppRoute.recordings) { Label("录像库", systemImage: "film").font(.caption) }
                }
            }
            if executionMode == "history" {
                Button { inputFocused = false; rangeSheet = true } label: {
                    HStack { Image(systemName: "calendar"); Text(historyFilter?.label ?? "日期：按问题判断").lineLimit(1); Spacer(); Image(systemName: "chevron.down") }
                        .font(.caption).padding(.vertical, 3)
                }.accessibilityLabel("查询时间范围：\(historyFilter?.label ?? "按问题判断")").accessibilityIdentifier("chat.historyRange")
            }
            if executionMode == "live", let selectedCamera, let owner = store.data.skills.first(where: { $0.status == "active" && $0.devices.contains(selectedCamera.id) }) {
                Text("正在守护：\(owner.name) · 查看新画面沿用此任务，不切换守护")
                    .font(.caption2).foregroundStyle(Brand.blue)
            }
            HStack(alignment: .bottom, spacing: 8) {
                Button { inputFocused = false; voice = true } label: {
                    Image(systemName: "mic").font(.system(size: 21)).frame(width: 44, height: 44)
                }.accessibilityLabel("语音输入").accessibilityIdentifier("chat.voice")
                TextField("输入消息，和 AI 沟通…", text: $input, axis: .vertical)
                    .lineLimit(1...5).focused($inputFocused)
                    .padding(.horizontal, 12).padding(.vertical, 12)
                    .background(Brand.background).clipShape(RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Brand.blue.opacity(0.22), lineWidth: 1))
                    .accessibilityLabel("消息输入框").accessibilityIdentifier("chat.input")
                Button { Task { await send() } } label: {
                    Group { if sending { ProgressView() } else { Image(systemName: "arrow.up").font(.headline) } }
                        .frame(width: 44, height: 44).foregroundStyle(canSend ? .white : Brand.muted)
                        .background(canSend ? Brand.blue : Brand.background).clipShape(Circle())
                }.disabled(!canSend).accessibilityLabel("发送消息").accessibilityIdentifier("chat.send")
            }
            if !store.isConnected || !store.data.agent.ready {
                Button { store.path.append(.settings) } label: {
                    Label(store.isConnected ? "AI 服务未就绪，检查连接" : "服务未连接，输入内容会保留", systemImage: "exclamationmark.circle")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
        }
        .padding(.horizontal, 12).padding(.top, 10).padding(.bottom, 10)
        .background(.regularMaterial)
    }

    private func reply(_ run: AgentRun) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("AI 助手", systemImage: "sparkles").font(.caption.bold()).foregroundStyle(Brand.blue)
            if run.isRunning {
                HStack { ProgressView(); Text(events.last?.progressLabel ?? "正在处理…").font(.subheadline) }
                Button("停止本次回复", role: .cancel) { Task { await cancel(run) } }.accessibilityIdentifier("chat.cancel")
            }
            if let text = run.text {
                Text((try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(text)).textSelection(.enabled)
            }
            if let error = run.error {
                Text(error).foregroundStyle(.orange).font(.subheadline)
                Button("编辑后重试") { prepareRetry(run) }
            }
            ForEach(run.captures ?? []) { capture in
                VStack(alignment: .leading, spacing: 8) {
                    Label(store.camera(capture.cameraId)?.name ?? capture.cameraId, systemImage: "video")
                        .font(.subheadline.bold())
                    if capture.status == "completed", let url = store.client.absoluteURL(capture.imageUrl) {
                        if let draft = draftForCapture(capture) {
                            DraftFramePreview(url: url, skill: draft, cameraID: capture.cameraId)
                            Text("蓝框：关注区域 · 橙框：目标 · 草案框待确认，尚未启用").font(.caption).foregroundStyle(Brand.muted)
                        } else { EvidenceImage(url: url) }
                        Text("\(capture.historical == true ? "历史资料 · " : "")采集于 \(displayTime(capture.capturedAt)) · \(capture.sourceType == "fixture" ? "测试画面" : "设备画面")")
                            .font(.caption).foregroundStyle(Brand.muted)
                        if executionMode == "live" && capture.historical != true {
                            if let draft = draftForCapture(capture) {
                                Button("圈选此摄像头的目标与区域") { inputFocused = false; store.openEditor(draft, regionCameraID: capture.cameraId) }.accessibilityIdentifier("chat.capture.editRegion")
                            } else {
                                Button("为此摄像头新建草案并圈选") { Task { await createDraft(camera: capture.cameraId) } }.disabled(creatingDraft || !store.isConnected).accessibilityIdentifier("chat.capture.newDraft")
                            }
                        }
                    } else { Text(capture.reason).font(.caption).foregroundStyle(.orange) }
                }.padding(12).background(Brand.background).clipShape(RoundedRectangle(cornerRadius: 12))
            }
            ForEach(run.videos ?? []) { video in
                NavigationLink(value: AppRoute.video(video.recordingId, video.seekSeconds)) {
                    VStack(alignment: .leading, spacing: 8) {
                        Label(video.verdictLabel, systemImage: video.verdict == "matched" ? "checkmark.circle" : "questionmark.circle")
                            .font(.subheadline.bold()).foregroundStyle(video.verdict == "matched" ? Brand.blue : .orange)
                        Text(video.summary).font(.subheadline).foregroundStyle(.primary)
                        Text("\(store.camera(video.cameraId)?.name ?? video.cameraId) · \(video.title)").font(.caption).foregroundStyle(Brand.muted)
                        if !video.limitation.isEmpty { Text(video.limitation).font(.caption).foregroundStyle(Brand.muted) }
                        Label("\(video.verdict == "matched" ? "核验动作" : "查看候选") · \(videoTime(video.seekSeconds))", systemImage: "play.circle.fill").font(.headline)
                        Text(video.recordedAt == nil ? "拍摄日期未知 · 显示录像内时间，定位为模型估计" : "录像始于 \(displayTime(video.recordedAt)) · 定位为模型估计")
                            .font(.caption2).foregroundStyle(Brand.muted)
                    }.padding(14).frame(maxWidth: .infinity, alignment: .leading).background(Brand.background).clipShape(RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain).accessibilityIdentifier("chat.video.\(video.id)")
            }
            if (run.videos ?? []).contains(where: { $0.verificationStatus == "failed" }) {
                Button("复核未完成，编辑后重试") { prepareRetry(run) }.font(.subheadline)
            }
            if let draft = run.draft {
                let current = store.skill(draft.id) ?? draft
                Button {
                    inputFocused = false
                    if current.status == "draft" { store.openEditor(current) } else { store.path.append(.skill(current.id)) }
                } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        Label(current.name, systemImage: "doc.badge.gearshape").font(.headline)
                        Text(current.status == "draft" ? "编辑对象、区域与条件；保存不会启用，验收通过后才能继续" : "查看任务当前状态").font(.caption)
                        Text(current.status == "draft" ? "编辑草案 →" : "查看任务 →").font(.subheadline.bold())
                    }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Brand.background).clipShape(RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain).accessibilityIdentifier("chat.draft")
            }
            if !run.toolReceipts.isEmpty {
                DisclosureGroup("本次操作（\(run.toolReceipts.count)）") {
                    ForEach(Array(run.toolReceipts.enumerated()), id: \.offset) { _, receipt in
                        Text("\(toolLabel(receipt.tool)) · \(receipt.status == "completed" ? "已完成" : "未完成")")
                            .font(.caption).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading).cardStyle().id(run.id)
    }

    private func prepareRetry(_ run: AgentRun) {
        input = run.message; requestID = nil
        if executionMode == "history" {
            historyFilter = run.historyFilter
            cameraID = run.cameraId ?? "all"
        }
        inputFocused = true
    }
    private func reload() async {
        let id = effectiveConversationID
        do {
            let loaded = try await store.client.conversation(id)
            guard id == effectiveConversationID && !Task.isCancelled else { return }
            runs = loaded
            if let run = activeRun {
                let loadedEvents = try await store.client.events(run.id)
                if id == effectiveConversationID { events = loadedEvents }
            }
            syncError = nil
        } catch { if !Task.isCancelled { self.syncError = "对话暂未同步，输入内容已保留。" } }
    }
    private func send() async {
        guard canSend else { return }
        sending = true; defer { sending = false }
        let message = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let filter = executionMode == "history" ? historyFilter : nil
        let filterKey = filter.flatMap { try? JSONEncoder().encode($0) }.flatMap { String(data: $0, encoding: .utf8) } ?? "auto"
        let signature = "\(message)|\(effectiveConversationID)|\(selectedCamera?.id ?? "all")|\(filterKey)"
        if pendingMessage != signature { requestID = nil }; pendingMessage = signature
        let id = requestID ?? "run-\(UUID().uuidString)"; requestID = id
        do {
            let run = try await store.client.start(message: message, conversation: effectiveConversationID, skill: skillID, camera: selectedCamera?.id, requestID: id, executionMode: executionMode, historyFilter: filter)
            events = []
            if !runs.contains(where: { $0.id == run.id }) { runs.append(run) }
            if input.trimmingCharacters(in: .whitespacesAndNewlines) == message { input = ""; store.conversationDrafts[effectiveConversationID] = "" }
            inputFocused = false; requestID = nil; error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func cancel(_ run: AgentRun) async {
        do { _ = try await store.client.cancel(run.id); await reload() }
        catch { self.error = error.localizedDescription }
    }
    private func toolLabel(_ name: String) -> String {
        ["search_recordings":"检索录像并观看片段复核", "read_stored_image":"读取历史图片", "request_camera_snapshot":"请求摄像头新画面", "list_camera_capabilities":"读取设备", "list_tasks":"查询任务", "get_task_state":"读取状态", "search_evidence":"检索证据", "draft_visual_skill":"生成草案", "request_recheck":"重新观察"][name] ?? name
    }
}

private struct HistoryRangeSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var period: String
    @State private var start: Date
    @State private var end: Date
    var apply: (HistoryFilter?) -> Void
    init(current: HistoryFilter?, apply: @escaping (HistoryFilter?) -> Void) {
        self.apply = apply
        _period = State(initialValue: current?.period ?? "auto")
        _start = State(initialValue: current?.startAt.map(Date.init(timeIntervalSince1970:)) ?? Date().addingTimeInterval(-86400))
        _end = State(initialValue: current?.endAt.map(Date.init(timeIntervalSince1970:)) ?? Date())
    }
    var body: some View {
        NavigationStack {
            Form {
                Section("查询范围") {
                    Picker("日期", selection: $period) {
                        Text("按本次问题判断").tag("auto")
                        Text("全部日期（包括未知日期）").tag("all")
                        Text("今天").tag("today")
                        Text("昨天").tag("yesterday")
                        Text("过去 24 小时").tag("last_24_hours")
                        Text("自定义时间").tag("custom")
                    }.pickerStyle(.inline)
                    if period == "custom" {
                        DatePicker("开始", selection: $start)
                        DatePicker("结束", selection: $end)
                        if start >= end { Text("结束时间需要晚于开始时间").foregroundStyle(.orange) }
                    }
                }
                Section {
                    Text("手动选择的范围优先于对话内容，助手不能扩大范围。今天和昨天按北京时间计算；自定义时间按手机当前时区显示。拍摄日期未知的录像仅在不限日期时参与检索。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }.navigationTitle("录像与证据时间范围").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("应用") {
                            apply(period == "auto" ? nil : HistoryFilter(period: period, startAt: period == "custom" ? start.timeIntervalSince1970 : nil, endAt: period == "custom" ? end.timeIntervalSince1970 : nil))
                            dismiss()
                        }.disabled(period == "custom" && start >= end).accessibilityIdentifier("historyRange.apply")
                    }
                }
        }
    }
}

private struct DraftFramePreview: View {
    var url: URL
    var skill: VisualSkill
    var cameraID: String
    var body: some View {
        AsyncImage(url: url) { phase in
            if let image = phase.image {
                image.resizable().scaledToFit().overlay {
                    GeometryReader { proxy in
                        if let region = skill.regions[cameraID] { box(region, color: .blue, size: proxy.size) }
                        if skill.target.cameraId == cameraID { box(skill.target.box, color: .orange, size: proxy.size) }
                    }.allowsHitTesting(false)
                }
            } else { EvidenceImage(url: url) }
        }.clipShape(RoundedRectangle(cornerRadius: 12))
    }
    private func box(_ roi: ROI, color: Color, size: CGSize) -> some View {
        Rectangle().stroke(color, style: StrokeStyle(lineWidth: 2, dash: [6,3]))
            .frame(width: size.width * roi.width, height: size.height * roi.height)
            .position(x: size.width * (roi.x + roi.width / 2), y: size.height * (roi.y + roi.height / 2))
    }
}
