import XCTest

final class WorkspaceTests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.buttons["workspace.switch"].waitForExistence(timeout: 15))
    }

    func testAllProductTabsRemainReachable() {
        for title in ["首页", "Skill", "AI", "证据", "我的"] {
            let tab = app.tabBars.buttons[title]
            XCTAssertTrue(tab.exists, "Missing native tab: \(title)")
            tab.tap()
            XCTAssertTrue(app.buttons["workspace.switch"].exists)
        }
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Native iOS profile and workspace switch"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    func testSimulatorExplainsOfficialSDKBoundaryAndReturns() {
        app.buttons["workspace.switch"].tap()
        XCTAssertTrue(app.navigationBars["官方 SDK 检查指引"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "当前是模拟器")).firstMatch.exists)
        app.buttons["完成"].tap()
        XCTAssertTrue(app.buttons["workspace.switch"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.tabBars.buttons["首页"].exists)
    }
}
