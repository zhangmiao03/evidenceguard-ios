import Foundation

func run(_ id: String, conversation: String, created: Double, completed: Double?) throws -> AgentRun {
    var json: [String: Any] = ["id": id, "conversationId": conversation, "message": "测试问题", "status": "completed", "createdAt": created, "text": "测试回复", "toolReceipts": []]
    if let completed { json["completedAt"] = completed }
    return try JSONDecoder().decode(AgentRun.self, from: JSONSerialization.data(withJSONObject: json))
}
func message(_ id: String, at: Double, body: String = "测试主动消息") throws -> AssistantMessage {
    try JSONDecoder().decode(AssistantMessage.self, from: JSONSerialization.data(withJSONObject: ["id": id, "createdAt": at, "title": "测试", "body": body, "why": "测试来源", "read": false, "sources": []]))
}
let live = try run("same-id", conversation: "main", created: 10, completed: 30)
let history = try run("history", conversation: "main-history", created: 40, completed: 50)
let proactive = try message("same-id", at: 20)
let report = try message("morning", at: 35)
let items = ChatTimelineItem.items(runs: [history, live, live], messages: [report, proactive])
precondition(items.map(\.id) == ["0-user:same-id", "2-message:same-id", "1-reply:same-id", "2-message:morning", "0-user:history", "1-reply:history"])
// Repeated polling and a merged reminder update the same row, never add a fake user turn.
let updated = try message("same-id", at: 20, body: "合并后的观察")
let merged = ChatTimelineItem.items(runs: [], messages: [proactive, updated])
precondition(merged.count == 1)
if case .proactive(let value) = merged[0] { precondition(value.body == updated.body) } else { fatalError() }
// Old backend payloads remain readable; unknown reply time falls back to its turn time.
let legacy = try run("legacy", conversation: "main", created: 1, completed: nil)
precondition(ChatTimelineItem.items(runs: [legacy], messages: []).map(\.id) == ["0-user:legacy", "1-reply:legacy"])
precondition(ChatTimelineItem.messageID(proactive.id) == items[1].id)
print("PASS: live/history turns, proactive messages and reports interleave; stable identities deduplicate; legacy payloads decode")
