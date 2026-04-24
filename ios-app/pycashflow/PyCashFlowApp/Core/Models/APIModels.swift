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
    let subscription_status: String?
    let subscription_source: String?
    let subscription_expiry: String?
}

struct LoginResponseDTO: Decodable {
    let token: String?
    let twofa_required: Bool?
    let challenge: String?
    let user: UserDTO
}

struct BillingStatusDTO: Decodable {
    let user_id: Int?
    let is_active: Bool?
    let effective_is_active: Bool?
    let subscription_status: String?
    let subscription_source: String?
    let subscription_expiry: String?
    let payments_enabled: Bool?
    let is_global_admin: Bool?
    let is_guest: Bool?
    let owner_user_id: Int?

    var effectiveAccessAllowed: Bool {
        if is_global_admin == true {
            return true
        }
        if let effective_is_active {
            return effective_is_active
        }
        return is_active ?? false
    }

    var accessMessage: String {
        let status = subscription_status ?? "inactive"
        if status == "expired" {
            return "Subscription expired. Renew to continue using owner-only features."
        }
        if is_guest == true {
            return "Guest access depends on your account owner's active subscription."
        }
        return "An active subscription is required to continue."
    }
}

struct AppStoreVerificationResponseDTO: Decodable {
    let verification_status: String
    let user_id: Int?
    let subscription_status: String?
    let subscription_source: String?
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
    let score: Int?
    let status: String?
    let runway_days: Double?
    let lowest_balance: String?
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

struct InsightItemDTO: Decodable, Identifiable {
    let type: String?
    let severity: String?
    let title: String?
    let description: String?

    var id: String { "\(title ?? "")-\(description ?? "")" }
}

struct InsightsDTO: Decodable {
    let configured: Bool
    let insights: [InsightItemDTO]?
    let last_updated: String?
    let model: String?

    private enum CodingKeys: String, CodingKey {
        case configured, insights, last_updated, model
    }

    private struct InsightsWrapper: Decodable {
        let insights: [InsightItemDTO]?
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        configured = try container.decodeIfPresent(Bool.self, forKey: .configured) ?? false
        last_updated = try container.decodeIfPresent(String.self, forKey: .last_updated)
        model = try container.decodeIfPresent(String.self, forKey: .model)

        // The backend stores insights as either an array of objects or the
        // OpenAI-shaped wrapper {"insights": [...]}; accept either form.
        if let flat = try? container.decodeIfPresent([InsightItemDTO].self, forKey: .insights) {
            insights = flat
        } else if let wrapped = try? container.decodeIfPresent(InsightsWrapper.self, forKey: .insights) {
            insights = wrapped.insights
        } else {
            insights = nil
        }
    }
}
