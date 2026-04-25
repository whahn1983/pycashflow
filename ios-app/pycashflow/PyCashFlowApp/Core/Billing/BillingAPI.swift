import Foundation

struct AppStoreVerificationPayload: Encodable {
    struct TransactionPayload: Encodable {
        let id: String
        let original_transaction_id: String
        let product_id: String
        let purchase_date: String
        let expiry_date: String?
        let signed_transaction_info: String?
    }

    let email: String
    let receipt_data: String
    let expiry_date: String?
    let transaction: TransactionPayload
}

enum BillingAPI {
    static func fetchBillingStatus(token: String) async throws -> BillingStatusDTO {
        let response: APIEnvelope<BillingStatusDTO> = try await APIClient.shared.request(
            "billing/status",
            token: token,
            as: APIEnvelope<BillingStatusDTO>.self
        )
        return response.data
    }

    static func verifyAppStorePurchase(token: String?, payload: AppStoreVerificationPayload) async throws -> AppStoreVerificationResponseDTO {
        let response: APIEnvelope<AppStoreVerificationResponseDTO> = try await APIClient.shared.request(
            "billing/verify-appstore",
            method: "POST",
            token: token,
            body: payload,
            as: APIEnvelope<AppStoreVerificationResponseDTO>.self
        )
        return response.data
    }
}
