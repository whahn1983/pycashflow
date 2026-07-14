import Foundation
import StoreKit

/// Pure helpers for comparing subscription plans of different cadences
/// (for example monthly vs. annual) so the paywall can surface which plan is
/// the best value and how much it saves.
///
/// All math is driven by the live App Store prices and subscription periods,
/// so nothing here assumes a specific price point.
enum SubscriptionPlanValue {
    /// Number of months represented by a StoreKit subscription period. Weeks and
    /// days are converted to a fractional month using 30-day months so shorter
    /// cadences can still be normalized for comparison.
    static func months(in period: Product.SubscriptionPeriod) -> Decimal {
        let value = Decimal(period.value)
        switch period.unit {
        case .day:
            return value / 30
        case .week:
            return value * 7 / 30
        case .month:
            return value
        case .year:
            return value * 12
        @unknown default:
            return value
        }
    }

    /// Price normalized to a per-month figure so plans billed on different
    /// cadences can be compared directly. Returns `nil` when the period does not
    /// represent a positive span of time.
    static func monthlyEquivalentPrice(price: Decimal, period: Product.SubscriptionPeriod) -> Decimal? {
        let months = months(in: period)
        guard months > 0 else { return nil }
        return price / months
    }

    /// Percentage saved by a plan whose per-month cost is `monthlyEquivalent`
    /// relative to the most expensive per-month cost in `comparisons`.
    ///
    /// Returns `nil` when there is no baseline to compare against or the plan is
    /// not actually cheaper, so callers can hide the badge instead of showing
    /// "Save 0%".
    static func savingsPercent(monthlyEquivalent plan: Decimal, comparedTo comparisons: [Decimal]) -> Int? {
        guard let baseline = comparisons.max(), baseline > 0, plan < baseline else { return nil }
        let fraction = (baseline - plan) / baseline
        let percent = NSDecimalNumber(decimal: fraction).doubleValue * 100
        let rounded = Int(percent.rounded())
        return rounded > 0 ? rounded : nil
    }
}
