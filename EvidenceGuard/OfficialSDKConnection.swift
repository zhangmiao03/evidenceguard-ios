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
    let toolExecutor = IOSToolExecutor()
    @Published private(set) var devices: [SDKDiscoveredCamera] = []
    @Published private(set) var officialDemoController: UIViewController?
    @Published private(set) var switchingWorkspace = false
    @Published private(set) var workspaceMessage = ""
    @Published var workspaceError: String?
    weak var liveController: LiveCameraController?
    @Published private(set) var checking = false
    @Published private(set) var message = SDKConfiguration.current.usesManagedAccount
        ? "已配置摄像头账号，等待连接设备" : "等待主办方发放账号与 Token"
    @Published private(set) var inspecting = false
    @Published private(set) var events: [SDKInspectionEvent] = []
    @Published private(set) var picture: UIImage?
    @Published private(set) var pictureSource: String?
    @Published private(set) var inspectionMessage = "选择日期查询真实事件，或读取设备缩略图。"
    @Published private(set) var syncing = false
    @Published private(set) var syncMessage = "尚未同步官方事件"
    @Published private(set) var eventSyncOrigin = UserDefaults.standard.string(forKey: "sdkEventSyncOrigin")
    private var relayContinuation: CheckedContinuation<String, Error>?
    private var relayTimeout: Task<Void, Never>?
    private var relayRequestID = UUID()
    private var syncedImages = Set<String>()
    private var requestGeneration = 0
    private var connectedCredentials: SDKCredentials?
    #if canImport(SampleCore) && !targetEnvironment(simulator)
    private let bridge = EvidenceGuardSDKBridge()
    private var officialOrientation: FoundationCancellableJob?
    #endif

    var canDiscover: Bool {
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        true
        #else
        false
        #endif
    }
    var usesManagedAccount: Bool { SDKConfiguration.current.usesManagedAccount }
    func configuredCredentials() throws -> SDKCredentials? {
        if usesManagedAccount {
            guard let credentials = SDKConfiguration.current.credentials else {
                throw APIProblem(message: "此版本的摄像头连接配置不完整，请更新 App 后重试。")
            }
            return credentials
        }
        return try SDKCredentialVault.load()
    }
    func discoverConfigured(client: APIClient) {
        do {
            guard let credentials = try configuredCredentials() else {
                message = "请先配置摄像头账号"; return
            }
            discover(credentials, client: client)
        } catch { message = error.localizedDescription }
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
    func discover(_ credentials: SDKCredentials, client: APIClient? = nil) {
        guard officialDemoController == nil, !switchingWorkspace, !checking && !inspecting && !syncing else { return }
        do { try save(credentials) } catch { message = error.localizedDescription; return }
        guard canDiscover else { message = buildStatus; return }
        requestGeneration += 1
        let generation = requestGeneration
        devices = []
        connectedCredentials = nil
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
                        : self.usesManagedAccount
                            ? "设备连接未完成，请检查网络后重试；若仍失败，需要更新此版本的联调配置。"
                            : "设备查询未完成，请检查账号配置与网络。"
                    return
                }
                self.devices = devices
                self.connectedCredentials = normalized
                let count = devices.filter(\.isCompetitionCamera).count
                self.message = count > 0 ? "发现 \(count) 台赛事摄像头；画面与任务执行尚待验收"
                                        : "查询完成，账号下暂未发现 T8171 / T8214"
                if let client, count > 0 {
                    do { try await client.registerSDKDevices(devices) }
                    catch { self.syncMessage = "设备已找到，云端同步暂未完成，请重试。" }
                }
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
        checking = false
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        bridge.cancelInspection()
        #endif
        resetInspection()
    }
    func disconnect() {
        toolExecutor.invalidate()
        eventSyncOrigin = nil
        UserDefaults.standard.removeObject(forKey: "sdkEventSyncOrigin")
        liveController?.stop()
        connectedCredentials = nil
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

    func syncEnabled(for client: APIClient) -> Bool { eventSyncOrigin == client.baseURL.absoluteString }
    func setEventSync(_ enabled: Bool, client: APIClient) {
        eventSyncOrigin = enabled ? client.baseURL.absoluteString : nil
        UserDefaults.standard.set(eventSyncOrigin, forKey: "sdkEventSyncOrigin")
        if !enabled { cancelInspection(); syncMessage = "自动同步已暂停，已保存的事件仍可查看。" }
    }
    func restoreSession(client: APIClient) {
        guard syncEnabled(for: client), devices.isEmpty, !checking, canDiscover,
              let credentials = try? configuredCredentials() else { return }
        discover(credentials, client: client)
    }
    func syncRecentEvents(client: APIClient) async {
        guard syncEnabled(for: client), officialDemoController == nil, !switchingWorkspace else { return }
        for camera in devices.filter(\.isCompetitionCamera) {
            guard syncEnabled(for: client), !Task.isCancelled else { return }
            await syncEvents(camera: camera, date: Date(), client: client, recentOnly: true)
        }
    }
    func enterOfficialWorkspace() async {
        guard canDiscover, officialDemoController == nil, !switchingWorkspace else { return }
        // Compose 1.7.1 checks the host plist asynchronously and aborts on a
        // missing flag. Check before stopping the current camera/session;
        // Swift error handling cannot catch that Kotlin background failure.
        if let issue = SDKConfiguration.workspaceIssue(info: Bundle.main.infoDictionary ?? [:],
            resourceExists: { FileManager.default.fileExists(atPath: Bundle.main.bundleURL.appendingPathComponent($0).path) }) {
            workspaceError = issue
            return
        }
        let managedCredentials: SDKCredentials?
        do { managedCredentials = usesManagedAccount ? try configuredCredentials() : nil }
        catch { workspaceError = error.localizedDescription; return }
        workspaceError = nil
        switchingWorkspace = true
        defer { switchingWorkspace = false }
        workspaceMessage = "正在停止本项目直播与取帧…"
        await toolExecutor.shutdown()
        await liveController?.stopForWorkspaceSwitch()
        disconnect()
        // EvidenceGuardLiveBridge releases the native player after 500 ms.
        do { try await Task.sleep(for: .milliseconds(650)) }
        catch { workspaceMessage = "已取消打开摄像头页面"; return }
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        do {
            if let credentials = managedCredentials {
                officialDemoController = try bridge.openOfficialDemoWithAccount(
                    userId: credentials.userID, token: credentials.token, environment: credentials.environment)
            } else {
                officialDemoController = try bridge.openOfficialDemo()
            }
        } catch {
            workspaceError = "摄像头页面暂时未能启动，请重新打开 App 后重试。"
            return
        }
        officialOrientation = ToggleScreenOrientationKt.fullScreen.collectData { [weak self] value in
            Task { @MainActor in
                guard self?.officialDemoController != nil else { return }
                PushAppDelegate.setOrientation((value as? Bool) == true ? .landscape : .portrait)
            }
        }
        #endif
        workspaceMessage = usesManagedAccount ? "已打开摄像头页面，正在使用内置联调账号" : "官方原版 Demo · 请在原版登录页核对账号和环境"
    }

    func leaveOfficialWorkspace() async {
        guard officialDemoController != nil, !switchingWorkspace else { return }
        switchingWorkspace = true
        workspaceMessage = "正在释放官方页面、播放器与订阅…"
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        officialOrientation?.cancel(); officialOrientation = nil
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            bridge.closeOfficialDemo { continuation.resume() }
        }
        #endif
        officialDemoController = nil
        PushAppDelegate.setOrientation(.portrait)
        connectedCredentials = nil; devices = []
        message = "已从官方工作区返回，请重新查询账号下的设备并同步。"
        workspaceMessage = "已返回 EvidenceGuard；直播不会自动恢复"
        switchingWorkspace = false
    }

    func importDevices(client: APIClient) async throws -> [RegisteredCamera] {
        guard let credentials = connectedCredentials else { throw APIProblem(message: "请先用官方账号查询设备") }
        let cameras = devices.filter(\.isCompetitionCamera)
        guard !cameras.isEmpty else { throw APIProblem(message: "官方账号下没有可导入的赛事设备") }
        return try await client.importDevices(account: credentials.userID, environment: credentials.environment, cameras: cameras)
    }

    func hardwareManifest(camera: SDKDiscoveredCamera) async throws -> HardwareValue {
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        let json: String = await withCheckedContinuation { continuation in
            bridge.hardwareManifest(sn: camera.sn) { continuation.resume(returning: $0) }
        }
        return try HardwareValue.parse(json)
        #else
        throw APIProblem(message: "此构建未包含官方 arm64 SDK")
        #endif
    }

    func executeHardware(camera: SDKDiscoveredCamera, command: HardwareValue) async throws -> HardwareValue {
        guard officialDemoController == nil, !switchingWorkspace, devices.contains(where: { $0.sn == camera.sn }) else {
            throw APIProblem(message: "设备执行会话已结束")
        }
        #if canImport(SampleCore) && !targetEnvironment(simulator)
        let json: String = await withCheckedContinuation { continuation in
            bridge.executeHardware(sn: camera.sn, commandJSON: command.json) { continuation.resume(returning: $0) }
        }
        return try HardwareValue.parse(json)
        #else
        throw APIProblem(message: "此构建未包含官方 arm64 SDK")
        #endif
    }

    #if canImport(SampleCore) && !targetEnvironment(simulator)
    func makeLive(camera: SDKDiscoveredCamera) -> EvidenceGuardLiveBridge? {
        bridge.createLive(sn: camera.sn)
    }
    #endif
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
        let id = UUID()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                relayRequestID = id; relayContinuation = continuation
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
            Task { @MainActor [weak self] in
                guard let self, self.relayRequestID == id else { return }
                self.cancelInspection()
            }
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
            guard returned.allSatisfy({ $0.deviceSn == camera.sn }) else { throw APIProblem(message: "事件设备与所选摄像头不一致，未同步。") }
            guard syncGeneration == requestGeneration else { throw CancellationError() }
            try await client.registerSDKDevices([camera])
            events = returned
            // Preserve every returned event's metadata; upload images separately to
            // keep each HTTP body bounded. Only actual event images are eligible.
            for offset in stride(from: 0, to: returned.count, by: 10) {
                guard syncGeneration == requestGeneration else { throw CancellationError() }
                try Task.checkCancellation()
                let items = returned[offset..<min(offset + 10, returned.count)].map { SDKCloudEvent(camera: camera, event: $0) }
                // Fresh human/doorbell metadata can produce a qualified notice
                // even if the vendor has not made its thumbnail available yet.
                _ = try await client.ingestSDKEvents(Array(items), review: recentOnly)
            }
            var images = 0
            for event in returned.filter({ $0.hasThumbnail && !syncedImages.contains(client.baseURL.absoluteString + ":" + camera.sn + ":" + $0.id) }).prefix(10) {
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
                syncedImages.insert(client.baseURL.absoluteString + ":" + camera.sn + ":" + event.id); images += 1
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
