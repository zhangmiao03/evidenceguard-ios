import Combine
import Foundation

private func snapshot(_ preferences: PersonalPreferences, revision: Int = 1) -> PersonalSnapshot {
    PersonalSnapshot(preferences: preferences, revision: revision, memories: [], inbox: [], delivery: "in_app", lastError: nil)
}

actor TestBackend {
    var values = PersonalPreferences()
    var history: [PersonalPreferences] = []
    var concurrent = 0
    var maximumConcurrent = 0
    var failNext = false
    func read() -> PersonalSnapshot { snapshot(values) }
    func failOnce() { failNext = true }
    func save(_ value: PersonalPreferences) async throws -> PersonalSnapshot {
        history.append(value); concurrent += 1; maximumConcurrent = max(maximumConcurrent, concurrent)
        defer { concurrent -= 1 }
        try await Task.sleep(for: .milliseconds(120))
        if failNext { failNext = false; throw URLError(.notConnectedToInternet) }
        values = value
        return snapshot(value)
    }
    func calls() -> Int { history.count }
    func result() -> (PersonalPreferences, [PersonalPreferences], Int) { (values, history, maximumConcurrent) }
}

struct APIClient {
    var baseURL: URL
    var backend: TestBackend
    func personalSettings() async throws -> PersonalSnapshot { await backend.read() }
    func savePreferences(_ values: PersonalPreferences) async throws -> PersonalSnapshot { try await backend.save(values) }
}

@MainActor final class AppStore {
    var client: APIClient
    var data = DataSnapshot()
    struct DataSnapshot { var personal: PersonalSnapshot? }
    init(_ backend: TestBackend, origin: String = "https://one.example.test") {
        client = APIClient(baseURL: URL(string: origin)!, backend: backend)
    }
}

@main struct ReminderSettingsTests {
    @MainActor static func wait(_ predicate: () async -> Bool) async {
        for _ in 0..<300 {
            if await predicate() { return }
            try? await Task.sleep(for: .milliseconds(10))
        }
        fatalError("Timed out waiting for preference save")
    }
    @MainActor static func main() async {
        let backend = TestBackend(), store = AppStore(TestBackend())
        store.client.backend = backend
        let settings = ReminderSettings()
        await settings.load(store)
        settings.update(\.enabled, to: true)
        settings.update(\.summaryHour, to: 19)
        await wait { await backend.calls() == 1 }
        settings.update(\.enabled, to: false)
        settings.update(\.summaryHour, to: 20)
        await wait { !settings.saving }
        let result = await backend.result()
        precondition(result.0.enabled == false && result.0.summaryHour == 20)
        precondition(result.1.count == 2 && result.2 == 1, "Preference writes must be serial")
        precondition(store.data.personal?.preferences == result.0)
        print("PASS: rapid edits and in-flight changes persist the latest values serially")

        await backend.failOnce()
        settings.update(\.dailySummary, to: true)
        await wait { !settings.saving }
        precondition(settings.error != nil && settings.hasPendingChanges)
        await settings.load(store) // Returning to the page must retain unsaved choices.
        precondition(settings.preferences.dailySummary)
        settings.retry()
        await wait { !settings.saving }
        precondition(settings.error == nil && !settings.hasPendingChanges)
        let retried = await backend.result()
        precondition(retried.0.dailySummary)
        print("PASS: a failed save retains choices across navigation and retries")

        let oldCalls = await backend.calls()
        settings.update(\.summaryHour, to: 21)
        await wait { await backend.calls() == oldCalls + 1 }
        let other = TestBackend()
        store.client = APIClient(baseURL: URL(string: "https://two.example.test")!, backend: other)
        await settings.load(store)
        settings.update(\.quietStart, to: 23)
        await wait { !settings.saving }
        precondition(store.data.personal?.preferences.quietStart == 23)
        precondition(store.data.personal?.preferences.summaryHour == 18)
        let otherResult = await other.result()
        precondition(otherResult.1.count == 1)
        print("PASS: late responses cannot overwrite another service's preferences")
    }
}
