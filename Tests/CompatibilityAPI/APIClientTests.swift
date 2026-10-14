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
        APIClient(baseURL: origin, transport: session(), observations: OpsDelivery(session: session(observations: true)))
    }
    override func tearDown() {
        transports.forEach { $0.invalidateAndCancel() }
        transports.removeAll()
        super.tearDown()
    }

    func testLegacyCaptureFlowCompletesWhileObservationsAreStalled() async {
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
        let flow = Task {
            do {
                let live = try await api.startMedia("sdk-test", traceID: "start-trace")
                XCTAssertNil(live.traceId)
                await fulfillment(of: [blocked], timeout: 2)
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

    func testUnavailableCollectorDoesNotReplaceBusinessErrors() async throws {
        let diagnostics = Requests()
        let observed = expectation(description: "collector failures ignored")
        observed.expectedFulfillmentCount = 4
        StubProtocol.install { item in
            if item.request.url!.path == "/api/ops/client-events" {
                let n = diagnostics.append(item.request)
                if n == 1 { item.reply("{}", status: 404) }
                else if n == 2 { item.reply("{}", status: 503) }
                else if n == 3 { item.fail(.timedOut) }
                else { item.fail(.notConnectedToInternet) }
                observed.fulfill()
            } else if item.request.url!.path.hasSuffix("/frames") {
                item.reply(#"{"detail":"采集会话已停止"}"#, status: 409)
            } else if item.request.url!.path.hasSuffix("/stop") {
                item.reply("not-json")
            } else {
                item.reply(#"{"id":"live-test","deviceId":"sdk-test","token":"synthetic"}"#)
            }
        }
        let api = client()
        let live = try await api.startMedia("sdk-test")
        // Let each immediate failed observation release its slot; no retry is expected.
        try await Task.sleep(for: .milliseconds(100))
        do {
            try await api.uploadLiveFrame(live, body: LiveFrameUpload(requestId: "capture-test", sequence: 2,
                imageBase64: "synthetic-frame", width: 32, height: 24, sampledAt: 1))
            XCTFail("Expected original 409")
        } catch let error as APIProblem {
            XCTAssertEqual(error.statusCode, 409)
            XCTAssertEqual(error.message, "采集会话已停止")
        }
        try await Task.sleep(for: .milliseconds(100))
        do { try await api.stopMedia(live); XCTFail("Expected original decoding error") }
        catch let error as APIProblem { XCTAssertEqual(error.message, "当前版本无法读取服务返回的数据，请更新测试版本。") }
        try await Task.sleep(for: .milliseconds(100))
        let another = try await api.startMedia("sdk-test")
        XCTAssertEqual(another.deviceId, "sdk-test")
        await fulfillment(of: [observed], timeout: 2)
        try await Task.sleep(for: .milliseconds(100))
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
