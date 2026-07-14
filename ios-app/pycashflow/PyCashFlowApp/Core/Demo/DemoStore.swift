import Foundation
import Combine

/// Owns all Demo-mode data: loads/saves it locally (no backend, no sync) and
/// runs the standalone projection engine. Validation mirrors the backend
/// (`app/api/routes/data.py`) so Demo mode behaves like the real app.
@MainActor
final class DemoStore: ObservableObject {
    @Published private(set) var state: DemoState

    private let defaultsKey = "DEMO_STATE_V1"
    private let defaults: UserDefaults

    static let validTypes = ["Expense", "Income"]
    static let validFrequencies = ["Monthly", "Quarterly", "Yearly", "Weekly", "BiWeekly", "Onetime"]
    private static let maxNameLength = 100

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: defaultsKey),
           let decoded = try? JSONDecoder().decode(DemoState.self, from: data) {
            state = decoded
        } else {
            state = DemoState()
        }
    }

    // MARK: Persistence

    private func persist() {
        if let data = try? JSONEncoder().encode(state) {
            defaults.set(data, forKey: defaultsKey)
        }
    }

    private func nextID() -> Int {
        let id = state.nextID
        state.nextID += 1
        return id
    }

    /// Today's date in the device's local calendar.
    static var todayLocal: DemoDate {
        let comps = Calendar.current.dateComponents([.year, .month, .day], from: Date())
        return DemoDate(comps.year ?? 2000, comps.month ?? 1, comps.day ?? 1)
    }

    // MARK: Balance

    var currentBalance: DemoBalanceEntry? {
        state.balances.max { lhs, rhs in
            if lhs.date != rhs.date { return lhs.date < rhs.date }
            return lhs.id < rhs.id
        }
    }

    var balanceHistory: [DemoBalanceEntry] {
        state.balances.sorted { lhs, rhs in
            if lhs.date != rhs.date { return lhs.date > rhs.date }
            return lhs.id > rhs.id
        }
    }

    /// Sets (or updates) the balance for today's date, mirroring the API's
    /// `POST /balance` which stores against the current date.
    @discardableResult
    func setBalance(amountText: String) -> String? {
        guard let amount = Self.parseAmount(amountText) else {
            return "Amount must be a number"
        }
        let today = Self.todayLocal.isoString
        if let index = state.balances.firstIndex(where: { $0.date == today }) {
            state.balances[index].amount = amount
        } else {
            state.balances.append(DemoBalanceEntry(id: nextID(), amount: amount, date: today))
        }
        persist()
        return nil
    }

    // MARK: Schedules

    @discardableResult
    func addSchedule(name: String, amountText: String, type: String, frequency: String, startDate: DemoDate) -> String? {
        if let error = validate(name: name, amountText: amountText, type: type, frequency: frequency) {
            return error
        }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if state.schedules.contains(where: { $0.name == trimmed }) {
            return "Schedule already exists"
        }
        state.schedules.append(DemoSchedule(
            id: nextID(),
            name: trimmed,
            amount: Self.parseAmount(amountText)!,
            type: type,
            frequency: frequency,
            startDate: startDate.isoString
        ))
        persist()
        return nil
    }

    @discardableResult
    func updateSchedule(id: Int, name: String, amountText: String, type: String, frequency: String, startDate: DemoDate) -> String? {
        guard let index = state.schedules.firstIndex(where: { $0.id == id }) else {
            return "Schedule not found"
        }
        if let error = validate(name: name, amountText: amountText, type: type, frequency: frequency) {
            return error
        }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if state.schedules.contains(where: { $0.name == trimmed && $0.id != id }) {
            return "Schedule name already exists"
        }
        state.schedules[index].name = trimmed
        state.schedules[index].amount = Self.parseAmount(amountText)!
        state.schedules[index].type = type
        state.schedules[index].frequency = frequency
        state.schedules[index].startDate = startDate.isoString
        persist()
        return nil
    }

    func deleteSchedule(id: Int) {
        state.schedules.removeAll { $0.id == id }
        persist()
    }

    // MARK: Scenarios

    @discardableResult
    func addScenario(name: String, amountText: String, type: String, frequency: String, startDate: DemoDate) -> String? {
        if let error = validate(name: name, amountText: amountText, type: type, frequency: frequency) {
            return error
        }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if state.scenarios.contains(where: { $0.name == trimmed }) {
            return "Scenario already exists"
        }
        state.scenarios.append(DemoScenario(
            id: nextID(),
            name: trimmed,
            amount: Self.parseAmount(amountText)!,
            type: type,
            frequency: frequency,
            startDate: startDate.isoString
        ))
        persist()
        return nil
    }

    @discardableResult
    func updateScenario(id: Int, name: String, amountText: String, type: String, frequency: String, startDate: DemoDate) -> String? {
        guard let index = state.scenarios.firstIndex(where: { $0.id == id }) else {
            return "Scenario not found"
        }
        if let error = validate(name: name, amountText: amountText, type: type, frequency: frequency) {
            return error
        }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if state.scenarios.contains(where: { $0.name == trimmed && $0.id != id }) {
            return "Scenario name already exists"
        }
        state.scenarios[index].name = trimmed
        state.scenarios[index].amount = Self.parseAmount(amountText)!
        state.scenarios[index].type = type
        state.scenarios[index].frequency = frequency
        state.scenarios[index].startDate = startDate.isoString
        persist()
        return nil
    }

    func deleteScenario(id: Int) {
        state.scenarios.removeAll { $0.id == id }
        persist()
    }

    // MARK: Holds

    /// Creates a hold from a schedule (copies its name/type/amount), mirroring
    /// `POST /holds` with a `schedule_id`.
    @discardableResult
    func addHold(fromScheduleID scheduleID: Int) -> String? {
        guard let schedule = state.schedules.first(where: { $0.id == scheduleID }) else {
            return "Schedule not found"
        }
        state.holds.append(DemoHold(
            id: nextID(),
            name: schedule.name,
            amount: schedule.amount,
            type: schedule.type
        ))
        persist()
        return nil
    }

    func deleteHold(id: Int) {
        state.holds.removeAll { $0.id == id }
        persist()
    }

    // MARK: Skips

    /// Creates a skip from a schedule by projecting that schedule in isolation
    /// and taking its next upcoming transaction, mirroring `POST /skips` with a
    /// `schedule_id` (a skip is the inverse transaction that cancels the
    /// original occurrence).
    @discardableResult
    func addSkip(fromScheduleID scheduleID: Int) -> String? {
        guard let schedule = state.schedules.first(where: { $0.id == scheduleID }) else {
            return "Schedule not found"
        }
        guard let startDate = DemoDate.parse(schedule.startDate) else {
            return "No upcoming transaction found for this schedule"
        }
        let isolated = DemoProjectionEngine.Item(
            name: schedule.name,
            startDate: startDate,
            frequency: schedule.frequency,
            amount: schedule.amount,
            type: schedule.type
        )
        let result = DemoProjectionEngine.project(
            balance: 0,
            schedules: [isolated],
            scenarios: [],
            holds: [],
            skips: [],
            today: Self.todayLocal
        )
        guard let tx = result.upcoming.first else {
            return "No upcoming transaction found for this schedule"
        }
        state.skips.append(DemoSkip(
            id: nextID(),
            name: "\(tx.name) (SKIP)",
            amount: tx.amount,
            type: tx.type == "Expense" ? "Income" : "Expense",
            date: tx.date.isoString
        ))
        persist()
        return nil
    }

    func deleteSkip(id: Int) {
        state.skips.removeAll { $0.id == id }
        persist()
    }

    // MARK: Projection

    func projection(today: DemoDate = DemoStore.todayLocal) -> DemoProjectionEngine.Result {
        let balance = currentBalance?.amount ?? 0
        let schedules = state.schedules.compactMap { s -> DemoProjectionEngine.Item? in
            guard let date = DemoDate.parse(s.startDate) else { return nil }
            return DemoProjectionEngine.Item(name: s.name, startDate: date, frequency: s.frequency, amount: s.amount, type: s.type)
        }
        let scenarios = state.scenarios.compactMap { s -> DemoProjectionEngine.Item? in
            guard let date = DemoDate.parse(s.startDate) else { return nil }
            return DemoProjectionEngine.Item(name: s.name, startDate: date, frequency: s.frequency, amount: s.amount, type: s.type)
        }
        let holds = state.holds.map {
            DemoProjectionEngine.HoldInput(name: $0.name, amount: $0.amount, type: $0.type)
        }
        let skips = state.skips.compactMap { skip -> DemoProjectionEngine.SkipInput? in
            guard let date = DemoDate.parse(skip.date) else { return nil }
            return DemoProjectionEngine.SkipInput(name: skip.name, date: date, amount: skip.amount, type: skip.type)
        }
        return DemoProjectionEngine.project(
            balance: balance,
            schedules: schedules,
            scenarios: scenarios,
            holds: holds,
            skips: skips,
            today: today
        )
    }

    /// Clears all Demo data (used when the user chooses to reset).
    func resetAll() {
        state = DemoState()
        persist()
    }

    // MARK: Helpers

    private func validate(name: String, amountText: String, type: String, frequency: String) -> String? {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || trimmed.count > Self.maxNameLength {
            return "Name must be between 1 and \(Self.maxNameLength) characters"
        }
        if Self.parseAmount(amountText) == nil {
            return "Amount must be a number"
        }
        if !Self.validTypes.contains(type) {
            return "Invalid type"
        }
        if !Self.validFrequencies.contains(frequency) {
            return "Invalid frequency"
        }
        return nil
    }

    /// Parses a user-entered amount into an exact `Decimal`. Accepts a comma as
    /// the decimal separator (common on non-US keyboards) when unambiguous.
    static func parseAmount(_ text: String) -> Decimal? {
        var trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        if trimmed.contains(",") && !trimmed.contains(".") {
            trimmed = trimmed.replacingOccurrences(of: ",", with: ".")
        }
        // Reject anything that isn't a plain decimal number so behaviour matches
        // the backend's float() validation (which rejects letters, etc.).
        guard let value = Decimal(string: trimmed, locale: Locale(identifier: "en_US_POSIX")),
              trimmed.allSatisfy({ $0.isNumber || $0 == "." || $0 == "-" || $0 == "+" }) else {
            return nil
        }
        return value
    }
}
