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
}
