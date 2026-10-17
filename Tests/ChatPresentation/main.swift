import Foundation
precondition(ChatPresentation.textHash("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
precondition(ChatPresentation.textHash("回复") != ChatPresentation.textHash("回复 "))
let rendered = try AttributedString(markdown: "**回复**", options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))
precondition(ChatPresentation.textHash(String(rendered.characters)) == ChatPresentation.textHash("回复"))
struct Example: Decodable { let input: String; let expected: String }
let examples = try JSONDecoder().decode([Example].self, from: Data(contentsOf: URL(fileURLWithPath: "Tests/ChatPresentation/cases.json")))
for example in examples { precondition(ChatPresentation.text(example.input) == example.expected, "Unexpected presentation: \(ChatPresentation.text(example.input))") }
func operation(_ state: String, tool: String = "camera_ptz_step", args: [String:HardwareValue] = ["direction":.string("LEFT")]) -> HardwareValue { .object(["executionState":.string(state),"tool":.string(tool),"arguments":.object(args)]) }
precondition(ChatPresentation.operationStatus(operation("awaitingApproval")).hasPrefix("等待你确认"))
precondition(!ChatPresentation.operationStatus(operation("queued")).hasPrefix("正在移动"))
precondition(ChatPresentation.operationStatus(operation("executing")) == "正在移动摄像头")
precondition(ChatPresentation.operationStatus(operation("completed")).contains("仍需核对"))
precondition(ChatPresentation.operationDetails(operation("awaitingApproval"),deviceName:"客厅").contains("方向：向左移动一步"))
precondition(ChatPresentation.operationDetails(operation("awaitingApproval",tool:"camera_record_clip",args:["duration":.number(10),"audioPolicy":.string("forbidden")]),deviceName:nil).contains("持续 10 秒 · 不录入声音"))
precondition(!ChatPresentation.receipt("future_tool","future_state").contains("future"))
precondition(ChatPresentation.progress("camera_ptz_step") == "正在准备移动摄像头")
let event = try JSONDecoder().decode(RunEvent.self,from:Data(#"{"runId":"r","sequence":1,"type":"tool_started","payload":{"tool":"read_home_report"}}"#.utf8))
precondition(event.progressLabel == "正在整理家庭报告")
let unknown = try JSONDecoder().decode(RunEvent.self,from:Data(#"{"runId":"r","sequence":1,"type":"new_internal_event"}"#.utf8))
precondition(unknown.progressLabel == "正在处理请求")
precondition(ChatPresentation.error("TimeoutError requestHash=secret")=="等待响应超时，请稍后重试。")
print("PASS: chat hides structured payloads/code, preserves prose, shows truthful action phases and confirmation details")
