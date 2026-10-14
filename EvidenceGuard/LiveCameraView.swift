import SwiftUI
import Combine
import UIKit
#if canImport(SampleCore) && !targetEnvironment(simulator)
import SampleCore
#endif

struct RegisteredCamera: Decodable, Identifiable { var id: String; var sn: String; var model: String; var name: String }
struct LiveSession: Decodable { var id: String; var deviceId: String; var token: String }
struct LiveAcknowledgement: Decodable { var status: String }
struct LiveCaptureCommand: Decodable { var requestId: String; var afterSequence: Int; var deadline: Double }
struct LiveFrameUpload: Encodable {
    var requestId: String; var sequence: Int; var imageBase64: String
    var width: Int; var height: Int; var sampledAt: Double; var channelId = "main"
}

@MainActor final class LiveCameraController: ObservableObject {
    @Published private(set) var renderView: UIView?
    @Published private(set) var status = "准备连接"
    @Published private(set) var ready = false
    @Published private(set) var deviceID: String?
    @Published private(set) var running = false
    @Published private(set) var latestImage: UIImage?
    private var task: Task<Void, Never>?
    private var session: LiveSession?
    private var client: APIClient?
    private var generation = UUID()
    @Published private(set) var opening = false
    @Published private(set) var closing = false
    private var releaseTask: Task<Void, Never>?
    #if canImport(SampleCore) && !targetEnvironment(simulator)
    private var media: EvidenceGuardLiveBridge?
    #endif

    func start(camera: SDKDiscoveredCamera, connection: OfficialSDKConnection, client: APIClient) async {
        guard !running, !opening, !connection.switchingWorkspace, connection.officialDemoController == nil else { return }
        connection.liveController = self
        opening = true
        defer { opening = false }
        running = true; self.client = client
        generation = UUID(); let current = generation
        status = "正在登记官方设备…"
        do {
            // A quick stop/reconnect must not reuse a player that is still
            // releasing its native transport or owns the previous cloud lease.
            await releaseTask?.value
            try Task.checkCancellation()
            guard current == generation else { return }
            let devices = try await connection.importDevices(client: client)
            try Task.checkCancellation()
            guard current == generation else { return }
            guard let registered = devices.first(where: { $0.sn == camera.sn }) else { throw APIProblem(message: "设备未完成云端登记，请重新查询设备") }
            deviceID = registered.id
            #if canImport(SampleCore) && !targetEnvironment(simulator)
            guard let player = connection.makeLive(camera: camera) else { throw APIProblem(message: "设备不在当前官方会话内，请重新查询设备") }
            media = player
            renderView = player.renderView()
            let opened = try await Task { try await client.startMedia(registered.id) }.value
            guard current == generation, !Task.isCancelled else {
                player.stop()
                await releaseSession(opened, client: client)
                return
            }
            session = opened
            player.start { [weak self] state in
                Task { @MainActor in
                    guard let self, self.generation == current else { return }
                    if state == "failed" || state == "stopped" { self.stop(message: "官方直播已中断，请重新连接") }
                    else if state == "playing" { self.status = "等待有效新帧…" }
                }
            }
            task = Task { [weak self] in await self?.relay(player: player, session: opened, client: client, generation: current) }
            #else
            throw APIProblem(message: connection.buildStatus)
            #endif
        } catch {
            if current == generation { stop(message: error is CancellationError ? "已停止" : error.localizedDescription) }
        }
    }

    #if canImport(SampleCore) && !targetEnvironment(simulator)
    private func relay(player: EvidenceGuardLiveBridge, session: LiveSession, client: APIClient, generation current: UUID) async {
        var sequence = 0
        var activity = 0
        var lastSample: Date?
        let startedAt = Date()
        do {
            while !Task.isCancelled && generation == current {
                let nextActivity = Int(player.activitySequence())
                if nextActivity > activity, let image = player.capture() {
                    activity = nextActivity; sequence += 1; lastSample = Date(); latestImage = image
                }
                let age = lastSample.map { Int(Date().timeIntervalSince($0) * 1000) }
                ready = age.map { $0 < 3000 } ?? false
                status = ready ? "实时画面可用 · Agent 可请求新取样" : "等待有效视频帧…"
                try await client.liveHeartbeat(session, state: ready ? "streaming" : "connecting", sequence: sequence, age: age)
                let commands = try await client.liveCommands(session)
                for command in commands {
                    // Require a further SDK media activity callback after the
                    // challenge, then read the player. No sensor PTS is exposed.
                    let challengedAt = player.activitySequence()
                    while player.activitySequence() <= challengedAt && generation == current && command.deadline > Date().timeIntervalSince1970 {
                        try await Task.sleep(for: .milliseconds(100))
                    }
                    try Task.checkCancellation()
                    guard generation == current, command.deadline > Date().timeIntervalSince1970,
                          let image = player.capture(), let pixels = image.cgImage,
                          let bytes = image.jpegData(compressionQuality: 0.8), bytes.count <= 5_000_000 else { continue }
                    // Read the SDK player after receiving the server challenge.
                    sequence = max(sequence, command.afterSequence) + 1
                    let sampledAt = Date().timeIntervalSince1970
                    // Waiting for the next media callback may exceed the last
                    // heartbeat's freshness window. Advertise this new sample.
                    try await client.liveHeartbeat(session, state: "streaming", sequence: sequence, age: 0)
                    do {
                        try await client.uploadLiveFrame(session, body: LiveFrameUpload(requestId: command.requestId, sequence: sequence,
                            imageBase64: bytes.base64EncodedString(), width: pixels.width, height: pixels.height, sampledAt: sampledAt))
                    } catch let problem as APIProblem where problem.statusCode == 409 {
                        // The requester may have cancelled while we sampled.
                        // The next heartbeat still detects a stale session.
                    }
                    activity = Int(player.activitySequence()); latestImage = image; lastSample = Date()
                }
                if !ready && Date().timeIntervalSince(startedAt) > 45 { throw APIProblem(message: "没有取得有效新帧，请检查设备与网络后重新开流") }
                try await Task.sleep(for: .milliseconds(700))
            }
        } catch {
            if generation == current { stop(message: error is CancellationError ? "已停止" : error.localizedDescription) }
        }
    }
    #endif

    func stop(message: String = "已停止直播") {
        generation = UUID(); task?.cancel(); task = nil
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        media?.stop(); media = nil
        #endif
        let stoppedSession = session, stoppedClient = client
        let previous = releaseTask
        closing = true
        releaseTask = Task {
            await previous?.value
            if let stoppedSession, let stoppedClient {
                await self.releaseSession(stoppedSession, client: stoppedClient)
            }
            // The official iOS renderer defers release by 500 ms.
            try? await Task.sleep(for: .milliseconds(650))
            self.closing = false
        }
        session = nil; renderView = nil; latestImage = nil; ready = false; running = false; status = message
    }

    private func releaseSession(_ session: LiveSession, client: APIClient) async {
        // Cleanup must finish even when the view's .task has been cancelled.
        await Task {
            do { try await client.stopMedia(session) }
            catch let problem as APIProblem where problem.statusCode == 409 {
                // An already expired/stopped lease cannot block a new session.
            } catch {
                status = "本地画面已停止，等待云端采集会话到期…"
                try? await Task.sleep(for: .seconds(13))
            }
        }.value
    }

    func stopForWorkspaceSwitch() async {
        stop(message: "正在切换到官方 SDK")
        // Also cover a switch while startMedia is still in flight. Its late
        // response is explicitly stopped before the official player can mount.
        while opening { try? await Task.sleep(for: .milliseconds(50)) }
        await releaseTask?.value
    }
}

private struct SDKRenderView: UIViewRepresentable {
    let rendered: UIView
    func makeUIView(context: Context) -> UIView {
        let host = UIView(); host.backgroundColor = .black
        rendered.translatesAutoresizingMaskIntoConstraints = false
        host.addSubview(rendered)
        NSLayoutConstraint.activate([rendered.leadingAnchor.constraint(equalTo: host.leadingAnchor), rendered.trailingAnchor.constraint(equalTo: host.trailingAnchor), rendered.topAnchor.constraint(equalTo: host.topAnchor), rendered.bottomAnchor.constraint(equalTo: host.bottomAnchor)])
        return host
    }
    func updateUIView(_ uiView: UIView, context: Context) {}
    static func dismantleUIView(_ uiView: UIView, coordinator: ()) { uiView.subviews.forEach { $0.removeFromSuperview() } }
}

struct OfficialLiveCameraView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var controller = LiveCameraController()
    let camera: SDKDiscoveredCamera
    @State private var question = "现在画面里有什么？"
    @State private var run: AgentRun?
    @State private var asking = false
    @State private var feedback: String?
    @State private var conversationID: String?
    @State private var questionTask: Task<Void, Never>?
    @State private var questionGeneration = UUID()
    @State private var activeRunID: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(camera.name).font(.title2.bold())
                Text("\(camera.model) · \(camera.sn)").font(.caption).foregroundStyle(Brand.muted)
                Group {
                    if let view = controller.renderView { SDKRenderView(rendered: view) }
                    else { ZStack { Color.black; Text("官方实时视频").foregroundStyle(.white) } }
                }.frame(height: 250).clipShape(RoundedRectangle(cornerRadius: 16))
                Label(controller.status, systemImage: controller.ready ? "dot.radiowaves.left.and.right" : "video.slash").font(.subheadline)
                HStack {
                    Button(controller.running ? "停止直播" : (controller.closing || controller.opening ? "正在释放会话…" : "重新连接")) {
                        if controller.running { controller.stop() }
                        else { Task { await controller.start(camera: camera, connection: store.officialSDK, client: store.client) } }
                    }.buttonStyle(.bordered).disabled(!controller.running && (controller.closing || controller.opening))
                    Button("获取一张新画面") {
                        guard let id = controller.deviceID else { return }
                        Task { do { let value = try await store.client.captureLive(id); feedback = value.reason } catch { feedback = error.localizedDescription } }
                    }.buttonStyle(.borderedProminent).disabled(!controller.ready)
                }
                if let feedback { Text(feedback).font(.caption).foregroundStyle(Brand.muted) }
                if let image = controller.latestImage { Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 160).clipShape(RoundedRectangle(cornerRadius: 12)) }
                Text("问问 Agent").font(.headline)
                TextField("你想了解画面中的什么？", text: $question, axis: .vertical).textFieldStyle(.roundedBorder)
                Button(asking ? "正在观察与回答…" : "获取新画面并提问") { ask() }.buttonStyle(PrimaryAction()).disabled(asking || !controller.ready || question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if let run { Text(run.text ?? run.error ?? "等待 Agent 请求新画面…").textSelection(.enabled) }
                Text("本页在前台时提供画面。设备拍摄时间未由 SDK 确认，记录的是客户端取样时间；离开本页或锁屏会停止，不代表持续守护。").font(.caption).foregroundStyle(Brand.muted)
            }.padding(16)
        }.pageStyle("实时查看与 Agent")
            .task { await controller.start(camera: camera, connection: store.officialSDK, client: store.client); await store.refresh() }
            .onChange(of: scenePhase) { _, phase in if phase != .active { controller.stop(message: "App 已离开前台，直播已停止"); cancelQuestion() } }
            .onChange(of: controller.running) { _, running in if !running { cancelQuestion() } }
            .onDisappear { controller.stop(); cancelQuestion() }
    }
    private func cancelQuestion() {
        questionGeneration = UUID()
        questionTask?.cancel(); questionTask = nil
        let client = store.client
        if let id = activeRunID { Task { _ = try? await client.cancel(id) } }
        activeRunID = nil; asking = false
    }
    private func ask() {
        guard let device = controller.deviceID else { return }
        asking = true; feedback = nil
        let text = question
        let current = UUID(); questionGeneration = current
        let client = store.client
        questionTask = Task {
            defer { if questionGeneration == current { asking = false; activeRunID = nil } }
            do {
                if conversationID == nil { conversationID = try await client.newConversation(requestID: UUID().uuidString).id }
                try Task.checkCancellation()
                guard questionGeneration == current else { return }
                guard let conversationID else { return }
                // Keep the start receipt observable even if this view closes
                // during the request, so the late server run can be cancelled.
                var value = try await Task {
                    try await client.start(message: text, conversation: conversationID, skill: nil, camera: device, requestID: UUID().uuidString)
                }.value
                guard !Task.isCancelled, questionGeneration == current else {
                    let id = value.id
                    Task { _ = try? await client.cancel(id) }
                    return
                }
                activeRunID = value.id
                run = value
                while value.isRunning {
                    try await Task.sleep(for: .seconds(1))
                    value = try await client.agentRun(value.id)
                    try Task.checkCancellation()
                    guard questionGeneration == current else { return }
                    run = value
                }
            } catch { if questionGeneration == current, !(error is CancellationError) { feedback = error.localizedDescription } }
        }
    }
}

struct RegisteredLiveCameraView: View {
    @EnvironmentObject private var store: AppStore
    let deviceID: String
    @State private var camera: SDKDiscoveredCamera?
    @State private var message = "正在核对设备…"
    var body: some View {
        Group {
            if let camera { OfficialLiveCameraView(camera: camera) }
            else { List { Text(message); NavigationLink("连接官方账号并查询设备", value: AppRoute.officialSDK) }.pageStyle("实时查看") }
        }.task {
            do {
                let records = try await store.client.registeredCameras()
                guard let record = records.first(where: { $0.id == deviceID }) else { message = "设备尚未登记"; return }
                camera = store.officialSDK.devices.first(where: { $0.sn == record.sn })
                if camera == nil { message = "此手机尚未建立官方设备会话。请先连接官方账号并查询设备，再返回这里。" }
            } catch { message = error.localizedDescription }
        }
    }
}
