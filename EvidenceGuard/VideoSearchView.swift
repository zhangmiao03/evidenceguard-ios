import SwiftUI
import UIKit
import PhotosUI
import UniformTypeIdentifiers

struct VideoSearchSeed {
    let imagePath: String
    let cameraID: String
    let origin: URL
    let label: String
}

struct VideoSearchView: View {
    @EnvironmentObject private var store: AppStore
    let seed: VideoSearchSeed?
    init(seed: VideoSearchSeed? = nil) { self.seed = seed }
    @State private var loadingSeed = false
    @State private var seedLoaded = false
    @State private var text = ""
    @State private var camera = "all"
    @State private var period = "all"
    @State private var from = Date().addingTimeInterval(-86400)
    @State private var until = Date()
    @State private var photo: PhotosPickerItem?
    @State private var reference: UIImage?
    @State private var filePicker = false
    @State private var crop = false
    @State private var submitting = false
    @State private var result: VideoSearchResult?
    @State private var searchID: String?
    @State private var resultOrigin: URL?
    @State private var refreshID = UUID()
    @State private var error: String?

    private var canSubmit: Bool {
        store.isConnected && store.data.videoModels?.retrievalVersion == 2 && store.data.videoModels?.embeddingReady == true && !submitting && !loadingSeed && result?.isRunning != true &&
        (!text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || reference != nil) &&
        text.count <= 1000 &&
        (period != "custom" || from < until)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 14) {
                    Label("找回你关心的片刻", systemImage: "sparkle.magnifyingglass").font(.title2.bold())
                    Text("描述一件事，或添加目标照片。在已保存录像中寻找相关片段，再查看原片核对。").font(.subheadline).foregroundStyle(Brand.muted)
                    if let seed {
                        Text("入口：\(seed.label)。可替换参考图；请确认当前图片、摄像头与时间范围后开始检索。").font(.caption).foregroundStyle(Brand.muted)
                        if loadingSeed { ProgressView("正在读取所选证据画面…") }
                        if !loadingSeed && !seedLoaded { Button("重新读取证据画面") { Task { await loadSeed() } } }
                    }
                    if store.data.videoModels?.retrievalVersion != 2 {
                        Text("当前服务尚未开启新版图文检索。请升级云端服务；原有助手历史查询仍可使用。").font(.subheadline).foregroundStyle(.orange)
                    } else if store.data.videoModels?.embeddingReady != true {
                        Text("当前服务尚未配置录像检索模型，请联系团队完成配置。").font(.subheadline).foregroundStyle(.orange)
                    }
                    TextField("例如：有人把蓝色背包放到门边", text: $text, axis: .vertical)
                        .lineLimit(2...4).padding(12).background(Brand.background).clipShape(RoundedRectangle(cornerRadius: 12))
                        .accessibilityIdentifier("videoSearch.text")
                    if text.count > 1000 { Text("检索文字请控制在 1000 字以内，当前输入已保留。").font(.caption).foregroundStyle(.orange) }
                    if let reference {
                        HStack(alignment: .top) {
                            Image(uiImage: reference).resizable().scaledToFit().frame(width: 112, height: 112).clipShape(RoundedRectangle(cornerRadius: 12))
                            VStack(alignment: .leading, spacing: 10) {
                                Text("参考图片").font(.headline)
                                Text("未裁剪时使用整张图片；只比较可见外观。").font(.caption).foregroundStyle(Brand.muted)
                                HStack {
                                    Button("裁剪目标") { crop = true }.accessibilityIdentifier("videoSearch.crop")
                                    Button("移除", role: .destructive) { self.reference = nil; photo = nil }
                                }.font(.subheadline)
                            }
                        }
                    }
                    HStack(spacing: 16) {
                        PhotosPicker(selection: $photo, matching: .images) { Label("添加参考图片", systemImage: "photo") }
                            .accessibilityIdentifier("videoSearch.photo")
                        Button { filePicker = true } label: { Label("文件", systemImage: "folder") }
                    }.font(.subheadline)
                    Text("参考图会上传至当前服务，并发送给已配置的检索与核验模型。").font(.caption).foregroundStyle(Brand.muted)
                    Divider()
                    Picker("摄像头", selection: $camera) {
                        Text("全部摄像头").tag("all")
                        ForEach(store.data.cameras) { Text($0.name).tag($0.id) }
                    }
                    Picker("拍摄时间", selection: $period) {
                        Text("全部日期").tag("all"); Text("今天").tag("today"); Text("昨天").tag("yesterday")
                        Text("过去 24 小时").tag("last_24_hours"); Text("自定义").tag("custom")
                    }
                    if period == "custom" {
                        DatePicker("开始", selection: $from); DatePicker("结束", selection: $until)
                        if from >= until { Text("结束时间应晚于开始时间").font(.caption).foregroundStyle(.orange) }
                    }
                    Text("按手机时区 \(TimeZone.current.identifier) 筛选。拍摄日期未知的录像仅出现在“全部日期”。文字中的日期不会自动扩大这里的范围。").font(.caption).foregroundStyle(Brand.muted)
                    Button { Task { await submit() } } label: {
                        HStack { if submitting { ProgressView() }; Label(submitting ? "正在提交…" : "检索录像", systemImage: "magnifyingglass") }.frame(maxWidth: .infinity)
                    }.buttonStyle(.borderedProminent).disabled(!canSubmit).accessibilityIdentifier("videoSearch.submit")
                }.padding(18).background(.white).clipShape(RoundedRectangle(cornerRadius: 22))

                if let error {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(error).foregroundStyle(.orange)
                        if searchID != nil { Button("刷新本次结果") { refreshID = UUID() } }
                    }.font(.subheadline)
                }
                if let result {
                    querySummary(result)
                    ForEach(result.videos) { hit in card(hit) }
                    if !result.isRunning && !result.videos.isEmpty {
                        NavigationLink {
                            ConversationView(conversationID: "video-search-\(result.id)", skillID: nil, initialMode: "history", videoSearchContext: result)
                        } label: { Label("带着本次条件继续问助手", systemImage: "bubble.left.and.bubble.right") }
                    }
                }
            }.padding(16)
        }.pageStyle("录像检索")
        .task { await loadSeed() }
        .task(id: photo) {
            guard let photo else { return }
            do {
                guard let data = try await photo.loadTransferable(type: Data.self) else { throw APIProblem(message: "无法读取图片") }
                try select(data)
            } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
        }
        .task(id: "\(searchID ?? "")-\(refreshID)-\(store.client.baseURL.absoluteString)") { await poll() }
        .onChange(of: store.client.baseURL) { _, _ in
            result = nil; searchID = nil; resultOrigin = nil; error = nil
            if seed != nil { reference = nil; seedLoaded = false; camera = "all" }
        }
        .fileImporter(isPresented: $filePicker, allowedContentTypes: [.image]) { choice in
            do {
                let url = try choice.get()
                let secured = url.startAccessingSecurityScopedResource(); defer { if secured { url.stopAccessingSecurityScopedResource() } }
                let size = (try url.resourceValues(forKeys: [.fileSizeKey])).fileSize ?? 0
                guard size <= 20_000_000 else { throw APIProblem(message: "请选择 20 MB 内的图片") }
                try select(Data(contentsOf: url))
            } catch { self.error = error.localizedDescription }
        }
        .sheet(isPresented: $crop) {
            if let reference { VideoReferenceCrop(image: reference) { self.reference = $0 } }
        }
    }

    private func loadSeed() async {
        guard let seed, !seedLoaded, !loadingSeed else { return }
        guard seed.origin == store.client.baseURL else { error = "服务已切换，请返回当前服务的证据重新选择。"; return }
        guard store.camera(seed.cameraID) != nil else { error = "该证据的来源摄像头已不在当前服务中，请返回重新选择。"; return }
        loadingSeed = true; defer { loadingSeed = false }
        let client = store.client.scoped()
        do {
            let data = try await client.videoSearchImage(seed.imagePath)
            guard !Task.isCancelled, seed.origin == store.client.baseURL else { return }
            guard store.camera(seed.cameraID) != nil else { throw APIProblem(message: "来源摄像头已移除，请重新选择。") }
            try select(data)
            camera = seed.cameraID
            seedLoaded = true
        } catch { if !Task.isCancelled && seed.origin == store.client.baseURL { self.error = error.localizedDescription } }
    }

    private func querySummary(_ value: VideoSearchResult) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { if value.isRunning { ProgressView() }; Text(value.stateLabel).font(.headline) }
            if let query = value.query.text, !query.isEmpty { Text(query).font(.subheadline) }
            if let image = value.query.image_ref {
                VideoSearchThumbnail(path: "/api/video-search-images/\(image)").frame(width: 88, height: 88).clipShape(RoundedRectangle(cornerRadius: 12))
            }
            Text(value.scope.cameraIds.map { store.camera($0)?.name ?? $0 }.joined(separator: "、")).font(.caption)
            Text(value.scope.startAt.map { "\(displayTime($0)) — \(displayTime(value.scope.endAt))" } ?? "全部日期，包含拍摄日期未知的录像")
                .font(.caption).foregroundStyle(Brand.muted)
            Text(value.reason).font(.caption).foregroundStyle(Brand.muted)
            if value.indexChanged || value.removedCandidates > 0 { Text("录像库已更新，部分结果可能已移除。可重新检索获取最新结果。").font(.caption).foregroundStyle(.orange) }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func card(_ hit: VideoHit) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let path = hit.thumbnailUrl { VideoSearchThumbnail(path: path).frame(height: 172).clipped().clipShape(RoundedRectangle(cornerRadius: 12)) }
            Label(hit.verdictLabel, systemImage: hit.verdict == "matched" ? "checkmark.circle" : "questionmark.circle").font(.headline)
                .foregroundStyle(hit.verdict == "matched" ? Brand.blue : Brand.muted)
            Text(hit.summary).font(.subheadline)
            Text("\(store.camera(hit.cameraId)?.name ?? hit.cameraId) · \(hit.title)").font(.caption).foregroundStyle(Brand.muted)
            Text(hit.recordedAt.map { displayTime($0 + hit.seekSeconds) } ?? "拍摄日期未知 · 录像内 \(videoTime(hit.seekSeconds))")
                .font(.caption).foregroundStyle(Brand.muted)
            Text("片段 \(videoTime(hit.segmentStart))–\(videoTime(hit.segmentEnd))").font(.caption)
            if !hit.limitation.isEmpty { Text(hit.limitation).font(.caption).foregroundStyle(Brand.muted) }
            NavigationLink(value: AppRoute.video(hit.recordingId, hit.seekSeconds)) {
                Label("播放原片核对", systemImage: "play.circle.fill").frame(maxWidth: .infinity)
            }.buttonStyle(.bordered).accessibilityIdentifier("videoSearch.play.\(hit.id)")
        }.padding(16).background(.white).clipShape(RoundedRectangle(cornerRadius: 20))
    }

    private func select(_ data: Data) throws {
        guard !Task.isCancelled else { return }
        guard data.count <= 20_000_000, let image = UIImage(data: data), image.size.width * image.size.height <= 20_000_000 else {
            throw APIProblem(message: "请选择 20 MB、2000 万像素以内的可读图片")
        }
        let scale = min(1, 1600 / max(image.size.width, image.size.height))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        reference = UIGraphicsImageRenderer(size: size, format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }
        error = nil
    }

    private func submit() async {
        submitting = true; error = nil; defer { submitting = false }
        let client = store.client.scoped()
        let query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let selected = camera == "all" ? [] : [camera]
        let filter = HistoryFilter(period: period, startAt: period == "custom" ? from.timeIntervalSince1970 : nil, endAt: period == "custom" ? until.timeIntervalSince1970 : nil)
        let imageData = reference?.jpegData(compressionQuality: 0.9)
        do {
            var imageRef: String?
            if let imageData { imageRef = try await client.uploadSearchImage(imageData).image_ref }
            guard client.baseURL == store.client.baseURL, !Task.isCancelled else { return }
            let value = try await client.searchVideos(VideoSearchInput(text: query.isEmpty ? nil : query, image_ref: imageRef, camera_ids: selected, time_range: filter))
            guard client.baseURL == store.client.baseURL, !Task.isCancelled else { return }
            resultOrigin = client.baseURL; result = value; searchID = value.id
        } catch { if client.baseURL == store.client.baseURL { self.error = error.localizedDescription } }
    }

    private func poll() async {
        guard let searchID, resultOrigin == store.client.baseURL else { return }
        let client = store.client.scoped()
        do {
            for _ in 0..<150 {
                let value = try await client.videoSearch(searchID)
                guard !Task.isCancelled, client.baseURL == store.client.baseURL, self.searchID == searchID else { return }
                result = value; error = nil
                if !value.isRunning { return }
                try await Task.sleep(for: .seconds(2))
            }
            error = "后台仍在核对，候选可以先播放；稍后刷新结果。"
        } catch { if !Task.isCancelled && client.baseURL == store.client.baseURL { self.error = "结果暂未同步：\(error.localizedDescription)" } }
    }
}

struct VideoSearchThumbnail: View {
    @EnvironmentObject private var store: AppStore
    let path: String
    @State private var image: UIImage?
    @State private var failed = false
    var body: some View {
        ZStack {
            Brand.background
            if let image { Image(uiImage: image).resizable().scaledToFit() }
            else if failed { Image(systemName: "photo").foregroundStyle(Brand.muted).accessibilityLabel("缩略图暂不可用，请播放原片") }
            else { ProgressView() }
        }.task(id: path + store.client.baseURL.absoluteString) {
            image = nil; failed = false; let client = store.client.scoped()
            do {
                let data = try await client.videoSearchImage(path)
                if !Task.isCancelled && client.baseURL == store.client.baseURL { image = UIImage(data: data); failed = image == nil }
            } catch { if !Task.isCancelled { failed = true } }
        }
    }
}

private struct VideoReferenceCrop: View {
    @Environment(\.dismiss) private var dismiss
    let image: UIImage
    let apply: (UIImage) -> Void
    @State private var zoom = 1.0
    @State private var offset = CGSize.zero
    @State private var anchor = CGSize.zero
    private let side: CGFloat = 280
    private var scale: CGFloat { max(side / image.size.width, side / image.size.height) * CGFloat(zoom) }
    private func clamped(_ value: CGSize) -> CGSize {
        let x = max(0, (image.size.width * scale - side) / 2), y = max(0, (image.size.height * scale - side) / 2)
        return CGSize(width: min(x, max(-x, value.width)), height: min(y, max(-y, value.height)))
    }
    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Text("拖动画面，将目标放入方框").font(.headline)
                Image(uiImage: image).resizable().frame(width: image.size.width * scale, height: image.size.height * scale)
                    .offset(offset).frame(width: side, height: side).clipped().overlay(Rectangle().stroke(.blue, lineWidth: 2))
                    .gesture(DragGesture().onChanged { value in offset = clamped(CGSize(width: anchor.width + value.translation.width, height: anchor.height + value.translation.height)) }
                        .onEnded { _ in anchor = offset })
                Slider(value: $zoom, in: 1...4).accessibilityLabel("放大目标")
                    .onChange(of: zoom) { _, _ in offset = clamped(offset); anchor = offset }
                Text("只上传裁剪后的参考图；未选择裁剪时保留整图。").font(.caption).foregroundStyle(Brand.muted)
            }.padding(24).navigationTitle("裁剪参考目标").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) { Button("使用选区") {
                        let bounds = CGRect(x: (image.size.width * scale - side) / 2 / scale - offset.width / scale,
                            y: (image.size.height * scale - side) / 2 / scale - offset.height / scale, width: side / scale, height: side / scale)
                        if let cg = image.cgImage?.cropping(to: bounds.integral) { apply(UIImage(cgImage: cg)) }
                        dismiss()
                    } }
                }
        }
    }
}
