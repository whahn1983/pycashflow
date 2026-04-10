import Foundation

struct APIEnvelope<T: Decodable>: Decodable { let data: T }
struct APIListEnvelope<T: Decodable>: Decodable { let data: [T]; let meta: Meta? }
struct Meta: Decodable { let total: Int?; let limit: Int?; let offset: Int? }

struct APIErrorEnvelope: Decodable, Error {
    let error: String
    let code: String
    let status: Int
    let fields: [String: String]?
}

struct EmptyResponse: Decodable {}

struct UserDTO: Decodable {
    let id: Int
    let email: String
    let name: String
    let is_admin: Bool
    let is_global_admin: Bool?
    let twofa_enabled: Bool?
    let is_guest: Bool
}

struct LoginResponseDTO: Decodable {
    let token: String?
    let twofa_required: Bool?
    let challenge: String?
    let user: UserDTO
}

struct DashboardDTO: Decodable {
    let balance: String
    let balance_date: String
    let risk_v2: RiskScoreDTO?
    let upcoming_transactions: [TransactionDTO]
    let min_balance: String
    let ai_last_updated: String?
}

struct RiskScoreDTO: Decodable {
    let score: Int
    let status: String
    let runway_days: Int
    let lowest_balance: String
}

struct TransactionDTO: Decodable, Identifiable {
    let name: String
    let type: String
    let amount: String
    let date: String

    var id: String { "\(name)-\(date)-\(amount)" }
}

struct BalanceDTO: Decodable, Identifiable {
    let id: Int?
    let amount: String
    let date: String
}

struct ScheduleDTO: Decodable, Identifiable {
    let id: Int
    let name: String
    let amount: String
    let type: String
    let frequency: String
    let start_date: String
}

struct ScenarioDTO: Decodable, Identifiable {
    let id: Int
    let name: String
    let amount: String
    let type: String
    let frequency: String
    let start_date: String
}

struct ProjectionPointDTO: Decodable, Identifiable {
    let date: String
    let amount: String

    var id: String { "\(date)-\(amount)" }
}

struct ProjectionsDTO: Decodable {
    let schedule: [ProjectionPointDTO]
    let scenario: [ProjectionPointDTO]?
}

struct SettingsDTO: Decodable {
    struct SettingsUserDTO: Decodable {
        let id: Int
        let email: String
        let name: String
        let is_admin: Bool
        let is_guest: Bool
    }

    struct SettingsAppDTO: Decodable {
        let version: String
        let python_version: String
    }

    struct SettingsAIDTO: Decodable {
        let configured: Bool
        let model: String?
        let last_updated: String?
    }

    let user: SettingsUserDTO
    let app: SettingsAppDTO
    let ai: SettingsAIDTO
}

struct InsightsDTO: Decodable {
    let configured: Bool
    let insights: [String]?
    let last_updated: String?
    let model: String?
}
