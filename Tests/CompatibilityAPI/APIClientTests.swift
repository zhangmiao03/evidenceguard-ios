import XCTest
@testable import EvidenceGuard

// Exercise the real APIClient with native URLSession transports, without vendor
// binaries or a network server. These tests cannot certify real camera playback.
private final class StubProtocol: URLProtocol {
    private static let lock = NSLock()
    private static var callback: ((StubProtocol) -> Void)?
    static func install(_ handler: @escaping (StubProtocol) -> Void) {
        lock.lock(); callback = handler; lock.unlock()
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock(); let handler = Self.callback; Self.lock.unlock()
        handler?(self)
    }
    override func stopLoading() {}
    func reply(_ json: String, status: Int = 200) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
            httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    func fail(_ code: URLError.Code) { client?.urlProtocol(self, didFailWithError: URLError(code)) }
}

private final class Requests {
    private let lock = NSLock()
    private var values: [URLRequest] = []
    private var held: [StubProtocol] = []
    @discardableResult func append(_ request: URLRequest) -> Int {
        lock.lock(); defer { lock.unlock() }
        values.append(request); return values.count
    }
    func hold(_ item: StubProtocol) { lock.lock(); held.append(item); lock.unlock() }
    func release() {
        lock.lock(); let items = held; held.removeAll(); lock.unlock()
        items.forEach { $0.fail(.timedOut) }
    }
    var all: [URLRequest] { lock.lock(); defer { lock.unlock() }; return values }
}

final class APIClientTests: XCTestCase {
    private var transports: [URLSession] = []
    private let origin = URL(string: "https://eg-api-tests.invalid")!

    private func session(observations: Bool = false) -> URLSession {
        let config = observations ? OpsDelivery.configuration() : URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let value = URLSession(configuration: config)
        transports.append(value)
        return value
    }
    private func client() -> APIClient {
        APIClient(baseURL: origin, transport: session(), observations: OpsDelivery(session: session(observations: true)), installationProof: { _ in "synthetic-installation-proof" })
    }

    func testEventRecordingUploadKeepsDeviceScopeAndUnknownFileStart() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".mp4")
        try Data("synthetic API transport fixture".utf8).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        StubProtocol.install { item in
            XCTAssertEqual(item.request.httpMethod, "POST")
            XCTAssertEqual(item.request.url!.path, "/api/recordings")
            let query = URLComponents(url: item.request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertEqual(query.first { $0.name == "cameraId" }?.value, "sdk-camera-test")
            XCTAssertEqual(query.first { $0.name == "title" }?.value, "设备事件录像 · 测试")
            XCTAssertFalse(query.contains { $0.name == "recordedAt" }, "Event time is not automatically file start time")
            XCTAssertEqual(item.request.value(forHTTPHeaderField: "Content-Type"), "application/octet-stream")
            XCTAssertEqual(item.request.value(forHTTPHeaderField: "X-EG-Private-Key"), "synthetic-installation-proof")
            item.reply(#"{"id":"video-test","cameraId":"sdk-camera-test","title":"设备事件录像 · 测试","sourceType":"uploaded","status":"queued","segmentCount":0,"playbackUrl":"/api/recordings/video-test/video"}"#, status: 202)
        }
        let result = try await client().uploadRecording(file, camera: "sdk-camera-test", recordedAt: nil, title: "设备事件录像 · 测试")
        XCTAssertEqual(result.status, "queued")
        XCTAssertNil(result.recordedAt)
    }

    func testEvidenceSearchImageRejectsAnotherOriginBeforeTransport() async {
        StubProtocol.install { _ in XCTFail("Cross-origin evidence must not receive credentials") }
        do { _ = try await client().videoSearchImage("https://other-origin.invalid/evidence.jpg"); XCTFail("Expected rejection") }
        catch {}
    }

    func testLatestGuardVersionAndHistoryReferenceTravelTogether() async throws {
        StubProtocol.install { item in
            if item.request.url!.path.hasPrefix("/api/ops/") { item.reply("{}"); return }
            var bytes = item.request.httpBody ?? Data()
            if bytes.isEmpty, let stream = item.request.httpBodyStream {
                stream.open(); defer { stream.close() }
                var buffer = [UInt8](repeating: 0, count: 4096)
                while true {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }
                    bytes.append(contentsOf: buffer.prefix(count))
                }
            }
            guard let body = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any] else {
                XCTFail("Expected a JSON Agent request"); item.reply("{}", status: 400); return
            }
            XCTAssertEqual(item.request.url!.path, "/api/agent/runs")
            XCTAssertEqual(body["clientPlatform"] as? String, "ios")
            XCTAssertEqual(body["guardFlowVersion"] as? Int, 1)
            if body["executionMode"] as? String == "history" {
                XCTAssertEqual(body["referenceImageId"] as? String, "query-image-11111111111111111111111111111111")
                XCTAssertEqual((body["historyFilter"] as? [String: Any])?["period"] as? String, "all")
                item.reply(#"{"id":"history-run","conversationId":"history","message":"找这个物体","status":"completed","createdAt":1,"toolReceipts":[],"executionMode":"history","referenceImageId":"query-image-11111111111111111111111111111111"}"#)
            } else {
                XCTAssertNil(body["referenceImageId"])
                item.reply(#"{"id":"live-run","conversationId":"live","message":"帮我看着包裹","status":"completed","createdAt":1,"toolReceipts":[],"guardDraftId":"scene-test"}"#)
            }
        }
        let api = client()
        let history = try await api.start(message: "找这个物体", conversation: "history", skill: nil,
            camera: nil, requestID: "history-run", executionMode: "history", historyFilter: HistoryFilter(period: "all"),
            referenceImageID: "query-image-11111111111111111111111111111111")
        XCTAssertNotNil(history.referenceImageId)
        XCTAssertNil(history.guardDraftId)
        let live = try await api.start(message: "帮我看着包裹", conversation: "live", skill: nil,
            camera: "sdk-test", requestID: "live-run")
        XCTAssertEqual(live.guardDraftId, "scene-test")
        XCTAssertNil(live.referenceImageId)
    }

    func testHardwareEnvelopeUsesBoundExecutorAndKeepsJSONTypes() async throws {
        let requests = Requests()
        StubProtocol.install { item in
            if item.request.url!.path.hasPrefix("/api/ops/") { item.reply("{}"); return }
            requests.append(item.request)
            item.reply(#"{"command":"execute","operation":{"id":"op-test","simulated":false,"arguments":{"value":true,"expectedSettingsRevision":3},"nullable":null}}"#)
        }
        let session = HardwareExecutorSession(id: "executor-test", token: "synthetic-executor-token", deviceID: "sdk-test")
        let response = try await client().hardware("executors/executor-test/claim", body: .object([:]), executor: session)
        XCTAssertEqual(response["command"], .string("execute"))
        XCTAssertEqual(response["operation"]["arguments"]["value"], .bool(true))
        XCTAssertEqual(response["operation"]["arguments"]["expectedSettingsRevision"], .number(3))
        XCTAssertEqual(response["operation"]["nullable"], .null)
        XCTAssertEqual(requests.all.first?.value(forHTTPHeaderField: "X-EG-Executor-Token"), "synthetic-executor-token")
        XCTAssertEqual(requests.all.first?.httpMethod, "POST")
        XCTAssertEqual(requests.all.first?.value(forHTTPHeaderField: "X-EG-Private-Key"), "synthetic-installation-proof")
        XCTAssertEqual(try HardwareValue.parse(response.json), response)
        XCTAssertEqual(IOSToolExecutor.deviceID("T8171TESTTOOLS1"), "sdk-e41d9c3701a5f085f9ea")
    }

    func testEndpointAnalysisDecodesUnknownAndPreservesPrivateHeaders() async throws {
        let requests = Requests()
        StubProtocol.install { item in
            if item.request.url!.path.hasPrefix("/api/ops/") { item.reply("{}"); return }
            requests.append(item.request)
            XCTAssertEqual(item.request.url!.path, "/api/visual-scenes/scene-test/analyze")
            XCTAssertEqual(item.request.timeoutInterval, 90)
            item.reply(#"{"status":"unknown","code":"NEEDS_SECOND_FRAME","reason":"只有一张画面","readOnly":true,"controlEligible":false,"limitation":"只读分析"}"#)
        }
        // Decode a legacy response: optional new fields must not break older services.
        let body = #"{"id":"scene-test","cameraId":"sdk-test","prompt":"看住包裹","revision":2,"status":"active","stage":"review","question":"","unsupportedReason":"","reason":"等待采样","summary":"包裹看护","limitation":"前台观察","canActivate":false,"observation":{"state":"unknown","reason":"等待采样"},"evidenceIds":[]}"#
        let scene = try JSONDecoder().decode(VisualScene.self, from: Data(body.utf8))
        XCTAssertNil(scene.endpointVision)
        let result = try await client().analyzeScene(scene)
        XCTAssertEqual(result.status, "unknown")
        XCTAssertNil(result.analysis)
        XCTAssertNil(result.sources)
        XCTAssertEqual(result.reason, "只有一张画面")
        XCTAssertEqual(requests.all.first?.httpMethod, "POST")
        XCTAssertEqual(requests.all.first?.value(forHTTPHeaderField: "X-EG-Private-Key"), "synthetic-installation-proof")
    }

    func testUnavailableInstallationProofDoesNotSendRequest() async throws {
        let requests = Requests()
        StubProtocol.install { item in requests.append(item.request); item.reply("{}") }
        let api = APIClient(baseURL: origin, transport: session(), installationProof: { _ in
            throw APIProblem(message: "Synthetic keychain unavailable")
        })
        do {
            _ = try await api.hardware("executors/executor-test/claim", body: .object([:]),
                executor: HardwareExecutorSession(id: "executor-test", token: "synthetic-executor-token", deviceID: "sdk-test"))
            XCTFail("Expected credential failure")
        } catch let error as APIProblem {
            XCTAssertEqual(error.message, "Synthetic keychain unavailable")
        }
        XCTAssertTrue(requests.all.isEmpty)
    }

    override func tearDown() {
        transports.forEach { $0.invalidateAndCancel() }
        transports.removeAll()
        super.tearDown()
    }

    func testLegacyCaptureFlowCompletesWhileObservationsAreStalled() async throws {
        let requests = Requests(), diagnostics = Requests()
        let blocked = expectation(description: "diagnostic endpoint is stalled")
        let completed = expectation(description: "media exchange completes without diagnostic acknowledgement")
        StubProtocol.install { item in
            let path = item.request.url!.path
            if path == "/api/ops/client-events" {
                diagnostics.hold(item)
                if diagnostics.append(item.request) == 1 { blocked.fulfill() }
                return
            }
            requests.append(item.request)
            if path == "/api/media-sessions" {
                // A server predating tracing has no traceId fields.
                item.reply(#"{"id":"live-test","deviceId":"sdk-test","token":"synthetic-media-token"}"#)
            } else if path.hasSuffix("/commands") {
                item.reply(#"[{"requestId":"capture-test","afterSequence":1,"deadline":2000000000}]"#)
            } else { item.reply(#"{"status":"ok"}"#) }
        }
        let api = client()
        let live = try await api.startMedia("sdk-test", traceID: "start-trace")
        XCTAssertNil(live.traceId)
        // XCTest waiters on the same test case must not overlap. First ensure
        // the observation is held, then time only the independent media exchange.
        await fulfillment(of: [blocked], timeout: 2)
        let flow = Task {
            do {
                try await api.liveHeartbeat(live, state: "streaming", sequence: 2, age: 0)
                let command = try await api.liveCommands(live).first!
                XCTAssertNil(command.traceId)
                try await api.uploadLiveFrame(live, body: LiveFrameUpload(requestId: command.requestId, sequence: 3,
                    imageBase64: "synthetic-frame", width: 32, height: 24, sampledAt: 1))
                try await api.stopMedia(live)
            } catch { XCTFail("Original camera exchange failed: \(error)") }
            completed.fulfill()
        }
        await fulfillment(of: [completed], timeout: 3)
        flow.cancel()
        diagnostics.release()
        await flow.value
        let captured = requests.all
        XCTAssertEqual(captured.map { $0.url!.lastPathComponent }, ["media-sessions", "heartbeat", "commands", "frames", "stop"])
        XCTAssertEqual(captured.first?.value(forHTTPHeaderField: "X-EG-Trace-ID"), "start-trace")
        XCTAssertTrue(captured.dropFirst().allSatisfy { $0.value(forHTTPHeaderField: "X-EG-Media-Session") == "synthetic-media-token" })
        XCTAssertEqual(captured.first { $0.url!.lastPathComponent == "frames" }?.value(forHTTPHeaderField: "X-EG-Trace-ID"), "capture-test")
        XCTAssertTrue(diagnostics.all.allSatisfy { $0.value(forHTTPHeaderField: "X-EG-Media-Session") == nil })
    }

    func testDisplayReceiptUsesSeparateTransportAndHashesOnly() async throws {
        let received = expectation(description: "display hashes delivered")
        let diagnostics = Requests()
        StubProtocol.install { item in
            if item.request.url!.path == "/api/ops/display-receipts" {
                diagnostics.append(item.request)
                item.reply("{}", status: 404) // Older servers may not support the optional receipt.
                received.fulfill()
            } else if item.request.url!.path == "/api/ops/client-events" { item.reply("{}") }
            else { item.reply(#"{"id":"live-test","deviceId":"sdk-test","token":"synthetic-media-token"}"#) }
        }
        let api = client()
        api.observeDisplay(runID: "run-test", status: "completed", backendHash: String(repeating: "a", count: 64), displayHash: String(repeating: "b", count: 64))
        await fulfillment(of: [received], timeout: 2)
        let live = try await api.startMedia("sdk-test")
        XCTAssertEqual(live.id, "live-test")
        let request = try XCTUnwrap(diagnostics.all.first)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertNotNil(request.value(forHTTPHeaderField: "X-EG-Installation-ID"))
        XCTAssertNil(request.value(forHTTPHeaderField: "X-EG-Media-Session"))
        var data = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(contentsOf: buffer.prefix(count)) }
        }
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(body["backendTextHash"] as? String, String(repeating: "a", count: 64))
        XCTAssertEqual(body["displayTextHash"] as? String, String(repeating: "b", count: 64))
        XCTAssertEqual(body["presentationVersion"] as? String, ChatPresentation.version)
        XCTAssertNil(body["text"]); XCTAssertNil(body["answer"])
    }

    func testUnavailableCollectorDoesNotReplaceBusinessErrors() async throws {
        let diagnostics = Requests()
        for scenario in 0..<4 {
            let observed = expectation(description: "collector failure \(scenario) ignored")
            StubProtocol.install { item in
                if item.request.url!.path == "/api/ops/client-events" {
                    diagnostics.append(item.request)
                    switch scenario {
                    case 0: item.reply("{}", status: 404)
                    case 1: item.reply("{}", status: 503)
                    case 2: item.fail(.timedOut)
                    default: item.fail(.notConnectedToInternet)
                    }
                    observed.fulfill()
                } else if item.request.url!.path.hasSuffix("/frames") {
                    item.reply(#"{"detail":"采集会话已停止"}"#, status: 409)
                } else if item.request.url!.path.hasSuffix("/stop") {
                    item.reply("not-json")
                } else {
                    item.reply(#"{"id":"live-test","deviceId":"sdk-test","token":"synthetic"}"#)
                }
            }
            // Fresh delivery per failure avoids testing scheduling/overflow here;
            // the separate held-request test verifies the bounded drop policy.
            let api = client(), live = LiveSession(id: "live-test", deviceId: "sdk-test", token: "synthetic", traceId: nil)
            if scenario == 1 {
                do {
                    try await api.uploadLiveFrame(live, body: LiveFrameUpload(requestId: "capture-test", sequence: 2,
                        imageBase64: "synthetic-frame", width: 32, height: 24, sampledAt: 1))
                    XCTFail("Expected original 409")
                } catch let error as APIProblem {
                    XCTAssertEqual(error.statusCode, 409)
                    XCTAssertEqual(error.message, "采集会话已停止")
                }
            } else if scenario == 2 {
                do { try await api.stopMedia(live); XCTFail("Expected original decoding error") }
                catch let error as APIProblem { XCTAssertEqual(error.message, "当前版本无法读取服务返回的数据，请更新测试版本。") }
            } else {
                let another = try await api.startMedia("sdk-test")
                XCTAssertEqual(another.deviceId, "sdk-test")
            }
            await fulfillment(of: [observed], timeout: 2)
        }
        XCTAssertEqual(diagnostics.all.count, 4, "Collector errors must not cause retries")
    }

    func testCancellationRetainsItsOriginalMeaning() async {
        StubProtocol.install { item in item.fail(.cancelled) }
        do { _ = try await client().startMedia("sdk-test"); XCTFail("Expected cancellation") }
        catch is CancellationError {} // Telemetry must not turn cancellation into a business error.
        catch { XCTFail("Wrong error: \(error)") }
    }

    func testHeartbeatsDoNotGenerateAdditionalRequests() async throws {
        let diagnostic = expectation(description: "no heartbeat observations")
        diagnostic.isInverted = true
        StubProtocol.install { item in
            if item.request.url!.path == "/api/ops/client-events" { diagnostic.fulfill() }
            item.reply(#"{"status":"ok"}"#)
        }
        let api = client(), live = LiveSession(id: "live-test", deviceId: "sdk-test", token: "synthetic", traceId: nil)
        for n in 1...4 { try await api.liveHeartbeat(live, state: "streaming", sequence: n, age: 0) }
        await fulfillment(of: [diagnostic], timeout: 0.2)
    }

    func testObservationOverflowDropsAndSlotsRecoverAfterFailure() async {
        let requests = Requests()
        let blocked = expectation(description: "two occupied observation slots")
        blocked.expectedFulfillmentCount = 2
        StubProtocol.install { item in
            requests.append(item.request); requests.hold(item); blocked.fulfill()
        }
        let delivery = OpsDelivery(session: session(observations: true))
        let request = URLRequest(url: origin.appendingPathComponent("api/ops/client-events"))
        let first = Task { await delivery.send(request) }
        let secondRequest = URLRequest(url: URL(string: "https://eg-api-second.invalid/api/ops/client-events")!)
        let second = Task { await delivery.send(secondRequest) }
        await fulfillment(of: [blocked], timeout: 2)
        let dropped = expectation(description: "excess events return without waiting for network")
        let overflow = Task {
            for _ in 0..<20 { await delivery.send(request) }
            dropped.fulfill()
        }
        await fulfillment(of: [dropped], timeout: 1)
        XCTAssertEqual(requests.all.count, 2)
        requests.release()
        await first.value; await second.value; await overflow.value
        StubProtocol.install { item in requests.append(item.request); item.reply("{}", status: 503) }
        await delivery.send(request)
        XCTAssertEqual(requests.all.count, 3, "Failure must release a diagnostic slot")
    }
}
