import Foundation

/// The internal build is a preconfigured client of an isolated demo service.
/// Its bundled credential is demo-scoped and extractable; it is never a model key.
struct MobileServiceConfiguration {
    static let installationID: String = {
        let defaults = UserDefaults.standard
        if let raw = defaults.string(forKey: "installationID"), UUID(uuidString: raw) != nil { return raw }
        let value = UUID().uuidString.lowercased(); defaults.set(value, forKey: "installationID"); return value
    }()
    let values: [String: Any]
    static var current: Self { .init(values: Bundle.main.infoDictionary ?? [:]) }
    var isInternalDemo: Bool { (values["EGInternalDemo"] as? String) == "YES" }
    var origin: URL? {
        guard let raw = values["EGServiceBaseURL"] as? String,
              let url = URL(string: raw), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              ["", "/"].contains(url.path) else { return nil }
        return url
    }
    /// Build 4 stored drafts and the selected conversation under the Oregon origin.
    /// Copy them once when the internal app moves to its new bundled service.
    /// Credentials stay origin-scoped, and the installation identity is unchanged.
    func migrateLegacyChatState(in defaults: UserDefaults) {
        let legacy = "https://demo.34.218.51.85.sslip.io"
        guard isInternalDemo, let origin, origin.absoluteString != legacy else { return }
        let marker = "chatOriginMigration:" + origin.absoluteString
        guard !defaults.bool(forKey: marker) else { return }
        for prefix in ["localChats:", "activeChat:"] {
            let destination = prefix + origin.absoluteString
            if defaults.object(forKey: destination) == nil,
               let saved = defaults.object(forKey: prefix + legacy) {
                defaults.set(saved, forKey: destination)
            }
        }
        defaults.set(true, forKey: marker)
    }
    func demoToken(for url: URL) -> String? {
        guard isInternalDemo, let origin, Self.sameOrigin(origin, url),
              let token = values["EGDemoAccessToken"] as? String,
              token.count >= 32, token.utf8.allSatisfy({ (33...126).contains($0) }),
              !token.contains("$(") else { return nil }
        return token
    }
    static func sameOrigin(_ lhs: URL, _ rhs: URL) -> Bool {
        lhs.scheme?.lowercased() == rhs.scheme?.lowercased() &&
        lhs.host?.lowercased() == rhs.host?.lowercased() &&
        (lhs.port ?? (lhs.scheme == "https" ? 443 : 80)) == (rhs.port ?? (rhs.scheme == "https" ? 443 : 80)) &&
        rhs.user == nil && rhs.password == nil
    }
}
