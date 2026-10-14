import Foundation

let delivery = PushTap(id: UUID().uuidString, scope: "team")
var pending: PushTap? = delivery
var selection: AppTab = .cameraSkills
var paths: [[AppRoute]] = Array(repeating: [], count: AppTab.allCases.count)
paths[AppTab.assistant.rawValue] = [.conversation("saved-chat", nil)]
paths[AppTab.cameraSkills.rawValue] = [.camera("saved-camera")]
let before = paths

// Opening, showing and releasing the vendor UI must preserve the tap and all
// product navigation. The caller exposes productVisible only after release.
for _ in ["opening", "official", "releasing"] {
    assert(!PushNavigation.consume(&pending, selection: &selection, paths: &paths,
        productVisible: false, presentationBlocked: false))
    assert(pending == delivery && selection == .cameraSkills && paths == before)
}
// Returning first restores the SDK account page; a guide/editor still defers.
selection = .profile
paths[AppTab.profile.rawValue] = [.officialSDK]
let restored = paths
assert(!PushNavigation.consume(&pending, selection: &selection, paths: &paths,
    productVisible: true, presentationBlocked: true))
assert(pending == delivery && selection == .profile && paths == restored)

assert(PushNavigation.consume(&pending, selection: &selection, paths: &paths,
    productVisible: true, presentationBlocked: false))
assert(pending == nil && selection == .assistant)
assert(paths[0] == [.conversation("saved-chat", nil), .pushDelivery(delivery.id, delivery.scope)])
assert(paths[AppTab.cameraSkills.rawValue] == before[AppTab.cameraSkills.rawValue])
assert(paths[AppTab.profile.rawValue] == [.officialSDK])
let opened = paths
assert(!PushNavigation.consume(&pending, selection: &selection, paths: &paths,
    productVisible: true, presentationBlocked: false))
assert(paths == opened) // Repeated SwiftUI change notifications must not duplicate.

// A tap that survived a cold launch remains Codable and is not consumed while
// product paths have not yet been installed.
pending = try JSONDecoder().decode(PushTap.self, from: JSONEncoder().encode(delivery))
paths = []
assert(!PushNavigation.consume(&pending, selection: &selection, paths: &paths,
    productVisible: true, presentationBlocked: false))
assert(pending == delivery)
print("PASS: pending push survives official workspace, sheets and cold launch; return routes once and preserves other tabs")
