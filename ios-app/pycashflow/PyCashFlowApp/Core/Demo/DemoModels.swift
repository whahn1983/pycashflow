import Foundation

/// Local, on-device data model for Demo mode. Everything here is stored only in
/// `UserDefaults` on the device (via `DemoStore`) and never leaves the app —
/// there is no backend, sync, Plaid, or AI in Demo mode.

struct DemoSchedule: Identifiable, Codable, Equatable {
    let id: Int
    var name: String
    var amount: Decimal
    var type: String
    var frequency: String
    /// `yyyy-MM-dd`.
    var startDate: String

    var amountString: String { DemoAmount.string(amount) }
}

struct DemoScenario: Identifiable, Codable, Equatable {
    let id: Int
    var name: String
    var amount: Decimal
    var type: String
    var frequency: String
    /// `yyyy-MM-dd`.
    var startDate: String

    var amountString: String { DemoAmount.string(amount) }
}

struct DemoHold: Identifiable, Codable, Equatable {
    let id: Int
    var name: String
    var amount: Decimal
    var type: String

    var amountString: String { DemoAmount.string(amount) }
}

struct DemoSkip: Identifiable, Codable, Equatable {
    let id: Int
    var name: String
    var amount: Decimal
    var type: String
    /// `yyyy-MM-dd`.
    var date: String

    var amountString: String { DemoAmount.string(amount) }
}

struct DemoBalanceEntry: Identifiable, Codable, Equatable {
    let id: Int
    var amount: Decimal
    /// `yyyy-MM-dd`.
    var date: String

    var amountString: String { DemoAmount.string(amount) }
}

/// The full persisted Demo-mode state.
struct DemoState: Codable, Equatable {
    var balances: [DemoBalanceEntry] = []
    var schedules: [DemoSchedule] = []
    var scenarios: [DemoScenario] = []
    var holds: [DemoHold] = []
    var skips: [DemoSkip] = []
    /// Monotonic id source shared across all entities.
    var nextID: Int = 1
}
