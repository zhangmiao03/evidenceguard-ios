import SwiftUI

@main
struct EvidenceGuardApp: App {
    @UIApplicationDelegateAdaptor(WorkspaceAppDelegate.self) private var appDelegate
    @StateObject private var store = AppStore()

    init() {
        let appearance = UITabBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor.white.withAlphaComponent(0.97)
        appearance.shadowColor = UIColor(red: 0.86, green: 0.90, blue: 0.95, alpha: 1)
        UITabBar.appearance().standardAppearance = appearance
        UITabBar.appearance().scrollEdgeAppearance = appearance
        UITabBar.appearance().tintColor = UIColor(Brand.blue)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(.light)
        }
    }
}

@MainActor final class WorkspaceAppDelegate: NSObject, UIApplicationDelegate {
    static var orientation: UIInterfaceOrientationMask = .portrait
    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        Self.orientation
    }
    static func setOrientation(_ mask: UIInterfaceOrientationMask) {
        orientation = mask
        for scene in UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }) {
            scene.windows.first(where: \.isKeyWindow)?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
            scene.requestGeometryUpdate(.iOS(interfaceOrientations: mask)) { _ in }
        }
    }
}
