import SwiftUI

/// Keep the selected native decoder attached behind the opaque app surface.
/// Switching tabs must not detach it; only one camera can play at a time.
struct CameraRenderHost: View {
    @ObservedObject var connection: OfficialSDKConnection
    var body: some View {
        ZStack {
            ForEach(connection.liveControllers.keys.sorted(), id: \.self) { id in
                if let controller = connection.liveControllers[id] { CameraDecoderHost(controller: controller) }
            }
        }.frame(width: 320, height: 180)
    }
}
private struct CameraDecoderHost: View {
    @ObservedObject var controller: LiveCameraController
    var body: some View {
        if let view = controller.renderView { SDKRenderView(rendered: view).frame(width: 320, height: 180) }
    }
}

struct CameraOverviewView: View {
    @EnvironmentObject private var store: AppStore
    @ObservedObject var connection: OfficialSDKConnection
    @State private var scenes: [VisualScene] = []
    @State private var error: String?
    private var cameras: [SDKDiscoveredCamera] { connection.devices.filter(\.isCompetitionCamera) }
    private var displayedCameras: [SDKDiscoveredCamera] {
        let id = connection.activeCameraID ?? store.selectedCameraID
        return cameras.first(where: { IOSToolExecutor.deviceID($0.sn) == id }).map { [$0] } ?? Array(cameras.prefix(1))
    }
    private var active: [VisualScene] { scenes.filter { $0.status == "active" } }
    private var attention: [VisualScene] { scenes.filter { ["issue", "unknown", "checking"].contains($0.resultState) } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                ConnectionBanner()
                VStack(alignment: .leading, spacing: 12) {
                    Text("我关心的事").font(.title2.bold())
                    Text(summary).font(.headline).accessibilityIdentifier("cameraSkills.summary")
                    HStack {
                        metric("摄像头", value: cameras.count, icon: "video")
                        metric("运行中守护", value: active.count, icon: "shield.checkered")
                        metric("需关注", value: attention.count, icon: "exclamationmark.circle")
                    }
                    Text("结果来自最近一次有效检查；画面缺失、过期或看不清时显示无法确认。").font(.caption).foregroundStyle(Brand.muted)
                }.padding(18).background(.white.opacity(0.9)).clipShape(RoundedRectangle(cornerRadius: 22))
                HStack {
                    Text("助手连接的摄像头").font(.headline); Spacer()
                    Menu("切换摄像头") {
                        ForEach(cameras) { camera in
                            Button(camera.model + " · " + camera.name) {
                                store.selectedCameraID = IOSToolExecutor.deviceID(camera.sn)
                                Task { await connection.selectCamera(camera, client: store.client) }
                            }
                        }
                        NavigationLink("管理设备", value: AppRoute.officialSDK)
                    }.font(.subheadline)
                }
                if cameras.isEmpty {
                    Text(connection.checking ? "正在恢复摄像头连接…" : connection.message).foregroundStyle(Brand.muted)
                    NavigationLink("连接摄像头", value: AppRoute.officialSDK).buttonStyle(.borderedProminent)
                }
                ForEach(displayedCameras) { camera in
                    CameraPurposeCard(connection: connection, camera: camera,
                                      scenes: scenes.filter { $0.cameraId == IOSToolExecutor.deviceID(camera.sn) })
                }
                VStack(alignment: .leading, spacing: 10) {
                    Label("摄像头自动保持连接", systemImage: "arrow.triangle.2.circlepath").font(.subheadline.weight(.medium))
                    Text("App 在前台时自动连接，断线自动重连。切换页面继续保持，需要另一台时自动切换；锁屏后暂停取样，返回后恢复。").font(.caption).foregroundStyle(Brand.muted)
                }
                HStack {
                    Text("我的守护").font(.title2.bold()); Spacer()
                }
                NavigationLink { VisualSceneEditor(initialCameraID: connection.activeCameraID ?? store.selectedCameraID) } label: {
                    Label("添加守护", systemImage: "plus.circle.fill").font(.headline)
                        .frame(maxWidth: .infinity, minHeight: 48)
                }.buttonStyle(.borderedProminent).accessibilityIdentifier("scene.create")
                if scenes.isEmpty { Text("告诉我想看住什么，再框选画面、确认条件。开启后，检查结果会显示在这里。").foregroundStyle(Brand.muted) }
                ForEach(scenes.sorted { priority($0) < priority($1) }) { scene in
                    NavigationLink { VisualSceneEditor(initialScene: scene) } label: { SceneResultCard(scene: scene) }
                        .buttonStyle(.plain).accessibilityIdentifier("scene.item." + scene.id)
                }
                if let error { Text(error).font(.caption).foregroundStyle(.orange) }
                VStack(alignment: .leading, spacing: 10) {
                    Text("主动触发").font(.headline)
                    HStack(spacing: 6) {
                        trigger("定时", "clock"); trigger("事件", "eye"); trigger("用户指令", "text.bubble"); trigger("特殊", "bell")
                    }
                    Text("定时报告与检查 · 关注事件 · 你交代的指令 · 门铃等特殊信号。每项守护按你确认的条件运行。").font(.caption).foregroundStyle(Brand.muted)
                }
                NavigationLink(value: AppRoute.legacyTasks) { Label("全部关注事项与历史任务", systemImage: "checklist") }
                DisclosureGroup("事件记录与提醒设置") {
                    VStack(alignment: .leading, spacing: 14) {
                        Toggle("前台同步摄像头事件", isOn: Binding(get: { connection.syncEnabled(for: store.client) }, set: { connection.setEventSync($0, client: store.client) }))
                        Text("普通事件仅在符合关注条件时提醒；关闭同步不影响前台实时取图。").font(.caption).foregroundStyle(Brand.muted)
                        NavigationLink("提醒设置", value: AppRoute.notificationSettings)
                        ForEach(store.data.cameraEvents?.events ?? []) { event in
                            NavigationLink(value: AppRoute.evidence(event.id)) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(event.label)
                                    Text(event.deviceName + " · " + displayTime(Double(event.startMs) / 1000)).font(.caption).foregroundStyle(Brand.muted)
                                }
                            }
                        }
                    }.padding(.top, 12)
                }
            }.padding(20)
        }.agentPageStyle("摄像头守护", largeTitle: true)
            .task(id: store.client.baseURL) {
                scenes = []; error = nil
                let source = store.client
                while !Task.isCancelled {
                    do {
                        let values = try await source.visualScenes()
                        guard source.baseURL == store.client.baseURL else { return }
                        scenes = values; error = nil
                    } catch is CancellationError { return }
                    catch { self.error = "检查结果暂未同步，不能据此判断正常。" }
                    do { try await Task.sleep(for: .seconds(5)) } catch { return }
                }
            }
            .refreshable { await store.refresh() }
    }
    private var summary: String {
        if error != nil { return "检查结果尚未同步" }
        if !attention.isEmpty { return "\(attention.count) 项需要关注" }
        if scenes.contains(where: { $0.resultState == "confirmed" }) { return "最近检查符合已确认条件" }
        return active.isEmpty ? "先确认你希望守护的事" : "正在等待有效检查"
    }
    private func priority(_ scene: VisualScene) -> Int {
        ["issue": 0, "unknown": 1, "checking": 2, "confirmed": 3, "pending": 4, "completed": 5][scene.resultState] ?? 6
    }
    private func metric(_ title: String, value: Int, icon: String) -> some View {
        VStack(spacing: 6) { Label("\(value)", systemImage: icon).font(.title3.bold()).foregroundStyle(Brand.blue); Text(title).font(.caption).foregroundStyle(Brand.muted) }.frame(maxWidth: .infinity)
    }
    private func trigger(_ title: String, _ icon: String) -> some View {
        Label(title, systemImage: icon).font(.caption).padding(.vertical, 8).frame(maxWidth: .infinity).background(Brand.paleBlue).clipShape(Capsule())
    }
}

private struct CameraPurposeCard: View {
    @EnvironmentObject private var store: AppStore
    @ObservedObject var connection: OfficialSDKConnection
    let camera: SDKDiscoveredCamera
    let scenes: [VisualScene]
    private var purpose: String {
        let titles = scenes.filter { $0.status == "active" }.compactMap { $0.plan?.title }.joined(separator: " · ")
        return titles.isEmpty ? "还没有添加守护。告诉我想关注什么，再框选画面并确认开启。" : titles
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(camera.model == "T8214" ? "门铃摄像头" : "摄像头", systemImage: camera.model == "T8214" ? "door.left.hand.closed" : "video")
                    .font(.headline)
                Spacer(); Text(camera.model).font(.caption).foregroundStyle(Brand.muted)
            }
            Text(camera.name).font(.caption).foregroundStyle(Brand.muted).lineLimit(1)
            if let controller = connection.liveControllers[IOSToolExecutor.deviceID(camera.sn)] {
                CameraPreviewStatus(controller: controller, camera: camera)
            } else { Label("账号已连接 · 正在准备画面连接", systemImage: "antenna.radiowaves.left.and.right").font(.subheadline).foregroundStyle(.orange) }
            Text(purpose)
                .font(.subheadline)
            NavigationLink { VisualSceneEditor(initialCameraID: IOSToolExecutor.deviceID(camera.sn)) } label: {
                Label("添加守护", systemImage: "plus.circle.fill").font(.headline)
                    .frame(maxWidth: .infinity, minHeight: 48)
            }.buttonStyle(.borderedProminent).accessibilityIdentifier("cameraGuard.add." + camera.id)
        }.padding(16).background(.white.opacity(0.88)).clipShape(RoundedRectangle(cornerRadius: 22))
    }
}
private struct CameraPreviewStatus: View {
    @EnvironmentObject private var store: AppStore
    @ObservedObject var controller: LiveCameraController
    let camera: SDKDiscoveredCamera
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(controller.ready ? "助手已连接 · 可获取新画面" : "正在为助手连接…",
                  systemImage: controller.ready ? "checkmark.circle.fill" : "antenna.radiowaves.left.and.right")
                .font(.subheadline).foregroundStyle(controller.ready ? .green : .orange)
            if let at = controller.lastSampledAt {
                Text("最近取样 " + displayTime(at.timeIntervalSince1970)).font(.caption).foregroundStyle(Brand.muted)
            }
            if !controller.ready { Text(controller.status).font(.caption).foregroundStyle(Brand.muted) }
        }
    }
}

struct SceneResultCard: View {
    let scene: VisualScene
    private var color: Color { scene.resultState == "confirmed" ? .green : scene.resultState == "issue" ? .red : scene.resultState == "pending" ? Brand.blue : .orange }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                Image(systemName: scene.resultState == "confirmed" ? "checkmark.circle.fill" : "exclamationmark.circle.fill").foregroundStyle(color)
                Text(scene.plan?.title ?? "待完善的守护").font(.headline)
                Spacer(); Text(scene.resultLabel).font(.caption.weight(.semibold)).foregroundStyle(color)
            }
            Text(scene.summary.isEmpty ? scene.prompt : scene.summary).font(.subheadline).foregroundStyle(.primary).lineLimit(4)
            HStack { Text(scene.status == "draft" ? "条件待确认" : "条件已确认"); Text("· 事件触发") }.font(.caption).foregroundStyle(Brand.muted)
            if scene.status != "draft" {
                Text(scene.result?.reason ?? scene.observation.reason).font(.subheadline).foregroundStyle(Brand.muted)
                if let at = scene.observation.lastAt { Text("最近检查 " + displayTime(at)).font(.caption).foregroundStyle(Brand.muted) }
            }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(.white.opacity(0.9)).clipShape(RoundedRectangle(cornerRadius: 20))
    }
}
