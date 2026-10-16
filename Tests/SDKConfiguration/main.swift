import Foundation

let configured: [String: Any] = ["EGSDKManagedAccount": "YES", "EGSDKUserID": "test-user",
    "EGSDKAuthToken": "test-token", "EGSDKEnvironment": "PR"]
precondition(SDKConfiguration(values: configured).credentials?.userID == "test-user")
precondition(SDKConfiguration(values: [:]).credentials == nil)
for key in ["EGSDKUserID", "EGSDKAuthToken", "EGSDKEnvironment"] {
    for invalid in ["", "  ", "$(UNRESOLVED)"] {
        var values = configured; values[key] = invalid
        precondition(SDKConfiguration(values: values).usesManagedAccount)
        precondition(SDKConfiguration(values: values).credentials == nil)
    }
}
var invalid = configured; invalid["EGSDKEnvironment"] = "other"
precondition(SDKConfiguration(values: invalid).credentials == nil)
precondition(SDKConfiguration.workspaceIssue(info: [:], resourceExists: { _ in true }) != nil)
precondition(SDKConfiguration.workspaceIssue(info: ["CADisableMinimumFrameDurationOnPhone": true],
    resourceExists: { _ in true }) == nil)
for missing in ["SampleCore", "AnkerWebRTC", "compose-resources"] {
    precondition(SDKConfiguration.workspaceIssue(info: ["CADisableMinimumFrameDurationOnPhone": true],
        resourceExists: { !$0.contains(missing) }) != nil)
}
print("SDK managed configuration and workspace preflight checks passed.")
