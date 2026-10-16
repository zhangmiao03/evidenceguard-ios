import Foundation

@main struct AssistantStoreChecks {
    @MainActor static func main() async throws {
        let defaults = UserDefaults.standard
        defaults.set("main", forKey: "conversationID")
        defaults.set(APIClient.defaultBaseURL.absoluteString, forKey: "serviceURL")
        defaults.set("topic-saved", forKey: "activeChat:" + APIClient.defaultBaseURL.absoluteString)
        let store = AppStore()
        precondition(store.activeConversationID == "main")
        store.conversationDrafts = ["main": "主对话草稿", "main-history": "历史草稿", "topic-saved": "独立话题草稿"]
        store.pendingChatRequests["topic-saved"] = PendingChatRequest(id: "retry-stable", message: "独立话题草稿", conversation: "topic-saved", skill: nil, camera: nil, mode: "live", filter: nil, replyID: nil)
        let savedDrafts = store.conversationDrafts
        store.tabPaths[AppTab.profile.rawValue] = [.settings]
        store.selectConversation("topic-saved")
        precondition(store.tabPaths[0] == [.conversation("topic-saved", nil)])
        let message = try JSONDecoder().decode(AssistantMessage.self, from: Data(#"{"id":"old-message","title":"旧消息","body":"已保存的旧观察","why":"待核实","createdAt":1,"read":false,"sources":[]}"#.utf8))
        APIClient.lookup = { _ in message }
        APIClient.snapshot.personal = try JSONDecoder().decode(PersonalSnapshot.self, from: Data(#"{"preferences":{},"revision":1,"memories":[],"inbox":[],"delivery":"in_app","messages":[]}"#.utf8))
        try await store.openAssistantMessage(message.id)
        precondition(store.selectedTab == .assistant && store.tabPaths[0].isEmpty)
        precondition(store.assistantMessageFocus == message.id && store.assistantMessages.count == 1)
        precondition(store.tabPaths[AppTab.profile.rawValue] == [.settings])
        precondition(store.conversationDrafts == savedDrafts && store.pendingChatRequests["topic-saved"]?.id == "retry-stable")
        try await store.feedbackAssistantMessage(message.id, action: "handled")
        precondition(store.assistantMessages[0].read && store.assistantMessages[0].feedback == "handled")
        // A regular bootstrap containing the same ID must update, not duplicate it.
        store.data.personal = APIClient.snapshot.personal
        var merged = message; merged.body = "更新后的同一消息"
        store.data.personal?.messages = [merged]
        precondition(store.assistantMessages.count == 1 && store.assistantMessages[0].body == merged.body)

        // An old service's delayed message fetch cannot navigate or contaminate a new service.
        let delayed = AppStore()
        let (started, continuation) = AsyncStream<Void>.makeStream()
        var response: CheckedContinuation<AssistantMessage, Never>?
        APIClient.lookup = { _ in
            await withCheckedContinuation { response = $0; continuation.yield(()) }
        }
        let open = Task { try await delayed.openAssistantMessage("pending") }
        for await _ in started { break }
        delayed.client = APIClient(baseURL: URL(string: "https://store-b.invalid")!)
        response!.resume(returning: message)
        try await open.value
        precondition(delayed.assistantMessageFocus == nil && delayed.assistantMessages.isEmpty)

        let (refreshStarted, refreshContinuation) = AsyncStream<Void>.makeStream()
        var bootstrapResponse: CheckedContinuation<Bootstrap, Never>?
        APIClient.bootstrapLookup = {
            await withCheckedContinuation { bootstrapResponse = $0; refreshContinuation.yield(()) }
        }
        let refresh = Task { await delayed.refresh() }
        for await _ in refreshStarted { break }
        delayed.client = APIClient(baseURL: URL(string: "https://store-c.invalid")!)
        bootstrapResponse!.resume(returning: APIClient.snapshot)
        await refresh.value
        precondition(delayed.data.personal == nil && !delayed.isConnected)
        print("PASS: main-chat navigation, old-message focus/feedback and drafts; stale message/bootstrap responses cannot cross service boundaries")
    }
}
