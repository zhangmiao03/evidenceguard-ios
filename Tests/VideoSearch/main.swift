import Foundation

let query = VideoSearchInput(text: "有人放下这个物体", image_ref: "query-image-example", camera_ids: ["cam-a"], time_range: HistoryFilter(period: "all"))
let encoded = try JSONEncoder().encode(query)
let body = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
precondition(body["image_ref"] as? String == "query-image-example")
precondition(body["text"] as? String == "有人放下这个物体")
precondition(body["camera_ids"] as? [String] == ["cam-a"])
precondition(body["verify_limit"] as? Int == 3)

var pending = PendingChatRequest(id: "run-image", message: "找这个物体", conversation: "history", skill: nil, camera: "cam-a", mode: "history", filter: nil, replyID: nil)
pending.referenceImageID = "query-image-example"
let restored = try JSONDecoder().decode(PendingChatRequest.self, from: JSONEncoder().encode(pending))
precondition(restored.referenceImageID == pending.referenceImageID)
precondition(!restored.matches(message: pending.message, camera: pending.camera, mode: "history", filter: nil, replyID: nil))
precondition(restored.matches(message: pending.message, camera: pending.camera, mode: "history", filter: nil, replyID: nil, referenceImageID: pending.referenceImageID))

let legacy = try JSONDecoder().decode(VideoModelInfo.self, from: Data(#"{"visionModel":"vision","embeddingModel":"embed","embeddingReady":true}"#.utf8))
precondition(legacy.retrievalVersion == nil)
let payload = #"{"id":"search-example","status":"verifying","query":{"text":"物体","image_ref":null,"camera_ids":[],"time_range":{"period":"all","startAt":null,"endAt":null},"timezone":"Asia/Shanghai","limit":10,"verify_limit":3},"scope":{"cameraIds":[],"period":"all","startAt":null,"endAt":null,"timezone":"Asia/Shanghai","coverage":"已保存录像"},"videos":[],"reason":"核对中","candidateCount":0,"verifiedCount":0,"indexChanged":false,"removedCandidates":0}"#
let result = try JSONDecoder().decode(VideoSearchResult.self, from: Data(payload.utf8))
precondition(result.isRunning && result.query.image_ref == nil)
print("PASS: multimodal search request/result, old-server capability gate, and durable image-bound retry identity")
