import Combine
import Foundation
import Security
import UIKit
#if EVIDENCEGUARD_OFFICIAL_SDK
#if !canImport(SampleCore) || targetEnvironment(simulator)
#error("EvidenceGuardSDK must link the real arm64 SampleCore framework. Restore and prepare the official SDK first.")
#endif
#endif
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

struct SDKInspectionEvent: Decodable, Identifiable {
    var id: String
    var deviceSn: String
    var startMs: Int64
    var endMs: Int64
    var hasVideo: Bool
    var hasThumbnail: Bool
    var detectionType: String?
    var startDate: Date { Date(timeIntervalSince1970: Double(startMs) / 1_000) }
}

private struct SDKInspectionReceipt: Decodable {
    var status: String
    var code: String?
    var events: [SDKInspectionEvent]?
    var base64: String?
    var imageSource: String?
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
    @Published private(set) var inspecting = false
    @Published private(set) var events: [SDKInspectionEvent] = []
    @Published private(set) var picture: UIImage?
    @Published private(set) var pictureSource: String?
    @Published private(set) var inspectionMessage = "选择日期查询真实事件，或读取设备缩略图。"
    @Published private(set) var syncing = false
    @Published private(set) var syncMessage = "尚未同步官方事件"
    private var relayContinuation: CheckedContinuation<String, Error>?
    private var relayTimeout: Task<Void, Never>?
    private var relayRequestID = UUID()
    private var syncedImages = Set<String>()
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
        guard !checking && !inspecting && !syncing else { return }
        do { try save(credentials) } catch { message = error.localizedDescription; return }
        guard canDiscover else { message = buildStatus; return }
        requestGeneration += 1
        let generation = requestGeneration
        devices = []
        resetInspection()
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
    func queryEvents(camera: SDKDiscoveredCamera, date: Date) {
        guard beginInspection(camera) else { return }
        events = []
        picture = nil
        pictureSource = nil
        let generation = requestGeneration
        guard let day = Calendar.current.dateInterval(of: .day, for: date) else {
            inspecting = false
            inspectionMessage = "日期无法读取，请重新选择。"
            return
        }
        inspectionMessage = "正在查询所选日期的官方事件…"
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        bridge.queryEvents(sn: camera.sn, startMs: Int64(day.start.timeIntervalSince1970 * 1_000),
                           endMs: Int64(day.end.timeIntervalSince1970 * 1_000)) { [weak self] json in
            Task { @MainActor in
                guard let self, generation == self.requestGeneration else { return }
                self.inspecting = false
                guard let receipt = try? JSONDecoder().decode(SDKInspectionReceipt.self, from: Data(json.utf8)),
                      receipt.status == "success", let events = receipt.events else {
                    self.inspectionMessage = "事件查询未完成，请检查账号、设备与网络后重试。"
                    return
                }
                self.events = events
                self.inspectionMessage = events.isEmpty
                    ? "所选日期未返回事件；这不能证明现场没有活动。"
                    : "返回 \(events.count) 条事件（最多 50 条）。时间来自设备事件记录。"
            }
        }
        #endif
    }
    func readPicture(camera: SDKDiscoveredCamera, event: SDKInspectionEvent? = nil) {
        guard beginInspection(camera) else { return }
        picture = nil
        pictureSource = nil
        let generation = requestGeneration
        inspectionMessage = "正在读取\(event == nil ? "设备" : "事件")缩略图…"
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        bridge.readPicture(sn: camera.sn, eventId: event?.id) { [weak self] json in
            Task { @MainActor in
                guard let self, generation == self.requestGeneration else { return }
                self.inspecting = false
                guard let receipt = try? JSONDecoder().decode(SDKInspectionReceipt.self, from: Data(json.utf8)),
                      receipt.status == "success", let base64 = receipt.base64,
                      let data = Data(base64Encoded: base64), let image = UIImage(data: data) else {
                    self.inspectionMessage = "图片暂不可用，请检查设备是否产生了带缩略图的事件。"
                    return
                }
                self.picture = image
                self.pictureSource = receipt.imageSource
                self.inspectionMessage = "已读取缩略图。它可能来自历史事件或缓存，不能当作当前实时画面。"
            }
        }
        #endif
    }
    private func beginInspection(_ camera: SDKDiscoveredCamera) -> Bool {
        guard canDiscover, !checking, !inspecting, !syncing,
              devices.contains(where: { $0.sn == camera.sn && $0.isCompetitionCamera }) else {
            inspectionMessage = "请先完成官方设备查询，再检查赛事摄像头。"
            return false
        }
        inspecting = true
        return true
    }
    private func resetInspection() {
        inspecting = false
        events = []
        picture = nil
        pictureSource = nil
        inspectionMessage = "选择日期查询真实事件，或读取设备缩略图。"
    }
    func cancelInspection() {
        finishRelay(.failure(CancellationError()))
        requestGeneration += 1
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        bridge.cancelInspection()
        #endif
        resetInspection()
    }
    func disconnect() {
        finishRelay(.failure(CancellationError()))
        requestGeneration += 1
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        bridge.disconnect()
        #endif
        checking = false
        devices = []
        resetInspection()
        message = "SDK 会话已断开，保存的配置仍在本机"
    }
    func clearCredentials() throws {
        disconnect()
        try SDKCredentialVault.clear()
        message = "凭证已清除，等待主办方发放账号与 Token"
    }

    private func finishRelay(_ result: Result<String, Error>) {
        relayTimeout?.cancel(); relayTimeout = nil
        let continuation = relayContinuation; relayContinuation = nil
        continuation?.resume(with: result)
    }

    private func relayRequest(_ begin: (@escaping (String) -> Void) -> Void) async throws -> String {
        try Task.checkCancellation()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                let id = UUID(); relayRequestID = id; relayContinuation = continuation
                relayTimeout = Task { [weak self] in
                    do { try await Task.sleep(for: .seconds(35)) } catch { return }
                    guard let self, self.relayRequestID == id else { return }
                    self.finishRelay(.failure(APIProblem(message: "设备事件读取超时，请重试。")))
                }
                begin { [weak self] json in
                    Task { @MainActor in
                        guard let self, self.relayRequestID == id else { return }
                        self.finishRelay(.success(json))
                    }
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.cancelInspection() }
        }
    }

    func syncEvents(camera: SDKDiscoveredCamera, date: Date, client: APIClient, recentOnly: Bool = false) async {
        guard canDiscover, !syncing, !checking, !inspecting,
              devices.contains(where: { $0.sn == camera.sn && $0.isCompetitionCamera }) else {
            syncMessage = "请先完成官方设备查询"; return
        }
        syncing = true; defer { syncing = false }
        let syncGeneration = requestGeneration
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        do {
            let interval = Calendar.current.dateInterval(of: .day, for: date)!
            let end = recentOnly ? Date() : min(interval.end, Date())
            let start = recentOnly ? end.addingTimeInterval(-120) : interval.start
            let json = try await relayRequest { completion in
                bridge.queryEvents(sn: camera.sn, startMs: Int64(start.timeIntervalSince1970 * 1_000),
                                   endMs: Int64(end.timeIntervalSince1970 * 1_000), completion: completion)
            }
            let receipt = try JSONDecoder().decode(SDKInspectionReceipt.self, from: Data(json.utf8))
            guard receipt.status == "success", let returned = receipt.events else { throw APIProblem(message: "官方事件查询未完成") }
            guard syncGeneration == requestGeneration else { throw CancellationError() }
            events = returned
            // Preserve every returned event's metadata; upload images separately to
            // keep each HTTP body bounded. Only actual event images are eligible.
            for offset in stride(from: 0, to: returned.count, by: 10) {
                guard syncGeneration == requestGeneration else { throw CancellationError() }
                try Task.checkCancellation()
                let items = returned[offset..<min(offset + 10, returned.count)].map { SDKCloudEvent(camera: camera, event: $0) }
                _ = try await client.ingestSDKEvents(Array(items), review: false)
            }
            var images = 0
            for event in returned.filter({ $0.hasThumbnail && !syncedImages.contains(client.baseURL.absoluteString + ":" + $0.id) }).prefix(10) {
                try Task.checkCancellation()
                guard syncGeneration == requestGeneration else { throw CancellationError() }
                syncMessage = "事件已入库，正在同步第 \(images + 1) 张证据图片…"
                let json = try await relayRequest { bridge.readPicture(sn: camera.sn, eventId: event.id, completion: $0) }
                let picture = try JSONDecoder().decode(SDKInspectionReceipt.self, from: Data(json.utf8))
                guard picture.status == "success", picture.imageSource == "event_thumbnail",
                      let encoded = picture.base64, let bytes = Data(base64Encoded: encoded, options: .ignoreUnknownCharacters),
                      bytes.count <= 8_000_000, let image = UIImage(data: bytes),
                      let jpeg = image.jpegData(compressionQuality: 0.8), jpeg.count <= 5_000_000 else { continue }
                guard syncGeneration == requestGeneration else { throw CancellationError() }
                var item = SDKCloudEvent(camera: camera, event: event); item.imageBase64 = jpeg.base64EncodedString()
                _ = try await client.ingestSDKEvents([item], review: true)
                syncedImages.insert(client.baseURL.absoluteString + ":" + event.id); images += 1
            }
            if syncedImages.count > 500 { syncedImages.removeAll() } // Server dedupe remains authoritative.
            syncMessage = "已同步 \(returned.count) 条事件、本次 \(images) 张图片，云端将合并核验。" + (returned.count >= 50 ? "本次达到查询上限，不代表完整记录。" : "")
            if returned.isEmpty { syncMessage = "本次未返回事件；不代表现场没有活动。" }
        } catch is CancellationError {
            syncMessage = "前台同步已暂停；已保存的事件仍可在证据页查看。"
        } catch {
            syncMessage = error.localizedDescription + "；已接收的事件保留，稍后可重试。"
        }
        #else
        syncMessage = buildStatus
        #endif
    }
}

struct SDKCloudEvent: Encodable {
    var eventId: String; var deviceSn: String; var model: String; var deviceName: String
    var startMs: Int64; var endMs: Int64; var detectionType: String; var hasVideo: Bool
    var imageBase64: String? = nil
    var imageSource = "event_thumbnail"
    init(camera: SDKDiscoveredCamera, event: SDKInspectionEvent) {
        eventId = event.id; deviceSn = camera.sn; model = camera.model; deviceName = camera.name
        startMs = event.startMs; endMs = max(event.startMs, event.endMs)
        detectionType = event.detectionType ?? "unknown"; hasVideo = event.hasVideo
    }
}
struct SDKImportReceipt: Decodable {
    struct Item: Decodable { var id: String; var status: String; var imageSaved: Bool }
    var receipts: [Item]; var continuousCoverage: Bool
}
