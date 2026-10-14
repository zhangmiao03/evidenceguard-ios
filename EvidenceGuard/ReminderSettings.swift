import Combine
import Foundation

// One serial save queue per AppStore. Navigation and bootstrap polling must not
// discard edited values or let an older request overwrite the latest choice.
@MainActor final class ReminderSettings: ObservableObject {
    @Published private(set) var preferences = PersonalPreferences()
    @Published private(set) var loaded = false
    @Published private(set) var loading = false
    @Published private(set) var saving = false
    @Published private(set) var savedOnce = false
    @Published private(set) var error: String?
    private var saved: PersonalPreferences?
    private var client: APIClient?
    private weak var store: AppStore?
    private var generation = UUID()
    var hasPendingChanges: Bool { loaded && preferences != saved }

    func load(_ store: AppStore) async {
        let source = store.client
        self.store = store
        if client?.baseURL != source.baseURL {
            generation = UUID(); client = source; saved = nil
            preferences = PersonalPreferences(); loaded = false; loading = false
            saving = false; savedOnce = false; error = nil
        }
        guard !loading, !saving, !hasPendingChanges else { return }
        let current = generation
        loading = true; error = nil
        defer { if generation == current { loading = false } }
        do {
            let snapshot = try await source.personalSettings()
            guard generation == current, store.client.baseURL == source.baseURL else { return }
            saved = snapshot.preferences; preferences = snapshot.preferences
            loaded = true; savedOnce = snapshot.revision > 0
            store.data.personal = snapshot
        } catch {
            guard generation == current else { return }
            self.error = "暂时无法读取提醒设置，请检查网络后重试。"
        }
    }

    func update<Value>(_ key: WritableKeyPath<PersonalPreferences, Value>, to value: Value) {
        guard loaded, !loading else { return }
        preferences[keyPath: key] = value
        preferences.timezone = TimeZone.current.identifier
        retry()
    }

    func retry() {
        guard loaded, hasPendingChanges, !saving, let source = client,
              store?.client.baseURL == source.baseURL else { return }
        let current = generation
        saving = true; error = nil
        Task {
            // Coalesce quick stepper/toggle edits. Requests remain serial even
            // when another edit arrives while the previous request is in flight.
            try? await Task.sleep(for: .milliseconds(300))
            while generation == current && hasPendingChanges {
                let values = preferences
                do {
                    let snapshot = try await source.savePreferences(values)
                    guard generation == current else { return }
                    saved = values; savedOnce = true
                    if store?.client.baseURL == source.baseURL { store?.data.personal = snapshot }
                } catch {
                    guard generation == current else { return }
                    self.error = "更改尚未保存，请检查网络后重试。"
                    break
                }
            }
            if generation == current { saving = false }
        }
    }
}
