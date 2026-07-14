import XCTest
import StoreKit
@testable import pycashflow

final class SubscriptionPlanValueTests: XCTestCase {
    func testConfiguredProductIDsIncludeMonthlyAndAnnual() {
        XCTAssertEqual(
            AppEnvironment.appStoreProductIDs,
            [
                "com.h3consultingpartners.pycashflow.cloud.monthly",
                "com.h3consultingpartners.pycashflow.cloud.annual"
            ]
        )
    }

    func testMonthsInPeriodForSupportedCadences() {
        XCTAssertEqual(
            SubscriptionPlanValue.months(in: Product.SubscriptionPeriod(value: 1, unit: .month)),
            1
        )
        XCTAssertEqual(
            SubscriptionPlanValue.months(in: Product.SubscriptionPeriod(value: 1, unit: .year)),
            12
        )
        XCTAssertEqual(
            SubscriptionPlanValue.months(in: Product.SubscriptionPeriod(value: 3, unit: .month)),
            3
        )
    }

    func testMonthlyEquivalentPriceNormalizesAnnualToPerMonth() {
        let annual = SubscriptionPlanValue.monthlyEquivalentPrice(
            price: Decimal(48),
            period: Product.SubscriptionPeriod(value: 1, unit: .year)
        )
        XCTAssertEqual(annual, 4)

        let monthly = SubscriptionPlanValue.monthlyEquivalentPrice(
            price: Decimal(string: "5.99")!,
            period: Product.SubscriptionPeriod(value: 1, unit: .month)
        )
        XCTAssertEqual(monthly, Decimal(string: "5.99"))
    }

    func testSavingsPercentComparesAnnualAgainstMonthly() {
        // Monthly $5.00/mo vs annual $48.00/yr ($4.00/mo) => 20% saved.
        let monthlyPerMonth = SubscriptionPlanValue.monthlyEquivalentPrice(
            price: Decimal(5),
            period: Product.SubscriptionPeriod(value: 1, unit: .month)
        )!
        let annualPerMonth = SubscriptionPlanValue.monthlyEquivalentPrice(
            price: Decimal(48),
            period: Product.SubscriptionPeriod(value: 1, unit: .year)
        )!

        let savings = SubscriptionPlanValue.savingsPercent(
            monthlyEquivalent: annualPerMonth,
            comparedTo: [monthlyPerMonth, annualPerMonth]
        )
        XCTAssertEqual(savings, 20)
    }

    func testSavingsPercentIsNilWhenPlanIsNotCheaper() {
        let monthlyPerMonth = SubscriptionPlanValue.monthlyEquivalentPrice(
            price: Decimal(string: "5.99")!,
            period: Product.SubscriptionPeriod(value: 1, unit: .month)
        )!
        XCTAssertNil(
            SubscriptionPlanValue.savingsPercent(
                monthlyEquivalent: monthlyPerMonth,
                comparedTo: [monthlyPerMonth]
            )
        )
    }
}
