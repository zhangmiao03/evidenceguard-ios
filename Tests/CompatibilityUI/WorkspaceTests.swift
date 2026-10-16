import XCTest

final class WorkspaceTests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["助手"].waitForExistence(timeout: 15))
    }

    func testAllProductTabsRemainReachable() {
        for title in ["助手", "摄像头Skill", "任务", "记忆", "我的"] {
            let tab = app.tabBars.buttons[title]
            XCTAssertTrue(tab.exists, "Missing native tab: \(title)")
            tab.tap()
            XCTAssertFalse(app.buttons["workspace.switch"].exists)
        }
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Native iOS profile without developer header"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    func testOfficialDiagnosticsLivesInSettings() {
        app.tabBars.buttons["我的"].tap()
        app.buttons["profile.settings"].tap()
        app.buttons["settings.cameraDebug"].tap()
        XCTAssertTrue(app.navigationBars["摄像头调试"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "当前是模拟器")).firstMatch.exists)
        XCTAssertFalse(app.buttons["settings.openOfficialWorkspace"].isEnabled)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(app.navigationBars["设置"].waitForExistence(timeout: 5))
    }

    func testProfileKeepsNotificationsAndOfficialCameraEntry() {
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.buttons["profile.notifications"].exists)
        let official = app.buttons["profile.officialSDK"]
        if !official.isHittable { app.swipeUp() }
        official.tap()
        XCTAssertTrue(app.navigationBars["连接摄像头"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["workspace.switch"].exists)
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
