import SwiftUI
import UniformTypeIdentifiers
import AVKit

struct EvidenceView: View {
    @EnvironmentObject var store: AppStore
    var skillID: String? = nil
    @State private var filter = "all"
    private var items: [EvidenceItem] { store.data.evidence.filter { (skillID == nil || $0.skillId == skillID) && (filter == "all" || $0.relation == filter) } }
    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                ConnectionBanner()
                NavigationLink(value: AppRoute.recordings) {
                    HStack { Label("录像库", systemImage: "film"); Spacer(); Text("\(store.data.recordings?.count ?? 0) 段"); Image(systemName: "chevron.right") }.font(.subheadline).padding(16).cardStyle()
                }
                Picker("证据筛选", selection: $filter) { Text("全部").tag("all"); Text("区域外").tag("outside"); Text("区域内").tag("inside"); Text("无法确认").tag("unknown") }.pickerStyle(.segmented)
                if items.isEmpty { EmptyState(title: "暂无对应证据", detail: "任务产生新的状态变化后，会保存关联画面和采集时间。", icon: "doc.text.magnifyingglass") }
                ForEach(items) { item in
                    NavigationLink(value: AppRoute.evidence(item.id)) {
                        HStack(spacing: 12) {
                            Image(systemName: item.relation == "outside" ? "exclamationmark.triangle" : "photo").font(.title2).foregroundStyle(Brand.blue).frame(width: 36)
                            VStack(alignment: .leading, spacing: 6) { Text(item.title).font(.headline); Text(store.skill(item.skillId)?.name ?? (item.sourceType == "official_sdk" ? "官方设备事件" : item.sourceType == "synthetic_demo" ? "门廊测试场景" : "守护任务")).font(.subheadline); Text(displayTime(item.capturedAt)).font(.caption).foregroundStyle(Brand.muted) }
                            Spacer(); Image(systemName: "chevron.right").font(.caption)
                        }.padding(16).cardStyle()
                    }.buttonStyle(.plain)
                }
            }.padding(16)
        }.pageStyle(skillID == nil ? "证据" : "任务证据").refreshable { await store.refresh() }
    }
}
struct EvidenceDetailView: View {
    @EnvironmentObject var store: AppStore
    let id: String
    @State private var exporting = false
    @State private var document = EvidenceDocument(text: "")
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let item = store.data.evidence.first(where: { $0.id == id }) {
                    Text(item.title).font(.title2.bold())
                    Text((item.sourceType == "synthetic_demo" ? "生成于 " : "") + displayTime(item.capturedAt)).font(.subheadline).foregroundStyle(Brand.muted)
                    if item.videoUrl != nil {
                        NavigationLink(value: AppRoute.replayVideo(item.id, item.seekSeconds ?? 0)) { Label("播放触发片段 · \(videoTime(item.originalEventTime ?? 0))", systemImage: "play.circle.fill") }.buttonStyle(PrimaryAction())
                        Text("回放测试生成的提醒；记录时间不是原录像拍摄时间。证据只包含触发时已到达的画面。").font(.caption).foregroundStyle(.orange)
                    } else { EvidenceImage(url: store.client.absoluteURL(item.imageUrl)) }
                    GroupBox("观察依据") { VStack(alignment: .leading, spacing: 10) { Text(item.reason); Text("来源设备：\(store.camera(item.cameraId)?.name ?? item.cameraId)"); if !item.skillId.isEmpty { Text("规则版本：\(item.revision)") }; Text(item.sourceType == "fixture" ? "来源：合成摄像头测试画面" : item.sourceType == "synthetic_demo" ? "来源：合成测试样本 · 非摄像头实拍，时间为生成时间" : item.sourceType == "official_sdk" ? "来源：官方事件缩略图 · 时间为设备事件时间" : "来源：\(item.sourceType)") }.font(.subheadline).frame(maxWidth: .infinity, alignment: .leading) }
                    if !item.skillId.isEmpty { NavigationLink(value: AppRoute.skill(item.skillId)) { Label("查看所属任务", systemImage: "shield") } }
                    if ["official_sdk", "synthetic_demo"].contains(item.sourceType) {
                        NavigationLink(value: AppRoute.evidenceConversation(item.id)) { Label("向 AI 追问这条事件", systemImage: "bubble.left") }.buttonStyle(PrimaryAction())
                    } else {
                        Button { store.openAI(prompt: "请根据证据解释这次观察：\(item.id)", skillID: item.skillId) } label: { Label("向 AI 追问", systemImage: "bubble.left") }.buttonStyle(PrimaryAction())
                    }
                    HStack {
                        Button("导出证据记录") { document = EvidenceDocument(text: item.exportText); exporting = true }.buttonStyle(.bordered)
                        ShareLink(item: item.exportText) { Label("分享记录", systemImage: "square.and.arrow.up") }.buttonStyle(.bordered)
                    }
                    Text("导出包含来源、记录时间、规则版本与证据 ID；回放证据可在上方播放，图片读取失败时不使用示例图替代。").font(.caption).foregroundStyle(Brand.muted)
                } else { EmptyState(title: "未找到证据", detail: "请返回列表重新加载。") }
            }.padding(16)
        }.pageStyle("证据详情")
        .fileExporter(isPresented: $exporting, document: document, contentType: .plainText, defaultFilename: "EvidenceGuard-证据记录") { result in if case .failure(let error) = result { store.errorMessage = error.localizedDescription } }
    }
}
struct EvidenceImage: View {
    let url: URL?
    var body: some View {
        Color.black.opacity(0.04).aspectRatio(1.6, contentMode: .fit).overlay {
            if let url { AsyncImage(url: url) { phase in
                switch phase { case .success(let image): image.resizable().scaledToFit(); case .failure: Label("证据图片当前不可读取", systemImage: "photo.badge.exclamationmark").font(.caption); default: ProgressView() }
            } } else { Text("此记录没有附图").foregroundStyle(Brand.muted) }
        }.clipShape(RoundedRectangle(cornerRadius: 16))
    }
}
struct EvidenceDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.plainText] }
    var text: String
    init(text: String) { self.text = text }
    init(configuration: ReadConfiguration) throws { text = String(data: configuration.file.regularFileContents ?? Data(), encoding: .utf8) ?? "" }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: Data(text.utf8)) }
}

struct RecordingLibraryView: View {
    @EnvironmentObject var store: AppStore
    @State private var importing = false
    @State private var uploading = false
    @State private var cameraID = ""
    @State private var knownDate = false
    @State private var recordedAt = Date()
    @State private var error: String?
    var body: some View {
        List {
            Section("导入录像") {
                Picker("来源摄像头", selection: $cameraID) { ForEach(store.data.cameras) { c in Text(c.name).tag(c.id) } }
                Toggle("我知道录像的拍摄开始时间", isOn: $knownDate)
                if knownDate { DatePicker("录像开始", selection: $recordedAt) }
                Text("选择视频后，会上传到当前服务并交给已配置的模型建立索引。日期未知时只显示录像内时间，不以导入时间代替。支持 10 分钟内、150 MB 内的视频。").font(.caption).foregroundStyle(Brand.muted)
                Button { importing = true } label: {
                    HStack { if uploading { ProgressView() }; Label(uploading ? "正在上传…" : "从文件导入录像", systemImage: "square.and.arrow.up") }
                }.disabled(uploading || cameraID.isEmpty || !store.isConnected)
                if store.data.videoModels?.embeddingReady == false { Text("Embedding 未配置，录像可保存，但语义索引尚不能完成。").font(.caption).foregroundStyle(.orange) }
                if let error { Text(error).font(.caption).foregroundStyle(.orange) }
            }
            Section("已保存录像") {
                if (store.data.recordings ?? []).isEmpty { Text("还没有录像。导入后可在 AI 的“历史回顾”中用一句话查找。").font(.subheadline).foregroundStyle(Brand.muted) }
                ForEach(store.data.recordings ?? []) { video in
                    VStack(alignment: .leading, spacing: 10) {
                        NavigationLink(value: AppRoute.video(video.id, 0)) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(video.title).font(.headline)
                                Text("\(video.stateLabel) · \(video.duration.map(videoTime) ?? "处理中")").font(.caption)
                                Text(video.recordedAt == nil ? "拍摄日期未知" : displayTime(video.recordedAt)).font(.caption).foregroundStyle(Brand.muted)
                            }
                        }
                        if let reason = video.error { Text(reason).font(.caption).foregroundStyle(.orange) }
                        if ["failed", "interrupted", "stale"].contains(video.status) {
                            Button("重新建立索引") { Task { await store.perform { _ = try await store.client.indexRecording(video.id) } } }
                        }
                    }
                }
            }
        }.pageStyle("录像库")
        .onAppear { if cameraID.isEmpty { cameraID = store.selectedCameraID } }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.movie, .mpeg4Movie], allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first { Task { await upload(url) } }
            case .failure(let problem): error = problem.localizedDescription
            }
        }
    }
    private func upload(_ url: URL) async {
        uploading = true; error = nil; defer { uploading = false }
        do {
            _ = try await store.client.uploadRecording(url, camera: cameraID, recordedAt: knownDate ? recordedAt.timeIntervalSince1970 : nil)
            await store.refresh(); store.toast = "录像已保存，正在建立视频索引"
        } catch { self.error = error.localizedDescription }
    }
}

struct RecordingPlayerView: View {
    @EnvironmentObject var store: AppStore
    let id: String
    let offset: Double
    var replayEvidence = false
    var trialEvidence = false
    @State private var recording: VideoRecording?
    @State private var player: AVPlayer?
    @State private var error: String?
    @State private var ready = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let recording {
                    Text(recording.title).font(.title2.bold())
                    Text("\(store.camera(recording.cameraId)?.name ?? recording.cameraId) · \(recording.duration.map(videoTime) ?? "")").font(.subheadline).foregroundStyle(Brand.muted)
                    if let player { VideoPlayer(player: player).aspectRatio(16/9, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: 14)).accessibilityIdentifier("evidence.videoPlayer") }
                    if !ready && error == nil { ProgressView("正在加载录像并定位…") }
                    if ready {
                        Button("从定位前 3 秒播放") { Task { await seek() } }.buttonStyle(.bordered).accessibilityIdentifier("video.playContext")
                        Button { Task { await seek(preroll: false) } } label: { Label("\(recording.timestampMeaning == "sample_confirmation" ? "跳到确认采样" : "跳到模型定位") \(videoTime(offset))", systemImage: "backward.end") }.buttonStyle(.borderedProminent)
                    }
                    Text(recording.recordedAt == nil ? "拍摄日期未知。\(videoTime(offset)) 表示当前视频内的播放时间，不是当天的时钟时间。" : "录像开始：\(displayTime(recording.recordedAt))\n当前证据定位：\(videoTime(offset))")
                        .font(.subheadline)
                    Text(recording.timestampMeaning == "sample_confirmation" ? "此位置是达到确认跨度的采样时刻，不是精确的拿取时间。请回看前后画面；采样间隔内的短暂动作可能未被检测。" : "动作时间由模型估计。请播放前后画面核验；不会仅凭相似度认定事件发生。播放版本经过兼容转码，导入原文件和来源摘要保存在服务端。").font(.caption).foregroundStyle(Brand.muted)
                    if recording.sourceType == "trial" { Text("仅为试跑结果，不是真实告警，也不代表规则已启用。").font(.caption).foregroundStyle(.orange) }
                    else if recording.sourceType == "replay" { Text("来源：导入录像的回放片段，非摄像头实时画面。").font(.caption).foregroundStyle(.orange) }
                    else if recording.sourceType == "public_sample" { Text("来源：公开数据集测试样例，非已连接的家庭摄像头。").font(.caption).foregroundStyle(.orange) }
                }
                if let error { Text(error).foregroundStyle(.orange) }
            }.padding(16)
        }.pageStyle("录像证据")
        .task(id: id) {
            do {
                ready = false; error = nil
                let value = try await (trialEvidence ? store.client.trialRecording(id) : replayEvidence ? store.client.replayRecording(id) : store.client.recording(id)); recording = value
                guard let url = store.client.absoluteURL(value.playbackUrl) else { throw APIProblem(message: "录像播放地址无效") }
                let cookies = HTTPCookieStorage.shared.cookies(for: url) ?? []
                let asset = AVURLAsset(url: url, options: [AVURLAssetHTTPCookiesKey: cookies])
                guard try await asset.load(.isPlayable) else { throw APIProblem(message: "录像当前不可播放") }
                guard !Task.isCancelled else { return }
                player = AVPlayer(playerItem: AVPlayerItem(asset: asset))
                await seek(); ready = true
            } catch { if !Task.isCancelled { self.error = "录像加载失败：\(error.localizedDescription)" } }
        }
        .onDisappear { player?.pause() }
    }
    private func seek(preroll: Bool = true) async {
        guard let player else { return }
        let seconds = min(max(0, offset - (preroll ? 3 : 0)), max(0, (recording?.duration ?? offset) - 0.1))
        error = nil
        let completed = await player.seek(to: CMTime(seconds: seconds, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        if !Task.isCancelled && completed { player.play() }
        else if !Task.isCancelled { error = "无法定位此时间点，请重试" }
    }
}
