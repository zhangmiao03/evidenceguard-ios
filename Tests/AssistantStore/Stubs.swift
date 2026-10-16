import Foundation

// Network/SDK boundaries only. The navigation, state persistence and async
// response handling under test are the production AppStore implementation.
final class OfficialSDKConnection {}
enum ServiceAccess { static func save(_ value: String, for url: URL) throws {} }
struct APIProblem: Error { var message: String }
@MainActor struct APIClient {
    static let defaultBaseURL = URL(string: "https://store-a.invalid")!
    var baseURL: URL
    static var snapshot = Bootstrap.empty
    static var lookup: ((String) async throws -> AssistantMessage)!
    static var bootstrapLookup: (() async throws -> Bootstrap)?
    func bootstrap() async throws -> Bootstrap { if let lookup = Self.bootstrapLookup { return try await lookup() }; return Self.snapshot }
    func assistantMessage(_ id: String) async throws -> AssistantMessage { try await Self.lookup(id) }
    func messageFeedback(_ id: String, action: String) async throws -> PersonalSnapshot { Self.snapshot.personal! }
    func personalSettings() async throws -> PersonalSnapshot { Self.snapshot.personal! }
    func savePreferences(_ value: PersonalPreferences) async throws -> PersonalSnapshot { Self.snapshot.personal! }
    func bindPersonalConversation(_ id: String) async throws {}
    func conversations() async throws -> [ConversationSummary] { [] }
    func newConversation(requestID: String) async throws -> ConversationSummary { fatalError("not exercised") }
    func renameConversation(_ id: String, title: String) async throws -> ConversationSummary { fatalError("not exercised") }
    func lifecycle(_ id: String, action: String) async throws {}
    func recheck(_ id: String, acknowledged: Bool) async throws {}
}
