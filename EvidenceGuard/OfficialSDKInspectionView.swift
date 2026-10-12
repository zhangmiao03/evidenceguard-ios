import SwiftUI

struct OfficialSDKInspectionView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject var connection: OfficialSDKConnection
    let camera: SDKDiscoveredCamera
    @State private var date = Date()
    @State private var foregroundSync = false

    var body: some View {
        List {
            Section(camera.name) {
                Text(camera.model).font(.subheadline)
                Text("此页检查官方 SDK 返回的数据，尚未启用摄像头守护任务。")
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
                Toggle("本页前台同步新事件", isOn: $foregroundSync)
                    .disabled(!connection.canDiscover || !store.isConnected)
                if connection.syncing { ProgressView("正在同步事件证据…") }
                Text(connection.syncMessage).font(.caption).foregroundStyle(Brand.muted)
                Text("每 30 s 查询最近 120 s 的事件，重复记录不会重复入库。图片交给云端合并核验，可在证据页查看。离开本页或锁屏会暂停同步；尚未验收持续后台守护。")
                    .font(.caption).foregroundStyle(Brand.muted)
                NavigationLink("查看云端证据", value: AppRoute.evidenceList(nil))
            }
            Section("决赛验收") {
                Text("拿到设备后，在摄像头前完成一次经过或放下包裹的动作，再查询事件并核对缩略图与时间。SDK 返回成功、图片可读和任务可执行是不同的验收步骤。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
        }.pageStyle("设备联调")
            .task(id: foregroundSync && scenePhase == .active) {
                guard foregroundSync, scenePhase == .active else { return }
                while !Task.isCancelled {
                    await connection.syncEvents(camera: camera, date: Date(), client: store.client, recentOnly: true)
                    await store.refresh()
                    do { try await Task.sleep(for: .seconds(30)) } catch { return }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase != .active { connection.cancelInspection() }
            }
            .onDisappear { connection.cancelInspection() }
    }

    private var pictureLabel: String {
        switch connection.pictureSource {
        case "event_thumbnail": "官方事件缩略图 · 非实时画面"
        case "cached_cover": "官方缓存封面 · 拍摄时间未知"
        default: "官方设备缩略图 · 拍摄时间待核实"
        }
    }
}
