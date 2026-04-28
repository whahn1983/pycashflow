import XCTest
@testable import pycashflow

final class SubscriptionDisclosureTests: XCTestCase {
    func testRequiredSubscriptionDisclosureCopy() {
        XCTAssertEqual(SubscriptionDisclosure.title, "PyCashFlow Cloud Monthly")
        XCTAssertEqual(SubscriptionDisclosure.price, "$9.99/month")
        XCTAssertEqual(
            SubscriptionDisclosure.durationAndType,
            "Billed monthly. Auto-renewing subscription."
        )
        XCTAssertTrue(SubscriptionDisclosure.renewalNotice.contains("Apple ID"))
        XCTAssertTrue(SubscriptionDisclosure.renewalNotice.contains("automatically renews"))
    }

    func testLegalLinksUseExpectedDestinations() {
        XCTAssertEqual(
            SubscriptionDisclosure.termsURL.absoluteString,
            "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/"
        )
        XCTAssertEqual(
            SubscriptionDisclosure.privacyURL.absoluteString,
            "https://www.pycashflow.com/privacy"
        )
    }
}
