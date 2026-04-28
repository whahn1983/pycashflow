import Foundation
import StoreKit
import SwiftUI

struct SubscriptionDisclosure: View {
    let product: Product

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(product.displayName)
                .font(.headline)
                .foregroundStyle(AppTheme.textPrimary)
                .lineLimit(2)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)

            Text(product.displayPrice)
                .font(.title3.weight(.semibold))
                .foregroundStyle(AppTheme.textPrimary)

            Text("Billed every \(Self.billingPeriodText(from: product.subscription?.subscriptionPeriod)). Auto-renewing subscription.")
                .foregroundStyle(AppTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            Text(Self.renewalNotice)
                .font(.footnote)
                .foregroundStyle(AppTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 6) {
                Link(Self.termsTitle, destination: Self.termsURL)
                Link(Self.privacyTitle, destination: Self.privacyURL)
            }
            .font(.footnote.weight(.semibold))
        }
    }

    static func billingPeriodText(from period: Product.SubscriptionPeriod?) -> String {
        guard let period else { return "subscription period" }
        let value = period.value
        let unit = billingUnitText(period.unit, value: value)
        return value == 1 ? unit : "\(value) \(unit)"
    }

    private static func billingUnitText(_ unit: Product.SubscriptionPeriod.Unit, value: Int) -> String {
        switch unit {
        case .day:
            return value == 1 ? "day" : "days"
        case .week:
            return value == 1 ? "week" : "weeks"
        case .month:
            return value == 1 ? "month" : "months"
        case .year:
            return value == 1 ? "year" : "years"
        @unknown default:
            return "subscription period"
        }
    }

    static let renewalNotice = "Payment will be charged to your Apple ID. " +
        "Subscription automatically renews unless canceled at least 24 hours " +
        "before the end of the current billing period. You can manage or " +
        "cancel your subscription in Apple ID settings."

    static let termsTitle = "Terms of Use"
    static let privacyTitle = "Privacy Policy"
    static let termsURL = URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!
    static let privacyURL = URL(string: "https://www.pycashflow.com/privacy")!
}
