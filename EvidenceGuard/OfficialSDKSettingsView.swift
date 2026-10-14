import SwiftUI

struct OfficialSDKSettingsView: View {
    @EnvironmentObject private var store: AppStore
    @ObservedObject var connection: OfficialSDKConnection
    @State private var credentials = SDKCredentials()
    @State private var feedback: String?

    var body: some View {
        Form {
            Section("完整官方功能") {
                Button("切换到官方原版：配网、绑定与设备设置") { Task { await connection.enterOfficialWorkspace() } }
                    .disabled(!connection.canDiscover || connection.switchingWorkspace)
                Text("顶部工作区按钮可随时返回。官方页面中的更改实际作用于设备，返回后请重新查询并同步。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            Section("接入状态") {
                Text(connection.buildStatus).font(.subheadline)
                Text(connection.message).font(.caption).foregroundStyle(Brand.muted)
            }
            Section("主办方账号") {
                Picker("SDK 环境", selection: $credentials.environment) {
                    Text("PR").tag("PR")
                    Text("QA").tag("QA")
                }
                TextField("User ID", text: $credentials.userID)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("sdk.user-id")
                SecureField("Token", text: $credentials.token)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("sdk.token")
                Text("填写赛事发放的 User ID 和 Token，环境以主办方说明为准。凭证保存在本机 Keychain。")
                    .font(.caption).foregroundStyle(Brand.muted)
                Button("保存配置") {
                    do { try connection.save(credentials); feedback = "配置已保存" }
                    catch { feedback = error.localizedDescription }
                }.disabled(!credentials.isComplete || connection.checking)
                Button { connection.discover(credentials) } label: {
                    HStack { if connection.checking { ProgressView() }; Text("检查官方设备") }
                }.disabled(!credentials.isComplete || connection.checking || connection.inspecting || !connection.canDiscover)
                    .accessibilityIdentifier("sdk.discover")
                if let feedback { Text(feedback).font(.caption) }
            }
            if !connection.devices.isEmpty {
                Section("官方账号下的设备") {
                    Button("同步到我的设备") {
                        Task { do { let imported = try await connection.importDevices(client: store.client); await store.refresh(); feedback = "已同步 \(imported.count) 台设备" } catch { feedback = error.localizedDescription } }
                    }
                    ForEach(connection.devices) { camera in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(camera.name).font(.headline)
                            Text("\(camera.model) · \(camera.online.map { $0 ? "在线" : "离线" } ?? "连接状态待确认")")
                                .font(.subheadline)
                            Text(camera.sn).font(.caption.monospaced()).textSelection(.enabled)
                            Text(camera.capabilitiesReady
                                 ? "物模型：\(camera.properties.count) 个属性 / \(camera.actions.count) 个动作 / \(camera.events.count) 个事件"
                                 : "物模型尚未就绪，设备能力待验证")
                                .font(.caption).foregroundStyle(Brand.muted)
                            if !camera.isCompetitionCamera { Text("此设备不属于本次接入的两款型号").font(.caption) }
                            if camera.isCompetitionCamera {
                                NavigationLink("实时查看与 Agent") { OfficialLiveCameraView(camera: camera) }
                                NavigationLink("检查图片与历史事件") {
                                    OfficialSDKInspectionView(connection: connection, camera: camera)
                                }
                            }
                        }.padding(.vertical, 4)
                    }
                }
            }
            Section("连接方式") {
                Label("iPhone：通过 TestFlight 安装测试包", systemImage: "airplane")
                Label("摄像头 → SDK：网络连接，用于查询与读取媒体", systemImage: "wifi")
                Text("TestFlight 安装不需要连接 Mac 或开启开发者模式。决赛拿到摄像头与赛事账号后再检查设备；USB 是可选的 Xcode 调试方式。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            Section("设备验收") {
                Text("检查设备列表只是接入第一步。截图、录像下载、断流恢复以及守护试跑验收通过后，才能启用真实 Skill。")
                    .font(.caption).foregroundStyle(Brand.muted)
            }
            Section {
                Button("断开 SDK 会话") { connection.disconnect() }.disabled(connection.devices.isEmpty && !connection.checking)
                Button("清除本机 SDK 凭证", role: .destructive) {
                    do { try connection.clearCredentials(); credentials = SDKCredentials(); feedback = nil }
                    catch { feedback = error.localizedDescription }
                }
            }
        }.pageStyle("官方摄像头接入")
            .task {
                do { if let saved = try SDKCredentialVault.load() { credentials = saved } }
                catch { feedback = error.localizedDescription }
            }
    }
}
