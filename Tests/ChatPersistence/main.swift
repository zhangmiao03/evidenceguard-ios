import Foundation

let defaults = UserDefaults(suiteName: "EvidenceGuardChatStateTest-" + UUID().uuidString)!
let pending = PendingChatRequest(id: "run-stable", message: "包裹在哪里？", conversation: "topic-1-history", skill: nil, camera: nil, mode: "history", filter: nil, replyID: nil)
let state = LocalChatState(drafts: [pending.conversation: pending.message, "topic-2": "另一段未发文字"], pending: [pending.conversation: pending], modes: ["topic-1": "history"], newConversationRequestID: "create-stable")
defaults.set(try JSONEncoder().encode(state), forKey: "server-A")
let restored = try JSONDecoder().decode(LocalChatState.self, from: defaults.data(forKey: "server-A")!)
precondition(restored.pending[pending.conversation]?.id == "run-stable")
precondition(restored.drafts["topic-2"] == "另一段未发文字")
precondition(restored.newConversationRequestID == "create-stable")
precondition(restored.pending[pending.conversation]!.matches(message: pending.message, camera: nil, mode: "history", filter: nil, replyID: nil))
precondition(!restored.pending[pending.conversation]!.matches(message: "修改后的问题", camera: nil, mode: "history", filter: nil, replyID: nil))
precondition(!restored.pending[pending.conversation]!.matches(message: pending.message, camera: "cam-b", mode: "history", filter: nil, replyID: nil))
precondition(defaults.data(forKey: "server-B") == nil)
print("PASS: drafts and request IDs survive persistence; edits and server namespaces remain separate")
