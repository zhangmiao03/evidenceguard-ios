import Foundation
let token = String(repeating: "a", count: 48)
let config = MobileServiceConfiguration(values: ["EGInternalDemo":"YES", "EGServiceBaseURL":"https://demo.example.com", "EGDemoAccessToken":token])
assert(config.demoToken(for: URL(string:"https://demo.example.com/api/bootstrap")!) == token)
for url in ["http://demo.example.com", "https://demo.example.com:8443", "https://example.com", "https://demo.example.com.evil.test", "https://user@demo.example.com"] { assert(config.demoToken(for: URL(string:url)!) == nil) }
assert(MobileServiceConfiguration(values:["EGInternalDemo":"NO"]).demoToken(for: URL(string:"https://demo.example.com")!) == nil)
assert(DeviceQRCode.parse("T8214DEMO001")?.model == "T8214")
assert(DeviceQRCode.parse("{\"sn\":\"T8171TEST123\"}")?.serial == "T8171TEST123")
assert(DeviceQRCode.parse("https://device.example.com/pair?sn=T8214DEMO001") != nil)
for raw in ["https://example.com", "javascript:T8214DEMO001", "T9999DEMO001", "https://device.example.com/?sn=T8214DEMO001&sn=T8171TEST123", String(repeating:"x",count:3000), "{\"token\":\"T8214DEMO001\"}"] { assert(DeviceQRCode.parse(raw) == nil) }
print("PASS: scoped auto-connection and device QR input boundaries")

let suite = "evidenceguard-migration-test-" + UUID().uuidString
let defaults = UserDefaults(suiteName: suite)!
defer { defaults.removePersistentDomain(forName: suite) }
let legacy = "https://demo.34.218.51.85.sslip.io"
let draft = Data("draft-and-pending-request".utf8)
defaults.set(draft, forKey: "localChats:" + legacy)
defaults.set("chat-existing", forKey: "activeChat:" + legacy)
defaults.set("installation-existing", forKey: "installationID")
MobileServiceConfiguration(values: ["EGServiceBaseURL":"https://demo.example.com"]).migrateLegacyChatState(in: defaults)
assert(defaults.data(forKey: "localChats:https://demo.example.com") == nil)
config.migrateLegacyChatState(in: defaults)
assert(defaults.data(forKey: "localChats:https://demo.example.com") == draft)
assert(defaults.string(forKey: "activeChat:https://demo.example.com") == "chat-existing")
assert(defaults.string(forKey: "installationID") == "installation-existing")
assert(defaults.data(forKey: "localChats:" + legacy) == draft)
defaults.set("chat-new", forKey: "activeChat:https://demo.example.com")
defaults.removeObject(forKey: "localChats:https://demo.example.com")
config.migrateLegacyChatState(in: defaults)
assert(defaults.string(forKey: "activeChat:https://demo.example.com") == "chat-new")
assert(defaults.data(forKey: "localChats:https://demo.example.com") == nil)
let other = MobileServiceConfiguration(values: ["EGInternalDemo":"YES", "EGServiceBaseURL":"https://existing.example.com"])
defaults.set("destination-chat", forKey: "activeChat:https://existing.example.com")
other.migrateLegacyChatState(in: defaults)
assert(defaults.string(forKey: "activeChat:https://existing.example.com") == "destination-chat")
print("PASS: server migration preserves drafts, chat selection and installation identity once")
