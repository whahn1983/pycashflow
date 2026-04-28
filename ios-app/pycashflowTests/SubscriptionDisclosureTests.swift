import XCTest
import StoreKit
@testable import pycashflow

final class SubscriptionDisclosureTests: XCTestCase {
    func testBillingPeriodTextSupportsSupportedStoreKitCadences() {
        XCTAssertEqual(
            SubscriptionDisclosure.billingPeriodText(
                from: Product.SubscriptionPeriod(value: 1, unit: .day)
            ),
            "day"
        )
        XCTAssertEqual(
            SubscriptionDisclosure.billingPeriodText(
                from: Product.SubscriptionPeriod(value: 2, unit: .week)
            ),
            "2 weeks"
        )
        XCTAssertEqual(
            SubscriptionDisclosure.billingPeriodText(
                from: Product.SubscriptionPeriod(value: 1, unit: .month)
            ),
            "month"
        )
        XCTAssertEqual(
            SubscriptionDisclosure.billingPeriodText(
                from: Product.SubscriptionPeriod(value: 3, unit: .year)
            ),
            "3 years"
        )
    }

    func testBillingPeriodTextFallsBackWhenSubscriptionPeriodIsUnavailable() {
        XCTAssertEqual(
            SubscriptionDisclosure.billingPeriodText(from: nil),
            "subscription period"
        )
    }

    func testRequiredSubscriptionDisclosureCopy() {
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
