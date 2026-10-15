import Foundation

/// Lossy diagnostics use their own session, never the business/media transport.
actor OpsDelivery {
    static let shared = OpsDelivery()
    private let session: URLSession
    private var pending = 0

    static func configuration() -> URLSessionConfiguration {
        let config = URLSessionConfiguration.ephemeral
        config.httpMaximumConnectionsPerHost = 1
        config.timeoutIntervalForRequest = 2.5
        config.timeoutIntervalForResource = 3
        config.waitsForConnectivity = false
        config.urlCache = nil
        config.httpCookieStorage = nil
        config.urlCredentialStorage = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return config
    }

    init(session: URLSession = URLSession(configuration: OpsDelivery.configuration())) {
        self.session = session
    }

    func send(_ request: URLRequest) async {
        // At most two in flight; excess diagnostics are dropped, never queued
        // behind a stalled endpoint or retried alongside camera heartbeats.
        guard pending < 2 else { return }
        pending += 1
        defer { pending -= 1 }
        _ = try? await session.data(for: request)
    }
}
