import SwiftUI

struct OfficialSDKInspectionView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject var connection: OfficialSDKConnection
    let camera: SDKDiscoveredCamera
    @State private var date = Date()

    var body: some View {
        List {
            Section(camera.name) {
                Text(camera.model).font(.subheadline)
                Text("事件来自这台摄像头，图片为对应事件的缩略图。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            Section("设备图片") {
                Button("读取设备缩略图") { connection.readPicture(camera: camera) }
                    .disabled(connection.inspecting || connection.checking || connection.syncing)
                    .accessibilityIdentifier("sdk.read-picture")
                Text("设备缩略图或缓存封面可能较旧，不作为实时判断依据。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            if let image = connection.picture {
                Section("读取结果") {
                    Image(uiImage: image).resizable().scaledToFit()
                    Text(pictureLabel).font(.caption).foregroundStyle(Brand.muted)
                }
            }
            Section("历史事件") {
                DatePicker("查询日期", selection: $date, in: ...Date(), displayedComponents: .date)
                    .disabled(connection.inspecting || connection.syncing)
                Text("按 iPhone 当前时区的自然日查询，最多返回 50 条。")
                    .font(.caption).foregroundStyle(Brand.muted)
                Button("查询该日事件") { connection.queryEvents(camera: camera, date: date) }
                    .disabled(connection.inspecting || connection.checking || connection.syncing)
                    .accessibilityIdentifier("sdk.query-events")
                if connection.inspecting { ProgressView("正在等待 SDK 返回…") }
                Text(connection.inspectionMessage).font(.caption).foregroundStyle(Brand.muted)
                ForEach(connection.events) { event in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(event.startDate, format: .dateTime.year().month().day().hour().minute().second())
                            .font(.subheadline.bold())
                        Text("\(max(0, (event.endMs - event.startMs) / 1_000)) s · \(event.hasVideo ? "有录像记录" : "无录像记录")")
                            .font(.caption).foregroundStyle(Brand.muted)
                        if event.hasThumbnail {
                            Button("查看事件缩略图") { connection.readPicture(camera: camera, event: event) }
                                .disabled(connection.inspecting || connection.syncing)
                        }
                    }.padding(.vertical, 4)
                }
            }
            Section("同步到助手") {
                Button("同步所选日期的事件与图片") {
                    Task { await connection.syncEvents(camera: camera, date: date, client: store.client); await store.refresh() }
                }.disabled(connection.syncing || connection.inspecting || connection.checking || !store.isConnected)
                if connection.syncing { ProgressView("正在同步事件证据…") }
                Text(connection.syncMessage).font(.caption).foregroundStyle(Brand.muted)
                Text("在摄像头首页开启自动同步后，App 打开时每 30 秒查询近期事件；离开这页继续同步，锁屏暂停。重复事件不会重复入库。")
                    .font(.caption).foregroundStyle(Brand.muted)
                NavigationLink("查看云端证据", value: AppRoute.evidenceList(nil))
            }
            Section("决赛验收") {
                Text("拿到设备后，在摄像头前完成一次经过或放下包裹的动作，再查询事件并核对缩略图与时间。SDK 返回成功、图片可读和任务可执行是不同的验收步骤。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
        }.pageStyle(camera.name + "事件")
            .onChange(of: scenePhase) { _, phase in
                if phase != .active { connection.cancelInspection() }
            }
            .onDisappear { if !connection.syncing { connection.cancelInspection() } }
    }

    private var pictureLabel: String {
        switch connection.pictureSource {
        case "event_thumbnail": "官方事件缩略图 · 非实时画面"
        case "cached_cover": "官方缓存封面 · 拍摄时间未知"
        default: "官方设备缩略图 · 拍摄时间待核实"
        }
    }
}

struct SDKEventSyncWorker: View {
    @ObservedObject var connection: OfficialSDKConnection
    let client: APIClient
    let active: Bool
    let refresh: () async -> Void
    private var key: String { "\(active):\(client.baseURL.absoluteString):\(connection.eventSyncOrigin ?? "")" }
    var body: some View {
        Color.clear.frame(width: 0, height: 0).task(id: key) {
            guard active, connection.syncEnabled(for: client) else { return }
            connection.restoreSession(client: client)
            while !Task.isCancelled && connection.syncEnabled(for: client) {
                await connection.syncRecentEvents(client: client)
                await refresh()
                do { try await Task.sleep(for: .seconds(30)) } catch { return }
            }
        }
    }
}
