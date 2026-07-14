import Foundation

/// A pure-integer proleptic Gregorian calendar date (year / month / day) with
/// no timezone or `Foundation.Calendar` involvement.
///
/// The standalone Demo-mode projection engine reproduces the PyCashFlow backend
/// (`app/cashflow.py`) bit-for-bit. That backend does its date arithmetic with
/// Python's `datetime.date` + `dateutil.relativedelta` + pandas business-day
/// offsets. `Foundation.Calendar` can diverge from that math around DST and
/// month-length clamping, so this type re-implements the exact integer rules
/// instead, matching the behaviour that was fuzz-verified against the real
/// backend across tens of thousands of cases.
///
/// `weekday` follows Python's `date.weekday()` convention: Monday == 0 …
/// Sunday == 6.
struct DemoDate: Equatable, Comparable, Hashable, Codable {
    let year: Int
    let month: Int
    let day: Int

    init(_ year: Int, _ month: Int, _ day: Int) {
        self.year = year
        self.month = month
        self.day = day
    }

    // MARK: Calendar helpers

    static func isLeap(_ y: Int) -> Bool {
        (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0)
    }

    private static let monthDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    static func daysInMonth(_ y: Int, _ m: Int) -> Int {
        if m == 2 && isLeap(y) { return 29 }
        return monthDays[m - 1]
    }

    /// Proleptic Gregorian ordinal matching Python's `date.toordinal()`
    /// (`date(1, 1, 1)` == 1).
    var ordinal: Int {
        var days = 0
        let yy = year - 1
        days += yy * 365 + yy / 4 - yy / 100 + yy / 400
        var m = 1
        while m < month {
            days += DemoDate.daysInMonth(year, m)
            m += 1
        }
        days += day
        return days
    }

    /// Monday == 0 … Sunday == 6 (Python `date.weekday()`).
    var weekday: Int {
        // ordinal for 0001-01-01 is 1 and that day is a Monday.
        let r = (ordinal - 1) % 7
        return r >= 0 ? r : r + 7
    }

    static func fromOrdinal(_ n: Int) -> DemoDate {
        var y = (n / 366) + 1
        while DemoDate(y + 1, 1, 1).ordinal <= n { y += 1 }
        while DemoDate(y, 1, 1).ordinal > n { y -= 1 }
        var rem = n - DemoDate(y, 1, 1).ordinal + 1   // 1-based day of year
        var m = 1
        while rem > daysInMonth(y, m) {
            rem -= daysInMonth(y, m)
            m += 1
        }
        return DemoDate(y, m, rem)
    }

    // MARK: Arithmetic

    func addingDays(_ n: Int) -> DemoDate {
        DemoDate.fromOrdinal(ordinal + n)
    }

    /// `dateutil.relativedelta(months=n)`: shift the month, clamping the day to
    /// the length of the destination month.
    func addingMonths(_ n: Int) -> DemoDate {
        let total = year * 12 + (month - 1) + n
        let ny = Int(floorDiv(total, 12))
        let nm = Int(mod(total, 12)) + 1
        let nd = min(day, DemoDate.daysInMonth(ny, nm))
        return DemoDate(ny, nm, nd)
    }

    /// `dateutil.relativedelta(years=n)`: shift the year, clamping the day
    /// (Feb 29 → Feb 28 in a common year).
    func addingYears(_ n: Int) -> DemoDate {
        let ny = year + n
        let nd = min(day, DemoDate.daysInMonth(ny, month))
        return DemoDate(ny, month, nd)
    }

    /// Mirrors Python `date.replace(day:)` which raises when the day is out of
    /// range — here that surfaces as `nil`.
    func replacingDay(_ d: Int) -> DemoDate? {
        guard d >= 1, d <= DemoDate.daysInMonth(year, month) else { return nil }
        return DemoDate(year, month, d)
    }

    // MARK: Business-day rolls (pandas offsets)

    /// `(date - BDay(0))`: a weekend rolls **forward** to the next Monday.
    var rolledForwardToBusinessDay: DemoDate {
        switch weekday {
        case 5: return addingDays(2)   // Saturday → Monday
        case 6: return addingDays(1)   // Sunday → Monday
        default: return self
        }
    }

    /// `BDay(1).rollback(date)`: a weekend rolls **back** to the prior Friday.
    var rolledBackToBusinessDay: DemoDate {
        switch weekday {
        case 5: return addingDays(-1)  // Saturday → Friday
        case 6: return addingDays(-2)  // Sunday → Friday
        default: return self
        }
    }

    // MARK: ISO string

    /// `yyyy-MM-dd`.
    var isoString: String {
        let y = String(year)
        let yPad = String(repeating: "0", count: max(0, 4 - y.count)) + y
        let m = month < 10 ? "0\(month)" : "\(month)"
        let d = day < 10 ? "0\(day)" : "\(day)"
        return "\(yPad)-\(m)-\(d)"
    }

    /// Parses a `yyyy-MM-dd` string; returns `nil` for anything malformed.
    static func parse(_ s: String) -> DemoDate? {
        let parts = s.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3,
              let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]),
              m >= 1, m <= 12, d >= 1, d <= daysInMonth(y, m) else {
            return nil
        }
        return DemoDate(y, m, d)
    }

    static func < (lhs: DemoDate, rhs: DemoDate) -> Bool {
        lhs.ordinal < rhs.ordinal
    }
}

/// Floored integer division (matches Python `//` for negative operands, which
/// `addingMonths` relies on when subtracting months across year boundaries).
private func floorDiv(_ a: Int, _ b: Int) -> Int {
    let q = a / b
    let r = a % b
    return (r != 0 && ((r < 0) != (b < 0))) ? q - 1 : q
}

/// Floored modulo, paired with `floorDiv` so the remainder is always in
/// `0..<b` for positive `b`.
private func mod(_ a: Int, _ b: Int) -> Int {
    let r = a % b
    return (r != 0 && ((r < 0) != (b < 0))) ? r + b : r
}
