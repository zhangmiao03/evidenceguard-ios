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
        for title in ["助手", "摄像头Skill", "任务", "记忆", "我的"] {
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
        XCTAssertTrue(app.tabBars.buttons["助手"].exists)
    }

    func testProfileKeepsNotificationsAndOfficialCameraEntry() {
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.buttons["profile.notifications"].exists)
        let official = app.buttons["profile.officialSDK"]
        if !official.isHittable { app.swipeUp() }
        official.tap()
        XCTAssertTrue(app.navigationBars["连接摄像头"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["workspace.switch"].exists)
    }

    func testConnectionsAndPhonePreviewDoNotRequestPermissionOnEntry() {
        app.tabBars.buttons["我的"].tap()
        app.buttons["连接应用"].tap()
        XCTAssertTrue(app.navigationBars["连接应用"].waitForExistence(timeout: 5))
        app.buttons["日历与提醒事项"].tap()
        XCTAssertTrue(app.navigationBars["手机信息"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["预览未来 7 天的日历"].exists)
        XCTAssertFalse(app.alerts.firstMatch.exists)
        XCTAssertFalse(app.buttons["共享给 anker，24 小时内可读"].exists)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Phone information requires preview before sharing"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    func testMorningAndEveningReportsHaveSeparateControls() {
        app.tabBars.buttons["我的"].tap()
        app.buttons["profile.notifications"].tap()
        XCTAssertTrue(app.switches["notifications.morning"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.switches["notifications.evening"].exists)
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "不把没有事件当作家里安全")).firstMatch.exists)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Morning and evening report subscriptions"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
}
