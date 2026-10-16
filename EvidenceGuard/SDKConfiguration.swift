import Foundation

struct SDKCredentials: Codable, Equatable {
    var userID = ""
    var token = ""
    var environment = "PR"
    var isComplete: Bool {
        !userID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        ["PR", "QA"].contains(environment)
    }
    var normalized: SDKCredentials {
        .init(userID: userID.trimmingCharacters(in: .whitespacesAndNewlines),
              token: token.trimmingCharacters(in: .whitespacesAndNewlines), environment: environment)
    }
}

/// Values are supplied by a private internal-build xcconfig, never by source literals.
struct SDKConfiguration {
    let values: [String: Any]
    static var current: Self { .init(values: Bundle.main.infoDictionary ?? [:]) }
    var usesManagedAccount: Bool { values["EGSDKManagedAccount"] as? String == "YES" }
    var credentials: SDKCredentials? {
        guard usesManagedAccount,
              let user = value("EGSDKUserID"), let token = value("EGSDKAuthToken"),
              let environment = value("EGSDKEnvironment") else { return nil }
        let credentials = SDKCredentials(userID: user, token: token, environment: environment)
        return credentials.isComplete ? credentials : nil
    }
    private func value(_ key: String) -> String? {
        guard let raw = values[key] as? String else { return nil }
        let result = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return result.isEmpty || result.contains("$(") || result.contains("${") ? nil : result
    }

    static func workspaceIssue(info: [String: Any], resourceExists: (String) -> Bool) -> String? {
        guard info["CADisableMinimumFrameDurationOnPhone"] as? Bool == true else {
            return "当前版本的摄像头页面配置不完整，请更新 App 后重试。"
        }
        let required = ["Frameworks/SampleCore.framework/SampleCore",
                        "Frameworks/AnkerWebRTC.framework/AnkerWebRTC",
                        "compose-resources/composeResources/com.anker.esiotkit.demo.generated.resources"]
        guard required.allSatisfy(resourceExists) else {
            return "当前安装包缺少摄像头页面所需资源，请更新 App 后重试。"
        }
        return nil
    }
}
