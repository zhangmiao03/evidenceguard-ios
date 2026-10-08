import SwiftUI

struct OfficialSDKSettingsView: View {
    @ObservedObject var connection: OfficialSDKConnection
    @State private var credentials = SDKCredentials()
    @State private var feedback: String?

    var body: some View {
        Form {
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
                }.disabled(!credentials.isComplete || connection.checking || !connection.canDiscover)
                    .accessibilityIdentifier("sdk.discover")
                if let feedback { Text(feedback).font(.caption) }
            }
            if !connection.devices.isEmpty {
                Section("官方账号下的设备") {
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
                        }.padding(.vertical, 4)
                    }
                }
            }
            Section("连接方式") {
                Label("iPhone → Mac：USB 数据线，用于安装和调试", systemImage: "cable.connector")
                Label("摄像头 → SDK：Wi‑Fi，用于查询与取画面", systemImage: "wifi")
                Text("真机首次安装需在 Xcode 选择你的 Team，并在 iPhone 信任这台 Mac、开启开发者模式。设备已由主办方绑定时，直接使用账号查询。")
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
