import SwiftUI
import UIKit

struct VisualScenePlan: Codable, Equatable {
    var title: String; var target: String; var selection: String; var trigger: String
    var confirmationSeconds: Int; var completion: String
}
struct VisualSceneFrame: Codable, Equatable {
    var frameId: String; var imageUrl: String; var width: Int; var height: Int
    var capturedAt: Double?; var sampledAt: Double?
}
struct VisualSceneObservation: Codable, Equatable {
    var state: String; var reason: String; var lastAt: Double?
}
struct VisualSceneResult: Codable, Equatable {
    var state: String; var label: String; var reason: String
}
struct EndpointVisionConfiguration: Codable, Equatable { var ready: Bool }
struct EndpointAnalysis: Codable, Equatable {
    struct Analysis: Codable, Equatable { var summary: String }
    struct Frame: Codable, Equatable { var captured_at: Double?; var sampled_at: Double? }
    struct Sources: Codable, Equatable { var a: Frame; var b: Frame }
    var status: String; var reason: String?; var limitation: String
    var analysis: Analysis?; var cached: Bool?; var model: String?
    var sources: Sources?
}
struct VisualScene: Codable, Identifiable, Equatable {
    var id: String; var cameraId: String; var prompt: String; var revision: Int
    var status: String; var stage: String; var plan: VisualScenePlan?
    var question: String; var unsupportedReason: String; var reason: String
    var frame: VisualSceneFrame?; var box: ROI?; var summary: String; var limitation: String
    var result: VisualSceneResult?
    var endpointVision: EndpointVisionConfiguration?
    var endpointAnalysis: EndpointAnalysis?
    var resultState: String { result?.state ?? (status == "draft" ? "pending" : "unknown") }
    var resultLabel: String { result?.label ?? (status == "draft" ? "待确认" : "无法确认") }
    var canActivate: Bool; var observation: VisualSceneObservation; var evidenceIds: [String]
    var label: String { resultLabel }
}

/// Camera-page drafts and chat drafts share the same persisted record.
struct CameraGuardDestination: View {
    @EnvironmentObject private var store: AppStore
    let id: String
    @State private var scene: VisualScene?
    @State private var error: String?
    @State private var retry = 0
    var body: some View {
        Group {
            if let scene { VisualSceneEditor(initialScene: scene) }
            else if let error {
                VStack(spacing: 18) {
                    Text(error).foregroundStyle(.secondary)
                    Button("重新加载守护") { retry += 1 }.buttonStyle(.borderedProminent)
                }.padding()
            } else { ProgressView("正在读取守护…") }
        }.task(id: "\(store.client.baseURL)-\(id)-\(retry)") {
            let source = store.client
            scene = nil; error = nil
            do {
                let value = try await source.visualScene(id)
                guard !Task.isCancelled, source.baseURL == store.client.baseURL else { return }
                scene = value
            } catch is CancellationError { }
            catch { self.error = "守护暂未加载成功，请检查连接后重试。" }
        }
    }
}

extension AppStore {
    func openCameraGuard(_ id: String) {
        selectedTab = .cameraSkills
        tabPaths[AppTab.cameraSkills.rawValue] = [.cameraGuard(id)]
    }
    func beginCameraGuard(cameraID: String?) {
        selectedTab = .cameraSkills
        tabPaths[AppTab.cameraSkills.rawValue] = [.newCameraGuard(cameraID)]
    }
}

struct VisualScenesSection: View {
    @EnvironmentObject private var store: AppStore
    @State private var scenes: [VisualScene] = []
    @State private var error: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("我的守护").font(.headline)
                Spacer()
            }
            NavigationLink { VisualSceneEditor() } label: {
                Label("添加守护", systemImage: "plus.circle.fill").font(.headline).frame(maxWidth: .infinity, minHeight: 48)
            }.buttonStyle(.borderedProminent).accessibilityIdentifier("scene.create")
            if scenes.isEmpty { Text("说一句需求，框出关注的对象或区域，再确认开启。").font(.subheadline).foregroundStyle(Brand.muted) }
            ForEach(scenes) { scene in
                NavigationLink { VisualSceneEditor(initialScene: scene) } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack { Text(scene.plan?.title ?? "待完善的场景").font(.headline); Spacer(); Text(scene.label).font(.caption).foregroundStyle(Brand.blue) }
                        Text(scene.status == "active" ? scene.observation.reason : scene.summary)
                            .font(.subheadline).foregroundStyle(Brand.muted).lineLimit(3)
                    }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                        .background(.white.opacity(0.85)).clipShape(RoundedRectangle(cornerRadius: 18))
                }.buttonStyle(.plain).accessibilityIdentifier("scene.item." + scene.id)
            }
            if let error { Text(error).font(.caption).foregroundStyle(.orange) }
        }.task(id: store.client.baseURL) {
            scenes = []; error = nil
            let source = store.client
            while !Task.isCancelled {
                do {
                    let values = try await source.visualScenes()
                    guard source.baseURL == store.client.baseURL else { return }
                    scenes = values; error = nil
                    try await Task.sleep(for: .seconds(5))
                } catch is CancellationError { return }
                catch let problem as APIProblem where problem.statusCode == 404 {
                    error = "场景服务尚未更新，已有任务仍可查看。"; return
                } catch { self.error = "场景暂未同步，请检查连接后重新打开。"; return }
            }
        }
    }
}

struct VisualSceneEditor: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var scene: VisualScene?
    @State private var message = ""
    @State private var cameraID = ""
    @State private var box: ROI?
    @State private var frozenImage: UIImage?
    @State private var busy = false
    @State private var error: String?
    @State private var origin: URL?
    @State private var requestID = UUID().uuidString
    @State private var lastSubmission = ""
    private let initialCameraID: String?
    init(initialScene: VisualScene? = nil, initialCameraID: String? = nil) {
        _scene = State(initialValue: initialScene); self.initialCameraID = initialCameraID
    }
    private var step: Int {
        guard let scene else { return 0 }
        if scene.status != "draft" || scene.stage == "review" { return 2 }
        return scene.stage == "select" ? 1 : 0
    }
    private var selectedCamera: String { scene?.cameraId ?? cameraID }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack {
                    ForEach(Array(["说需求", "框选画面", "确认开启"].enumerated()), id: \.offset) { index, title in
                        Text("\(index + 1) · " + title).font(.subheadline.weight(.medium))
                            .frame(maxWidth: .infinity).padding(.vertical, 10)
                            .background(index == step ? Brand.paleBlue : Color.clear)
                            .clipShape(Capsule()).foregroundStyle(index == step ? Brand.blue : Brand.muted)
                    }
                }
                if step == 0 { describe }
                else if step == 1 { select }
                else { review }
                if let error { Text(error).foregroundStyle(.orange).font(.subheadline).accessibilityIdentifier("scene.error") }
                if let scene, scene.status == "draft" {
                    Text("草稿会自动保存；只有点“确认并开启”才开始观察。").font(.caption).foregroundStyle(Brand.muted)
                }
            }.padding(20)
        }.navigationTitle(scene?.plan?.title ?? "添加守护").navigationBarTitleDisplayMode(.inline)
            .scrollDismissesKeyboard(.interactively)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("完成") { dismiss() }.disabled(busy) } }
            .task { await loadExisting() }
            .task(id: pollKey) { await pollScene() }
            .onChange(of: store.client.baseURL) { _, _ in dismiss() }
    }
    private var pollKey: String { (scene?.id ?? "") + ":" + (scene?.stage ?? "") + ":" + (scene?.status ?? "") }
    private func loadExisting() async {
        origin = store.client.baseURL
        cameraID = scene?.cameraId ?? initialCameraID ?? (store.camera(store.selectedCameraID)?.id ?? store.data.cameras.first?.id ?? "")
        if let current = scene {
            await operation {
                scene = try await store.client.visualScene(current.id)
                box = scene?.box
                if let frame = scene?.frame { try await loadImage(frame) }
            }
        }
    }
    private func pollScene() async {
        guard let current = scene, current.stage == "generating" || current.status == "active" else { return }
        let source = store.client
        var attempts = 0
        while !Task.isCancelled {
            do {
                try await Task.sleep(for: .seconds(2))
                var updated = try await source.visualScene(current.id)
                guard source.baseURL == store.client.baseURL else { return }
                guard updated.revision >= (scene?.revision ?? 0) else { continue }
                if updated.revision == scene?.revision { updated.endpointAnalysis = scene?.endpointAnalysis }
                scene = updated
                if updated.stage != "generating" && updated.status != "active" { return }
                attempts += 1
                if updated.stage == "generating" && attempts >= 65 { break }
            } catch is CancellationError { return }
            catch { self.error = "同步暂时中断，需求已保存；重新打开这份草稿可继续。"; return }
        }
        error = "需求整理尚未完成，稍后重新打开这份草稿查看。"
    }
    @ViewBuilder private var describe: some View {
        Text("想让摄像头帮你关注什么？").font(.title2.weight(.semibold))
        Text("例如：狗进入沙发区域时提醒我。").foregroundStyle(Brand.muted)
        if scene == nil {
            Picker("摄像头", selection: $cameraID) {
                Text("选择摄像头").tag("")
                ForEach(store.data.cameras) { camera in Text(camera.name).tag(camera.id) }
            }.accessibilityIdentifier("scene.camera")
            if store.data.cameras.isEmpty {
                Text("请先连接摄像头，再为它添加守护。").foregroundStyle(.orange)
                NavigationLink("连接摄像头", value: AppRoute.officialSDK)
            }
        }
        if let scene {
            Text(scene.prompt).font(.subheadline).foregroundStyle(Brand.muted)
            if !scene.question.isEmpty { Text(scene.question).font(.headline).accessibilityIdentifier("scene.question") }
            if !scene.unsupportedReason.isEmpty { Text(scene.unsupportedReason).foregroundStyle(.orange) }
            if scene.stage != "generating", scene.question.isEmpty, scene.unsupportedReason.isEmpty { Text(scene.reason).font(.subheadline) }
        }
        TextField(scene == nil ? "用一句话描述需求…" : "补充或修改这份需求…", text: $message, axis: .vertical)
            .lineLimit(3...6).padding(14).background(.white).clipShape(RoundedRectangle(cornerRadius: 16))
            .accessibilityIdentifier("scene.prompt")
            .disabled(busy || scene?.stage == "generating")
        Button { Task { await generate() } } label: {
            HStack { if busy || scene?.stage == "generating" { ProgressView() }; Text(scene?.stage == "generating" ? "正在理解你的需求…" : "生成守护") }.frame(maxWidth: .infinity, minHeight: 44)
        }.buttonStyle(.borderedProminent)
            .disabled(busy || scene?.stage == "generating" || selectedCamera.isEmpty || message.trimmingCharacters(in: .whitespacesAndNewlines).count < 2)
            .accessibilityIdentifier("scene.generate")
    }
    @ViewBuilder private var select: some View {
        if let scene {
            Text(scene.summary).font(.headline)
            Text(scene.plan?.selection == "object" ? "框出你想看住的具体物体；这个位置将作为关注区域。" : "框出关注区域；我会判断指定对象是否进入或离开这里。")
                .foregroundStyle(Brand.muted)
            if let frozenImage {
                SceneSelectionCanvas(image: frozenImage, box: $box).id(scene.frame?.frameId)
                if let at = scene.frame?.capturedAt ?? scene.frame?.sampledAt {
                    Text("框选画面取样于 " + displayTime(at)).font(.caption).foregroundStyle(Brand.muted)
                }
                Button("重画选框") { box = nil }.disabled(busy)
            }
            Button { Task { await capture() } } label: {
                HStack { if busy { ProgressView() }; Label(frozenImage == nil ? "获取摄像头新画面" : "刷新画面，重新框选", systemImage: "camera") }
            }.disabled(busy).accessibilityIdentifier("scene.capture")
            Text(frozenImage == nil ? "获取新画面后，框选目标。" : "拖动框选，也可以依次点选左上角和右下角。选框会绑定这张画面。")
                .font(.caption).foregroundStyle(Brand.muted)
            Button("完成框选，查看条件") { Task { await saveSelection() } }
                .buttonStyle(.borderedProminent).disabled(busy || frozenImage == nil || box == nil)
                .accessibilityIdentifier("scene.selection.done")
            modification
        }
    }
    @ViewBuilder private var review: some View {
        if let scene {
            Text(scene.status == "draft" ? "确认这件事" : scene.label).font(.title2.weight(.semibold))
            Text(scene.summary).font(.headline)
            Text(store.camera(scene.cameraId)?.name ?? "所选摄像头").foregroundStyle(Brand.muted)
            if let frozenImage { SceneSelectionCanvas(image: frozenImage, box: .constant(scene.box)).allowsHitTesting(false) }
            Label("看不清、遮挡或断流时保留判断。", systemImage: "eye.slash")
            Text(scene.limitation).font(.caption).foregroundStyle(Brand.muted)
            if scene.status == "draft" {
                Button { Task { await activate() } } label: {
                    HStack { if busy { ProgressView() }; Text("确认并开启") }.frame(maxWidth: .infinity)
                }.buttonStyle(.borderedProminent).disabled(busy || !scene.canActivate || frozenImage == nil)
                    .accessibilityIdentifier("scene.activate")
                if !scene.canActivate { Text("执行条件尚未就绪，草稿已保留。").foregroundStyle(.orange) }
                Button("重新框选") { self.scene?.stage = "select" }.disabled(busy)
                modification
            } else {
                Text(scene.observation.reason).accessibilityIdentifier("scene.observation")
                if scene.endpointVision?.ready == true {
                    Button("对照参考图与最近采样") { Task { await operation {
                        let source = store.client
                        let result = try await source.analyzeScene(scene)
                        guard source.baseURL == store.client.baseURL,
                              self.scene?.revision == scene.revision else { return }
                        self.scene?.endpointAnalysis = result
                    } } }.disabled(busy).accessibilityIdentifier("scene.analyzeEndpoints")
                    Text("只分析已保存图片；不会补拍、告警或转动摄像头。").font(.caption).foregroundStyle(Brand.muted)
                }
                if let report = scene.endpointAnalysis {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("首尾图分析 · 仅供核对").font(.headline)
                        Text(report.analysis?.summary ?? report.reason ?? "本次无法确认")
                        if let at = report.sources?.b.sampled_at ?? report.sources?.b.captured_at {
                            Text("对照图取样时间：" + Date(timeIntervalSince1970: at).formatted(date: .abbreviated, time: .standard)).font(.caption)
                        }
                        if report.cached == true { Text("复用相同证据的分析，未获取新画面").font(.caption) }
                        Text(report.limitation).font(.caption).foregroundStyle(Brand.muted)
                    }.padding().background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius: 16))
                }
                if scene.status == "active" {
                    Button("暂停守护") { Task { await operation { self.scene = try await store.client.sceneAction(scene, action: "pause"); frozenImage = nil; box = nil } } }
                        .disabled(busy).accessibilityIdentifier("scene.pause")
                }
                ForEach(scene.evidenceIds.reversed(), id: \.self) { id in
                    NavigationLink("查看提醒画面", value: AppRoute.evidence(id))
                }
                Button("回到助手") { store.openAI(); dismiss() }
            }
        }
    }
    private var modification: some View {
        DisclosureGroup("用一句话修改条件") {
            TextField("例如：只提醒我一次", text: $message, axis: .vertical).lineLimit(2...4)
                .accessibilityIdentifier("scene.revise")
            Button("更新这份草稿") { Task { await generate() } }.disabled(busy || message.trimmingCharacters(in: .whitespacesAndNewlines).count < 2)
        }
    }
    private func operation(_ body: () async throws -> Void) async {
        guard !busy, origin == store.client.baseURL else { return }
        busy = true; error = nil; defer { busy = false }
        do { try await body() }
        catch is CancellationError { }
        catch { self.error = error.localizedDescription }
    }
    private func generate() async {
        await operation {
            let input = message.trimmingCharacters(in: .whitespacesAndNewlines)
            if lastSubmission != input { requestID = UUID().uuidString; lastSubmission = input }
            if let current = scene { scene = try await store.client.interpretScene(current, message: input, requestID: requestID) }
            else { scene = try await store.client.createScene(cameraID: cameraID, message: input, requestID: requestID) }
            message = ""; frozenImage = nil; box = nil
        }
    }
    private func loadImage(_ frame: VisualSceneFrame) async throws {
        let bytes = try await store.client.sceneImage(frame.imageUrl)
        guard let image = UIImage(data: bytes) else { throw APIProblem(message: "画面加载失败，请重新取图。") }
        frozenImage = image
    }
    private func capture() async {
        await operation {
            guard let current = scene else { return }
            try await store.officialSDK.prepareAssistantCamera(current.cameraId, client: store.client)
            scene = try await store.client.sceneAction(current, action: "frame")
            frozenImage = nil; box = nil
            if let frame = scene?.frame { try await loadImage(frame) }
        }
    }
    private func saveSelection() async {
        await operation {
            guard let current = scene, let box, let frame = current.frame else { return }
            scene = try await store.client.selectScene(current, frameID: frame.frameId, box: box)
        }
    }
    private func activate() async {
        await operation {
            guard let current = scene else { return }
            scene = try await store.client.sceneAction(current, action: "activate")
            store.toast = "场景已开启，正在等待新的有效观察"
        }
    }
}

struct SceneSelectionCanvas: View {
    let image: UIImage
    @Binding var box: ROI?
    @State private var anchor: CGPoint?
    var body: some View {
        Image(uiImage: image).resizable().aspectRatio(contentMode: .fit)
            .overlay { GeometryReader { geometry in
                ZStack(alignment: .topLeading) {
                    Color.clear.contentShape(Rectangle())
                    if let box {
                        Rectangle().fill(Brand.blue.opacity(0.18)).overlay(Rectangle().stroke(.white, lineWidth: 2))
                            .frame(width: geometry.size.width * box.width, height: geometry.size.height * box.height)
                            .offset(x: geometry.size.width * box.x, y: geometry.size.height * box.y).allowsHitTesting(false)
                    }
                    if let anchor {
                        Circle().fill(.white).frame(width: 12, height: 12).position(anchor).allowsHitTesting(false)
                    }
                }.contentShape(Rectangle()).highPriorityGesture(DragGesture(minimumDistance: 6).onChanged { value in
                    anchor = nil
                    box = Self.selection(from: value.startLocation, to: value.location, in: geometry.size)
                }).simultaneousGesture(SpatialTapGesture().onEnded { value in
                    if let start = anchor {
                        box = Self.selection(from: start, to: value.location, in: geometry.size); anchor = nil
                    } else { box = nil; anchor = value.location }
                })
            } }.clipShape(RoundedRectangle(cornerRadius: 14))
            .accessibilityLabel("在摄像头画面上拖动，框选关注区域")
            .accessibilityIdentifier("scene.canvas")
    }
    static func selection(from start: CGPoint, to end: CGPoint, in size: CGSize) -> ROI? {
        guard size.width > 0, size.height > 0 else { return nil }
        let x1 = min(1, max(0, start.x / size.width)), x2 = min(1, max(0, end.x / size.width))
        let y1 = min(1, max(0, start.y / size.height)), y2 = min(1, max(0, end.y / size.height))
        guard abs(x2-x1) >= 0.02, abs(y2-y1) >= 0.02 else { return nil }
        return ROI(x: min(x1, x2), y: min(y1, y2), width: abs(x2-x1), height: abs(y2-y1))
    }
}
