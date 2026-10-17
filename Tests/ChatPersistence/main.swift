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

// Optional cloud additions must decode both older deployments and the merged demo.
let oldPersonal = #"{"preferences":{"enabled":false,"dailySummary":false,"summaryHour":18,"quietStart":22,"quietEnd":8,"timezone":"Asia/Shanghai"},"revision":1,"memories":[],"inbox":[],"delivery":"in_app"}"#
let oldSnapshot = try JSONDecoder().decode(PersonalSnapshot.self, from: Data(oldPersonal.utf8))
precondition(oldSnapshot.automaticMemory == nil)
var newPayload = try JSONSerialization.jsonObject(with: Data(oldPersonal.utf8)) as! [String: Any]
newPayload["automaticMemory"] = ["enabled": true, "pending": 1, "status": "pending", "reason": "等待整理"] as [String: Any]
newPayload["memories"] = [["id": "test-memory", "content": "简洁回复", "source": "conversation", "sourceQuote": "我希望简洁回复", "createdAt": 1]] as [[String: Any]]
let newSnapshot = try JSONDecoder().decode(PersonalSnapshot.self, from: JSONSerialization.data(withJSONObject: newPayload))
precondition(newSnapshot.automaticMemory?.enabled == true)
precondition(newSnapshot.memories.first?.sourceQuote == "我希望简洁回复")
print("PASS: legacy and automatic-memory response contracts decode with source attribution")
