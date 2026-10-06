import XCTest
@testable import PortalIOS

final class PortalNativeBridgeTests: XCTestCase {
    func testServerURLValidation() {
        XCTAssertTrue(PortalNativeBridge.isValidServerURL("https://portal.example"))
        XCTAssertTrue(PortalNativeBridge.isValidServerURL("http://127.0.0.1:8765"))
        XCTAssertTrue(PortalNativeBridge.isValidServerURL("http://[::1]:8765"))
        XCTAssertFalse(PortalNativeBridge.isValidServerURL("http://api.portal.example"))
        XCTAssertFalse(PortalNativeBridge.isValidServerURL("http://192.0.2.10"))
        XCTAssertFalse(PortalNativeBridge.isValidServerURL("ftp://portal.example"))
        XCTAssertFalse(PortalNativeBridge.isValidServerURL("https://user:pass@portal.example"))
        XCTAssertFalse(PortalNativeBridge.isValidServerURL("https://portal.example/api"))
        XCTAssertFalse(PortalNativeBridge.isValidServerURL("https://portal.example/?token=secret"))
    }

    func testOfficialMarketplaceLinksOnly() throws {
        XCTAssertTrue(PortalNativeBridge.isAllowedExternalURL(try XCTUnwrap(URL(string: "https://seller.ozon.ru/app"))))
        XCTAssertTrue(PortalNativeBridge.isAllowedExternalURL(try XCTUnwrap(URL(string: "https://seller.wildberries.ru/"))))
        XCTAssertFalse(PortalNativeBridge.isAllowedExternalURL(try XCTUnwrap(URL(string: "http://seller.ozon.ru/"))))
        XCTAssertFalse(PortalNativeBridge.isAllowedExternalURL(try XCTUnwrap(URL(string: "https://example.com/"))))
    }

    func testMessengerAllowsOnlyOfficialProviderHosts() throws {
        XCTAssertTrue(MessengerViewController.isAllowedTopLevel(try XCTUnwrap(URL(string: "https://web.telegram.org/a/"))))
        XCTAssertTrue(MessengerViewController.isAllowedTopLevel(try XCTUnwrap(URL(string: "https://web.max.ru/"))))
        XCTAssertFalse(MessengerViewController.isAllowedTopLevel(try XCTUnwrap(URL(string: "https://telegram.org/"))))
        XCTAssertFalse(MessengerViewController.isAllowedTopLevel(try XCTUnwrap(URL(string: "https://web.max.ru.evil.example/"))))
    }

    func testOfficialServerDiscoveryURLValidation() {
        XCTAssertEqual(
            PortalNativeBridge.normalizeOfficialServerURL("https://api.vart-portal.ru/"),
            "https://api.vart-portal.ru"
        )
        XCTAssertEqual(
            PortalNativeBridge.normalizeOfficialServerURL("https://reserve-api.vart-portal.ru"),
            "https://reserve-api.vart-portal.ru"
        )
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://api.portal.example"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://evil.api.vart-portal.ru"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://2a03-6f00-a--1-f426.sslip.io"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("http://api.portal.example"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://portal.invalid"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://abc.trycloudflare.com"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://api.portal.example/path"))
    }
}
