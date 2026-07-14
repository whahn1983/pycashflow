import Foundation

/// Standalone re-implementation of the PyCashFlow cash-flow projection
/// (`app/cashflow.py`: `calc_schedule` → `calc_transactions` →
/// `calculate_cash_risk_score`) used only by iOS **Demo mode**, which runs with
/// no backend.
///
/// The algorithm mirrors the backend's read-only (`commit=False`) path exactly.
/// Because Demo mode never advances a schedule's stored `startdate` (there is no
/// server housekeeping), a schedule's `firstdate` always equals its `startdate`,
/// and only `firstdate.day` is ever consulted — so the intended day-of-month is
/// taken directly from `startDate.day`.
///
/// This port was fuzz-verified field-for-field against the real backend across
/// tens of thousands of randomized cases and many calendar positions (month
/// ends, leap days, weekends, year boundaries). See
/// `DemoProjectionTests` for the embedded ground-truth vectors.
enum DemoProjectionEngine {

    // MARK: Inputs

    struct Item {
        let name: String
        let startDate: DemoDate
        let frequency: String
        let amount: Decimal
        let type: String
    }

    struct HoldInput {
        let name: String
        let amount: Decimal
        let type: String
    }

    struct SkipInput {
        let name: String
        let date: DemoDate
        let amount: Decimal
        let type: String
    }

    // MARK: Outputs

    struct SeriesPoint {
        let date: DemoDate
        let amount: Double
    }

    struct Transaction {
        let name: String
        let type: String
        let amount: Decimal
        let date: DemoDate
    }

    struct Risk {
        let score: Int
        let status: String
        let runwayDays: Double?
        let lowestBalance: String
    }

    struct Result {
        /// Running-balance projection using schedules only.
        let scheduleRun: [SeriesPoint]
        /// Running-balance projection using schedules **and** scenarios, or
        /// `nil` when there are no scenarios (mirrors the backend).
        let scenarioRun: [SeriesPoint]?
        /// Individual upcoming transactions in the next 90 days (schedules only).
        let upcoming: [Transaction]
        /// 90-day minimum of `scheduleRun`, formatted as an amount string.
        let minBalance: String
        let risk: Risk
    }

    // MARK: Internal row

    private struct Row {
        let type: String
        let name: String
        let amount: Decimal
        let date: DemoDate
    }

    private static let months = 13
    private static let weeks = 53
    private static let years = 2
    private static let quarters = 4
    private static let biweeks = 27

    // MARK: Entry point

    static func project(
        balance: Decimal,
        schedules: [Item],
        scenarios: [Item],
        holds: [HoldInput],
        skips: [SkipInput],
        today: DemoDate
    ) -> Result {
        var total: [Row] = []
        var totalScenario: [Row] = []

        // Schedule rows feed both the schedule-only and the schedule+scenario
        // projections; scenario rows feed only the latter.
        for s in schedules {
            let rows = expandRows(s, today: today)
            total.append(contentsOf: rows)
            totalScenario.append(contentsOf: rows)
        }
        for s in scenarios {
            totalScenario.append(contentsOf: expandRows(s, today: today))
        }

        let tomorrow = today.addingDays(1)
        for h in holds {
            let row = Row(type: h.type, name: h.name, amount: h.amount, date: tomorrow)
            total.append(row)
            totalScenario.append(row)
        }
        for sk in skips {
            if sk.date < today { continue }
            let row = Row(type: sk.type, name: sk.name, amount: sk.amount, date: sk.date)
            total.append(row)
            totalScenario.append(row)
        }

        let (upcoming, scheduleRun) = calcTransactions(balance: balance, total: total, today: today)
        var scenarioRun: [SeriesPoint]? = nil
        if !scenarios.isEmpty {
            scenarioRun = calcTransactions(balance: balance, total: totalScenario, today: today).run
        }

        // min_balance: 90-day minimum of the schedule run.
        let horizon90 = today.addingDays(90)
        let minBalanceValue: Double
        if scheduleRun.isEmpty {
            minBalanceValue = doubleValue(balance)
        } else {
            let within = scheduleRun.filter { $0.date <= horizon90 }
            let pool = within.isEmpty ? scheduleRun : within
            minBalanceValue = pool.map(\.amount).min() ?? doubleValue(balance)
        }

        let risk = calcRisk(balance: balance, run: scheduleRun, today: today)

        return Result(
            scheduleRun: scheduleRun,
            scenarioRun: scenarioRun,
            upcoming: upcoming,
            minBalance: DemoAmount.string(fromDouble: minBalanceValue),
            risk: risk
        )
    }

    // MARK: calc_schedule (per-item expansion)

    private static func expandRows(_ item: Item, today: DemoDate) -> [Row] {
        let firstDay = item.startDate.day  // firstdate == startdate in Demo mode
        var rows: [Row] = []

        func push(_ date: DemoDate) {
            rows.append(Row(type: item.type, name: item.name, amount: item.amount, date: date))
        }

        switch item.frequency {
        case "Monthly":
            let start = fastForward(
                item.startDate,
                window: { $0.addingMonths(months - 1) },
                step: { $0.addingMonths(1) },
                today: today
            )
            for k in 0..<months {
                var fd = start.addingMonths(k)
                fd = restoreDay(fd, firstDay: firstDay)
                push(item.type == "Income" ? fd.rolledBackToBusinessDay : fd.rolledForwardToBusinessDay)
            }

        case "Weekly":
            let start = fastForward(
                item.startDate,
                window: { $0.addingDays(7 * (weeks - 1)) },
                step: { $0.addingDays(7) },
                today: today
            )
            for k in 0..<weeks {
                push(start.addingDays(7 * k).rolledForwardToBusinessDay)
            }

        case "Yearly":
            let start = fastForward(
                item.startDate,
                window: { $0.addingYears(years - 1) },
                step: { $0.addingYears(1) },
                today: today
            )
            for k in 0..<years {
                push(start.addingYears(k).rolledForwardToBusinessDay)
            }

        case "Quarterly":
            let start = fastForward(
                item.startDate,
                window: { $0.addingMonths(3 * (quarters - 1)) },
                step: { $0.addingMonths(3) },
                today: today
            )
            for k in 0..<quarters {
                var fd = start.addingMonths(3 * k)
                fd = restoreDay(fd, firstDay: firstDay)
                push(fd.rolledForwardToBusinessDay)
            }

        case "BiWeekly":
            let start = fastForward(
                item.startDate,
                window: { $0.addingDays(14 * (biweeks - 1)) },
                step: { $0.addingDays(14) },
                today: today
            )
            for k in 0..<biweeks {
                push(start.addingDays(14 * k).rolledForwardToBusinessDay)
            }

        case "Onetime":
            if item.startDate >= today {
                push(item.startDate)
            }

        default:
            break
        }

        return rows
    }

    /// Advances `start` by whole `step` increments until `start + window` moves
    /// past `today`, so a stale start date still yields future projection points
    /// (mirrors `_fast_forward_start`). The iterative stepping intentionally
    /// carries the same day-of-month decay as `dateutil` (e.g. Jan 31 → Feb 28
    /// → Mar 28), which `restoreDay` later compensates for.
    private static func fastForward(
        _ start: DemoDate,
        window: (DemoDate) -> DemoDate,
        step: (DemoDate) -> DemoDate,
        today: DemoDate
    ) -> DemoDate {
        var s = start
        for _ in 0..<5000 {
            if window(s) > today { return s }
            s = step(s)
        }
        return s
    }

    /// Reproduces the backend's day-of-month restoration: when month-length
    /// clamping pulled the projected day below the intended day, nudge it back
    /// up by at most three days, stopping at the first invalid day (the backend
    /// catches the resulting `ValueError`).
    private static func restoreDay(_ date: DemoDate, firstDay: Int) -> DemoDate {
        var fd = date
        var fdd = date.day
        if firstDay > fdd {
            for _ in 0..<3 {
                fdd += 1
                if firstDay >= fdd {
                    guard let replaced = fd.replacingDay(fdd) else { break }
                    fd = replaced
                }
            }
        }
        return fd
    }

    // MARK: calc_transactions

    private static func calcTransactions(
        balance: Decimal,
        total: [Row],
        today: DemoDate
    ) -> (upcoming: [Transaction], run: [SeriesPoint]) {
        let balanceDouble = doubleValue(balance)
        if total.isEmpty {
            return ([], [SeriesPoint(date: today, amount: balanceDouble)])
        }

        // Stable sort by date (preserves per-date insertion order so the
        // floating-point accumulation order matches the backend).
        let rows = total.enumerated()
            .sorted { lhs, rhs in
                if lhs.element.date.ordinal != rhs.element.date.ordinal {
                    return lhs.element.date.ordinal < rhs.element.date.ordinal
                }
                return lhs.offset < rhs.offset
            }
            .map(\.element)

        let horizon = today.addingDays(90)
        var upcoming: [Transaction] = []
        for r in rows where r.date > today && r.date < horizon && !r.name.contains("(SKIP)") {
            upcoming.append(Transaction(name: r.name, type: r.type, amount: r.amount, date: r.date))
        }

        // Net change per date (Expense negated), in ascending date order.
        var netByOrdinal: [Int: Double] = [:]
        var orderedDates: [DemoDate] = []
        for r in rows {
            var amt = doubleValue(r.amount)
            if r.type == "Expense" { amt = -amt }
            if netByOrdinal[r.date.ordinal] == nil {
                orderedDates.append(r.date)
            }
            netByOrdinal[r.date.ordinal, default: 0] += amt
        }

        var runBalance = balanceDouble
        var run: [SeriesPoint] = [SeriesPoint(date: today, amount: runBalance)]
        for date in orderedDates where date > today {
            runBalance += netByOrdinal[date.ordinal] ?? 0
            run.append(SeriesPoint(date: date, amount: runBalance))
        }
        return (upcoming, run)
    }

    // MARK: calculate_cash_risk_score

    private static func calcRisk(balance: Decimal, run: [SeriesPoint], today: DemoDate) -> Risk {
        let current = doubleValue(balance)

        if current <= 0 {
            return Risk(score: 0, status: "Critical", runwayDays: 0,
                        lowestBalance: DemoAmount.string(fromDouble: current))
        }
        if run.isEmpty {
            return Risk(score: 50, status: "Watch", runwayDays: 0,
                        lowestBalance: DemoAmount.string(fromDouble: current))
        }

        if run.count == 1 {
            let row = run[0]
            let sb = row.amount
            let daysToRow = max(0, row.date.ordinal - today.ordinal)
            let lowest = min(current, sb)
            let balDelta = current - sb
            let ade = balDelta > 0 ? balDelta / Double(max(1, daysToRow)) : 0
            let runway: Double? = ade > 0 ? DemoRounding.pythonRound(current / ade, 1) : nil
            let score: Int
            let status: String
            if sb < 0 {
                score = 0; status = "Critical"
            } else {
                score = 50; status = "Watch"
            }
            return Risk(score: score, status: status, runwayDays: runway,
                        lowestBalance: DemoAmount.string(fromPyRounded: lowest))
        }

        // Multi-point.
        let rows = run.sorted { $0.date.ordinal < $1.date.ordinal }
        let horizon = today.addingDays(90)
        var run90 = rows.filter { $0.date <= horizon }
        if run90.isEmpty { run90 = rows }
        let nearHorizon = today.addingDays(14)
        let run14 = rows.filter { $0.date <= nearHorizon }

        let amounts = run90.map(\.amount)
        var minIdx = 0
        for i in amounts.indices where amounts[i] < amounts[minIdx] { minIdx = i }
        let lowest = amounts[minIdx]

        let totalDays = max(1, run90[run90.count - 1].date.ordinal - run90[0].date.ordinal)
        var expenseTotal = 0.0
        var hadDownwardMove = false
        for i in 1..<amounts.count where amounts[i] < amounts[i - 1] {
            expenseTotal += abs(amounts[i] - amounts[i - 1])
            hadDownwardMove = true
        }
        // The backend's `avg_daily_expense` is a numpy float when there was at
        // least one downward move; the `== 0 → 1.0` fallback makes it a plain
        // Python float. This selects which rounding regime the derived outputs
        // (runway, score) follow.
        var adeNumpy = hadDownwardMove
        var ade = totalDays > 0 ? expenseTotal / Double(totalDays) : 1.0
        if ade == 0 { ade = 1.0; adeNumpy = false }
        let round1: (Double) -> Double = adeNumpy
            ? { DemoRounding.numpyRound($0, 1) }
            : { DemoRounding.pythonRound($0, 1) }
        let round0: (Double) -> Double = adeNumpy
            ? { DemoRounding.numpyRound($0, 0) }
            : { DemoRounding.pythonRound($0, 0) }

        let avgMonthly = ade * 30
        let runway = current / ade
        let threshold = avgMonthly

        // 1. Minimum balance ratio (35%)
        let ratio = avgMonthly > 0 ? lowest / avgMonthly : 1.0
        let minBalanceScore: Double
        if ratio >= 1.5 { minBalanceScore = 100 }
        else if ratio >= 1.0 { minBalanceScore = 75 + (ratio - 1.0) / 0.5 * 25 }
        else if ratio >= 0.5 { minBalanceScore = 40 + (ratio - 0.5) / 0.5 * 35 }
        else if ratio >= 0.0 { minBalanceScore = ratio / 0.5 * 40 }
        else { minBalanceScore = 0 }

        // 2. Days below liquidity threshold (25%)
        var daysBelow = 0
        for i in run90.indices where run90[i].amount < threshold {
            let seg: Int
            if i < run90.count - 1 {
                seg = run90[i + 1].date.ordinal - run90[i].date.ordinal
            } else {
                seg = max(0, horizon.ordinal - run90[i].date.ordinal)
            }
            daysBelow += max(0, seg)
        }
        let pctBelow = Double(daysBelow) / 90.0
        let daysBelowScore = max(0.0, 100.0 - (pctBelow / 0.5) * 100.0)

        // 3. Recovery speed (20%)
        let recoveryScore: Double
        if lowest >= threshold {
            recoveryScore = 100
        } else {
            let lowestDate = run90[minIdx].date
            let postLow = run90.filter { $0.date.ordinal >= lowestDate.ordinal }
            if let recovered = postLow.first(where: { $0.amount >= threshold }) {
                let rday = max(0, recovered.date.ordinal - lowestDate.ordinal)
                if rday <= 7 { recoveryScore = 90 + Double(7 - rday) / 7.0 * 10 }
                else if rday <= 30 { recoveryScore = 50 + Double(30 - rday) / 23.0 * 40 }
                else { recoveryScore = max(0.0, 50 - Double(rday - 30) / 60.0 * 50) }
            } else {
                recoveryScore = 0
            }
        }

        // 4. Near-term liquidity buffer (14 days) (20%)
        let nearMin = run14.isEmpty ? current : (run14.map(\.amount).min() ?? current)
        let ntRatio = avgMonthly > 0 ? nearMin / avgMonthly : 1.0
        let nearTermScore: Double
        if ntRatio >= 1.5 { nearTermScore = 100 }
        else if ntRatio >= 1.0 { nearTermScore = 75 + (ntRatio - 1.0) / 0.5 * 25 }
        else if ntRatio >= 0.5 { nearTermScore = 40 + (ntRatio - 0.5) / 0.5 * 35 }
        else if ntRatio >= 0.0 { nearTermScore = ntRatio / 0.5 * 40 }
        else { nearTermScore = 0 }

        let composite = minBalanceScore * 0.35 + daysBelowScore * 0.25
            + recoveryScore * 0.20 + nearTermScore * 0.20
        let score = Int(max(0.0, min(100.0, round0(composite))))

        let status: String
        if score >= 80 { status = "Safe" }
        else if score >= 60 { status = "Stable" }
        else if score >= 40 { status = "Watch" }
        else if score >= 20 { status = "Risk" }
        else { status = "Critical" }

        return Risk(
            score: score,
            status: status,
            runwayDays: round1(runway),
            lowestBalance: DemoAmount.string(fromPyRounded: lowest)
        )
    }

    // MARK: Helpers

    static func doubleValue(_ d: Decimal) -> Double {
        NSDecimalNumber(decimal: d).doubleValue
    }
}
