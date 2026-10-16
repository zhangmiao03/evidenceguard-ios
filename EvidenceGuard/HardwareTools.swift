import SwiftUI
import CryptoKit

struct HardwareExecutorSession: Sendable { var id: String; var token: String; var deviceID: String }

@MainActor final class IOSToolExecutor: ObservableObject {
    @Published private(set) var message = "连接官方设备后，可在前台执行已授权工具"
    private var sessions: [String: HardwareExecutorSession] = [:]
    private var clients: [String: APIClient] = [:]
    private var pending: [String: [String: HardwareValue]] = [:]
    private var active: [String: Task<Void, Never>] = [:]
    private var cleanup: Task<Void, Never>?
    private var generation = UUID()
    private var released = Set<String>()

    nonisolated static func deviceID(_ sn: String) -> String {
        "sdk-" + String(SHA256.hash(data: Data(sn.utf8)).map { String(format: "%02x", $0) }.joined().prefix(20))
    }

    func run(connection: OfficialSDKConnection, client: APIClient) async {
        await shutdown()
        guard !Task.isCancelled else { return }
        let epoch = UUID(); generation = epoch; released = []
        while !Task.isCancelled && epoch == generation {
            guard connection.officialDemoController == nil, !connection.switchingWorkspace else { break }
            for camera in connection.devices.filter(\.isCompetitionCamera) {
                if released.contains(camera.sn) { continue }
                guard !Task.isCancelled && epoch == generation else { break }
                do {
                    if sessions[camera.sn] == nil {
                        let hash = Bundle.main.object(forInfoDictionaryKey: "EGSDKArtifactHash") as? String ?? ""
                        guard hash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else {
                            message = "工具执行等待 SDK 构件指纹，请先运行 SDK/prepare.py"; continue
                        }
                        // Discovery and live registration use the same canonical device ID.
                        try await client.registerSDKDevices([camera])
                        let manifest = try await connection.hardwareManifest(camera: camera)
                        try Task.checkCancellation()
                        guard epoch == generation else { break }
                        guard !manifest["routes"].object.isEmpty else { throw APIProblem(message: "SDK 能力尚未就绪") }
                        let body: HardwareValue = .object([
                            "deviceId": .string(Self.deviceID(camera.sn)), "model": .string(camera.model), "platform": .string("ios"),
                            "adapterVersion": .string("ios-tools-1"), "sdkArtifactHash": .string(hash), "firmwareVersion": .string("unknown"),
                            "officialIdentityReady": .bool(true), "privacy": manifest["privacy"], "routes": manifest["routes"], "fields": manifest["fields"]])
                        let receipt = try await client.hardware("executors", body: body)
                        let session = HardwareExecutorSession(id: receipt["executorId"].string, token: receipt["token"].string, deviceID: Self.deviceID(camera.sn))
                        guard !session.id.isEmpty && !session.token.isEmpty else { throw APIProblem(message: "执行器登记回执不完整") }
                        if epoch != generation || Task.isCancelled {
                            _ = try? await client.hardware("executors/\(session.id)/disconnect", body: .object([:]), executor: session); break
                        }
                        sessions[camera.sn] = session; clients[camera.sn] = client
                    }
                    guard let session = sessions[camera.sn] else { continue }
                    for (key, result) in pending[camera.sn] ?? [:] {
                        // Only redeliver receipts. Physical calls are never replayed.
                        _ = try await client.hardware("executors/\(session.id)/result", body: result, executor: session)
                        pending[camera.sn]?[key] = nil
                    }
                    let command = try await client.hardware("executors/\(session.id)/claim", body: .object([:]), executor: session)
                    guard !Task.isCancelled && epoch == generation else { break }
                    guard !command["command"].string.isEmpty else { continue }
                    let op = command["operation"]
                    guard op["deviceId"].string == session.deviceID, op["executorPlatform"].string == "iOS", !op["simulated"].boolean else {
                        throw APIProblem(message: "执行命令与当前设备不匹配")
                    }
                    let key = op["id"].string + ":" + command["command"].string
                    guard active[key] == nil, pending[camera.sn]?[key] == nil else { continue }
                    // Polling stays available while an SDK call is suspended, so stop has its own dispatch path.
                    active[key] = Task { [weak self] in
                        guard let self else { return }
                        var result: HardwareValue
                        do {
                            if command["command"].string == "stop", !op["control"].boolean {
                                result = .object(["status": .string("stopped"), "sdkUsed": .bool(false), "data": .object(["scope": .string("discard_read_result")])])
                            } else if op["tool"].string == "camera_observe", command["command"].string == "execute" {
                                let fresh = try await connection.hardwareManifest(camera: camera)
                                guard fresh["privacy"].string == "off" else { throw APIProblem(message: "设备隐私开启或无法读取") }
                                try await connection.prepareAssistantCamera(session.deviceID, client: client)
                                _ = try await client.hardware("executors/\(session.id)/observe", body: .object([
                                    "operationId": op["id"], "leaseToken": op["leaseToken"]]), executor: session)
                                self.active[key] = nil
                                return
                            } else {
                                result = try await connection.executeHardware(camera: camera, command: command)
                            }
                        } catch {
                            result = .object(["status": .string("unknown"), "sdkUsed": .bool(false), "error": .object([
                                "code": .string("DISPATCH_UNKNOWN"), "message": .string("设备回执未确认，请检查前台连接并核对设备")])])
                        }
                        guard epoch == self.generation, !Task.isCancelled else { self.active[key] = nil; return }
                        var body = result.object
                        body["operationId"] = op["id"]; body["leaseToken"] = op["leaseToken"]
                        body["command"] = command["command"]; body["simulated"] = .bool(false)
                        self.pending[camera.sn, default: [:]][key] = .object(body)
                        self.active[key] = nil
                        self.message = "设备回执已就绪，等待同步；物理效果仍需核对"
                    }
                } catch {
                    if Task.isCancelled { break }
                    message = error.localizedDescription
                    if let problem = error as? APIProblem, problem.statusCode == 403 {
                        sessions[camera.sn] = nil; pending[camera.sn] = nil; released.insert(camera.sn)
                    }
                }
            }
            do { try await Task.sleep(for: .milliseconds(700)) } catch { break }
        }
        if epoch == generation { await shutdown() }
    }

    func shutdown() async {
        invalidate()
        await cleanup?.value
    }
    func invalidate() {
        generation = UUID()
        let old = sessions, endpoints = clients, tasks = active, previous = cleanup
        sessions = [:]; clients = [:]; pending = [:]; active = [:]
        tasks.values.forEach { $0.cancel() }
        cleanup = Task {
            await previous?.value
            for (sn, session) in old {
                _ = try? await endpoints[sn]?.hardware("executors/\(session.id)/disconnect", body: .object([:]), executor: session)
            }
            // Drain bounded native calls before the official workspace takes the SDK.
            for task in tasks.values { await task.value }
        }
    }
}

struct HardwareExecutorWorker: View {
    @ObservedObject var connection: OfficialSDKConnection
    let client: APIClient
    let active: Bool
    private var scopeKey: String {
        let credentialHash = SHA256.hash(data: Data(client.accessToken.utf8)).map { String(format: "%02x", $0) }.joined()
        return "\(active):\(client.baseURL):\(credentialHash):\(connection.devices.map(\.sn).joined(separator: ","))"
    }
    var body: some View {
        Color.clear.frame(width:0,height:0).task(id: scopeKey) {
            if active && connection.canDiscover { await connection.toolExecutor.run(connection:connection,client:client.scoped()) }
            else { await connection.toolExecutor.shutdown() }
        }
    }
}

struct HardwareOperationCard: View {
    @EnvironmentObject private var store: AppStore
    let operation: HardwareValue
    @State private var current: HardwareValue?
    @State private var references: [HardwareValue] = []
    @State private var error: String?
    @State private var reviewNote = ""
    private var value: HardwareValue { current ?? operation }
    var body: some View {
        VStack(alignment:.leading,spacing:10) {
            Text(ChatPresentation.action(value["tool"].string)).font(.headline)
            Text(ChatPresentation.operationDetails(value, deviceName: store.camera(value["deviceId"].string)?.name, references: references)).font(.subheadline)
            Text(ChatPresentation.operationStatus(value)).font(.caption).accessibilityIdentifier("chat.operation.status")
            if value["executionState"].string == "awaitingApproval" {
                HStack {
                    Button("确认这次操作") { decide("approve") }.buttonStyle(.borderedProminent)
                    Button("拒绝") { decide("reject") }.buttonStyle(.bordered)
                }
            }
            if ["queued","executing","verifying","unknown"].contains(value["executionState"].string) {
                Button("取消 / 请求停止") { Task { do {
                    current=try await store.client.hardware("call",body:.object(["name":.string("camera_stop"),"arguments":.object(["operationId":value["id"]]),"idempotencyKey":.string(UUID().uuidString),"platform":.string("ios"),"taskId":value["taskId"]]))
                } catch { self.error=error.localizedDescription } } }
            }
            if !value["error"]["message"].string.isEmpty { Text(ChatPresentation.error(value["error"]["message"].string)).font(.caption) }
            if value["executionState"].string == "unknown", value["leaseReleasedByHuman"].string.isEmpty {
                TextField("人工核对记录（至少 10 字）", text: $reviewNote)
                Button("已核对设备，解除操作占用") { Task { do {
                    current = try await store.client.hardware("reconcile", body: .object([
                        "operationId": value["id"], "requestHash": value["requestHash"],
                        "decision": .string("release_after_manual_check"), "evidence": .string(reviewNote)]))
                } catch { self.error = error.localizedDescription } } }.disabled(reviewNote.count < 10)
            }
            if let error { Text(ChatPresentation.error(error)).font(.caption).foregroundStyle(.red) }
        }.padding(16).background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius:16))
        .task(id:operation["id"].string) {
            while !Task.isCancelled {
                if let snapshot=try? await store.client.hardware("snapshot"), let updated=snapshot["operations"].array.first(where:{$0["id"]==operation["id"]}) {
                    references = snapshot["operations"].array.flatMap { $0["result"]["references"].array }
                    current=updated
                    if ["completed","failed","cancelled"].contains(updated["executionState"].string) || !updated["leaseReleasedByHuman"].string.isEmpty { break }
                }
                do { try await Task.sleep(for:.seconds(2)) } catch { break }
            }
        }
    }
    private func decide(_ decision:String) { Task { do {
        current=try await store.client.hardware("confirmations",body:.object(["operationId":value["id"],"requestHash":value["requestHash"],"decision":.string(decision)]))
    } catch { self.error=error.localizedDescription } } }
}

struct HardwareToolsView: View {
    @EnvironmentObject private var store: AppStore
    let deviceID: String
    @State private var snapshot: HardwareValue = .null
    @State private var selected="camera_observe"
    @State private var arguments="{}"
    @State private var diagnostic=false
    @State private var note=""
    @State private var error: String?
    private var device: HardwareValue { snapshot["devices"].array.first(where:{$0["id"].string==deviceID}) ?? .null }
    var body: some View {
        Form {
            Section("设备工具检查") {
                Text("执行端：\(device["executorPlatform"].string) · \(device["executorOnline"].boolean ? "前台在线" : "等待执行器")")
                Text("只显示已接入的路线。首次真机检查使用诊断模式；验证通过后才开放给 Agent。").font(.caption)
                Picker("工具",selection:$selected) {
                    ForEach(device["routes"].object.keys.sorted(),id:\.self) { name in Text(name).tag(name) }
                }.onChange(of:selected) { _,_ in fillArguments() }
                Toggle("人工诊断（仍需逐次确认控制）",isOn:$diagnostic)
                TextEditor(text:$arguments).font(.caption.monospaced()).frame(minHeight:130)
                Button("提交请求") { Task { do {
                    _ = try await store.client.hardware("call",body:.object(["name":.string(selected),"arguments":try HardwareValue.parse(arguments),"idempotencyKey":.string(UUID().uuidString),"platform":.string("ios"),"diagnostic":.bool(diagnostic)]))
                    await refresh()
                } catch { self.error=error.localizedDescription } } }
                    .disabled(!device["executorOnline"].boolean || !device["routes"][selected]["ready"].boolean)
                TextField("真机检查记录（至少 10 字）",text:$note)
                Button("记录此工具真机通过") { Task { do {
                    _ = try await store.client.hardware("validations",body:.object(["deviceId":.string(deviceID),"tool":.string(selected),"capabilityRevision":device["capabilityRevision"],"status":.string("passed"),"evidence":.string(note)]))
                    await refresh()
                } catch { self.error=error.localizedDescription } } }.disabled(note.count<10)
                Button("记录此工具未通过") { Task { do {
                    _ = try await store.client.hardware("validations", body: .object(["deviceId":.string(deviceID),"tool":.string(selected),"capabilityRevision":device["capabilityRevision"],"status":.string("failed"),"evidence":.string(note)]))
                    await refresh()
                } catch { self.error=error.localizedDescription } } }.disabled(note.count<10)
                Button("已停止直播，释放执行端") { Task { do {
                    _ = try await store.client.hardware("devices/\(deviceID)/release", body: .object([:]))
                    await refresh()
                } catch { self.error=error.localizedDescription } } }
                if let error { Text(error).foregroundStyle(.red) }
            }
            Section("操作回执") {
                ForEach(Array(snapshot["operations"].array.filter { $0["deviceId"].string == deviceID }.enumerated()), id: \.offset) { item in HardwareOperationCard(operation: item.element) }
            }
        }.navigationTitle("硬件工具").task { await refresh(); fillArguments() }.refreshable { await refresh() }
    }
    private func refresh() async { do { snapshot=try await store.client.hardware("snapshot") } catch { self.error=error.localizedDescription } }
    private func fillArguments() {
        var args:[String:HardwareValue]=["deviceId":.string(deviceID)]
        if selected == "camera_observe" { args["freshness"] = .number(60) }
        if selected=="camera_ptz_step" {
            let ref=snapshot["operations"].array.filter{$0["deviceId"].string==deviceID}.flatMap{$0["result"]["references"].array}.first{$0["kind"].string=="observation"}
            args["direction"] = .string("LEFT"); args["expectedViewRevision"]=device["viewRevision"]; args["referenceObservationId"]=ref?["id"] ?? .string("")
        }
        arguments=HardwareValue.object(args).json
    }
}
