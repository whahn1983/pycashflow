import Foundation

/// Rounding helpers that reproduce the two rounding regimes the PyCashFlow
/// backend's risk score flows through.
///
/// The backend mixes `numpy.float64` and plain Python `float`, whose `round`
/// implementations differ at exact half-way boundaries:
///   * numpy scales, rounds the product half-to-even, then unscales
///     (`rint(x·10ⁿ)/10ⁿ`), so the scaling can nudge a tie the other way;
///   * Python performs correctly-rounded decimal rounding of the true double.
/// Reproducing both keeps `runway_days` (the only displayed risk field whose
/// rounding regime varies) exactly in step with the backend.
enum DemoRounding {
    /// numpy `round(x, n)`.
    static func numpyRound(_ x: Double, _ n: Int) -> Double {
        guard x.isFinite else { return x }
        let factor = pow(10.0, Double(n))
        return (x * factor).rounded(.toNearestOrEven) / factor
    }

    /// Python `round(x, n)` — correctly-rounded (half-to-even) decimal rounding
    /// of the *true* double value.
    static func pythonRound(_ x: Double, _ n: Int) -> Double {
        guard x.isFinite else { return x }
        // "%.20f" prints enough of the exact decimal expansion of the double
        // for a correct half-to-even decision at any 0–4 dp position in the
        // money/risk value ranges used here.
        let text = String(format: "%.20f", x)
        guard var dec = Decimal(string: text) else { return x }
        var rounded = Decimal()
        NSDecimalRound(&rounded, &dec, n, .bankers)
        return NSDecimalNumber(decimal: rounded).doubleValue
    }
}

/// Amount → string formatting that matches the backend's `_amount()` serializer
/// (`f"{Decimal(str(value)):.2f}"`) exactly, producing a locale-independent
/// two-decimal string such as `"1234.56"` or `"-11931.29"`.
enum DemoAmount {
    /// Formats a `Decimal` amount (already an exact decimal, e.g. a user-entered
    /// value) to two places with half-to-even rounding.
    static func string(_ value: Decimal) -> String {
        var v = value
        var rounded = Decimal()
        NSDecimalRound(&rounded, &v, 2, .bankers)

        let negative = rounded < 0
        let magnitude = negative ? -rounded : rounded
        var scaled = magnitude * 100
        var cents = Decimal()
        NSDecimalRound(&cents, &scaled, 0, .plain)
        let centsInt = NSDecimalNumber(decimal: cents).int64Value

        let dollars = centsInt / 100
        let frac = centsInt % 100
        let sign = (negative && centsInt != 0) ? "-" : ""
        let fracPadded = frac < 10 ? "0\(frac)" : "\(frac)"
        return "\(sign)\(dollars).\(fracPadded)"
    }

    /// Formats a `Double` amount via the backend's `_amount(float)` path:
    /// `Decimal(str(x))` (shortest round-tripping repr) then two-place rounding.
    static func string(fromDouble x: Double) -> String {
        guard x.isFinite else { return "0.00" }
        let decimal = Decimal(string: String(x)) ?? Decimal(x)
        return string(decimal)
    }

    /// Formats a `Double` that the backend first passes through Python
    /// `round(x, 2)` before `_amount()` (the risk `lowest_balance` /
    /// `near_term_buffer` fields).
    static func string(fromPyRounded x: Double) -> String {
        guard x.isFinite else { return "0.00" }
        let text = String(format: "%.20f", x)
        guard var dec = Decimal(string: text) else { return string(fromDouble: x) }
        var rounded = Decimal()
        NSDecimalRound(&rounded, &dec, 2, .bankers)
        return string(rounded)
    }
}
