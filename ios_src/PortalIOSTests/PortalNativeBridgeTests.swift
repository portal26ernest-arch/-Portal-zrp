import XCTest
@testable import PortalIOS

final class PortalNativeBridgeTests: XCTestCase {
    func testServerURLValidation() {
        XCTAssertTrue(PortalNativeBridge.isValidServerURL("https://portal.example"))
        XCTAssertTrue(PortalNativeBridge.isValidServerURL("http://127.0.0.1:8765"))
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

    func testOfficialServerDiscoveryURLValidation() {
        XCTAssertEqual(
            PortalNativeBridge.normalizeOfficialServerURL("https://2a03-6f00-a--1-f426.sslip.io/"),
            "https://2a03-6f00-a--1-f426.sslip.io"
        )
        XCTAssertEqual(
            PortalNativeBridge.normalizeOfficialServerURL("https://api.portal.example"),
            "https://api.portal.example"
        )
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("http://api.portal.example"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://portal.invalid"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://abc.trycloudflare.com"))
        XCTAssertNil(PortalNativeBridge.normalizeOfficialServerURL("https://api.portal.example/path"))
    }
}
