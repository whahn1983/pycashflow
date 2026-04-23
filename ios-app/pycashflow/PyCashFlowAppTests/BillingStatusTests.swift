import XCTest
@testable import pycashflow

final class BillingStatusTests: XCTestCase {
    func testGlobalAdminAlwaysAllowed() {
        let status = BillingStatusDTO(
            user_id: 1,
            is_active: false,
            effective_is_active: false,
            subscription_status: "expired",
            subscription_source: "app_store",
            subscription_expiry: nil,
            payments_enabled: true,
            is_global_admin: true,
            is_guest: false,
            owner_user_id: nil
        )

        XCTAssertTrue(status.effectiveAccessAllowed)
    }

    func testGuestMessageWhenInactive() {
        let status = BillingStatusDTO(
            user_id: 22,
            is_active: false,
            effective_is_active: false,
            subscription_status: "expired",
            subscription_source: "app_store",
            subscription_expiry: nil,
            payments_enabled: true,
            is_global_admin: false,
            is_guest: true,
            owner_user_id: 7
        )

        XCTAssertEqual(
            status.accessMessage,
            "Guest access depends on your account owner's active subscription."
        )
    }
}
