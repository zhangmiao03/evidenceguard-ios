import Combine
import Foundation
import Security
#if canImport(SampleCore) && !targetEnvironment(simulator)
import SampleCore
#endif

struct SDKCredentials: Codable, Equatable {
    var userID = ""
    var token = ""
    var environment = "PR"
    var isComplete: Bool {
        !userID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        ["PR", "QA"].contains(environment)
    }
    var normalized: SDKCredentials {
        .init(userID: userID.trimmingCharacters(in: .whitespacesAndNewlines),
              token: token.trimmingCharacters(in: .whitespacesAndNewlines), environment: environment)
    }
}

struct SDKDiscoveredCamera: Decodable, Identifiable {
    var sn: String
    var model: String
    var name: String
    var online: Bool?
    var capabilitiesReady: Bool
    var properties: [String]
    var actions: [String]
    var events: [String]
    var id: String { sn }
    var isCompetitionCamera: Bool { ["T8171", "T8214"].contains(model) }
}

struct SDKDiscoveryReceipt: Decodable {
    var status: String
    var code: String?
    var devices: [SDKDiscoveredCamera]?
}

enum SDKCredentialVault {
    private static let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "com.evidenceguard.official-sdk",
        kSecAttrAccount as String: "competition-credentials"
    ]
    static func load() throws -> SDKCredentials? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw VaultError(status: status) }
        return try JSONDecoder().decode(SDKCredentials.self, from: data)
    }
    static func save(_ credentials: SDKCredentials) throws {
        let data = try JSONEncoder().encode(credentials.normalized)
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            status = SecItemAdd(query.merging(attributes) { _, value in value } as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw VaultError(status: status) }
    }
    static func clear() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw VaultError(status: status) }
    }
    private struct VaultError: LocalizedError {
        let status: OSStatus
        var errorDescription: String? { "凭证未能保存或读取（\(status)），请重新尝试。" }
    }
}

@MainActor final class OfficialSDKConnection: ObservableObject {
    @Published private(set) var devices: [SDKDiscoveredCamera] = []
    @Published private(set) var checking = false
    @Published private(set) var message = "等待主办方发放账号与 Token"
    private var requestGeneration = 0
    #if canImport(SampleCore) && !targetEnvironment(simulator)
    private let bridge = EvidenceGuardSDKBridge()
    #endif

    var canDiscover: Bool {
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        true
        #else
        false
        #endif
    }
    var buildStatus: String {
        #if targetEnvironment(simulator)
        "当前是模拟器，可准备配置；官方 SDK 需要 iPhone 真机。"
        #elseif canImport(SampleCore)
        "官方 SDK 已链接，等待账号与设备验证。"
        #else
        "当前构建未链接官方 SDK，请选择 EvidenceGuardSDK 真机方案。"
        #endif
    }
    func save(_ credentials: SDKCredentials) throws {
        guard credentials.isComplete else { throw APIProblem(message: "请填写主办方发放的 User ID 和 Token。", conflicts: []) }
        try SDKCredentialVault.save(credentials)
        message = "配置已保存到本机 Keychain，设备尚未验证"
    }
    func discover(_ credentials: SDKCredentials) {
        guard !checking else { return }
        do { try save(credentials) } catch { message = error.localizedDescription; return }
        guard canDiscover else { message = buildStatus; return }
        requestGeneration += 1
        let generation = requestGeneration
        devices = []
        checking = true
        message = "正在从官方服务获取账号下的设备…"
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        let normalized = credentials.normalized
        bridge.connect(userId: normalized.userID, token: normalized.token,
                       environment: normalized.environment) { [weak self] json in
            Task { @MainActor in
                guard let self, generation == self.requestGeneration else { return }
                self.checking = false
                guard let receipt = try? JSONDecoder().decode(SDKDiscoveryReceipt.self, from: Data(json.utf8)) else {
                    self.message = "SDK 返回格式无法读取，设备仍待验证"; return
                }
                guard receipt.status == "success", let devices = receipt.devices else {
                    self.message = receipt.code == "environment_restart_required"
                        ? "切换 SDK 环境后请重新启动 App，再检查设备。"
                        : "设备查询未完成（\(receipt.code ?? "unknown")），请检查主办方账号、Token 与网络。"
                    return
                }
                self.devices = devices
                let count = devices.filter(\.isCompetitionCamera).count
                self.message = count > 0 ? "发现 \(count) 台赛事摄像头；画面与任务执行尚待验收"
                                        : "查询完成，账号下暂未发现 T8171 / T8214"
            }
        }
        #endif
    }
    func disconnect() {
        requestGeneration += 1
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        bridge.disconnect()
        #endif
        checking = false
        devices = []
        message = "SDK 会话已断开，保存的配置仍在本机"
    }
    func clearCredentials() throws {
        disconnect()
        try SDKCredentialVault.clear()
        message = "凭证已清除，等待主办方发放账号与 Token"
    }
}
