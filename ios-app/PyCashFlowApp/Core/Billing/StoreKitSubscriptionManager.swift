import Foundation
import StoreKit

@MainActor
final class StoreKitSubscriptionManager: ObservableObject {
    @Published var availableProducts: [Product] = []
    @Published var isBusy = false
    @Published var errorMessage: String?
    @Published var statusMessage: String?

    func loadProducts() async {
        guard !AppEnvironment.appStoreProductIDs.isEmpty else {
            errorMessage = "Subscription products are not configured for this build."
            return
        }

        do {
            availableProducts = try await Product.products(for: AppEnvironment.appStoreProductIDs)
                .sorted { $0.displayPrice < $1.displayPrice }
            if availableProducts.isEmpty {
                errorMessage = "No App Store products are currently available."
            } else {
                errorMessage = nil
            }
        } catch {
            errorMessage = "Unable to load App Store products."
        }
    }

    func purchase(_ product: Product, email: String, token: String?) async {
        guard !email.isEmpty else {
            errorMessage = "Email is required to activate a hosted cloud account."
            return
        }

        isBusy = true
        errorMessage = nil
        statusMessage = "Completing purchase..."

        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)
                try await submit(transaction: transaction, email: email, token: token)
                await transaction.finish()
                statusMessage = "Purchase verified with backend."
            case .pending:
                statusMessage = "Purchase pending approval."
            case .userCancelled:
                statusMessage = "Purchase cancelled."
            @unknown default:
                errorMessage = "Purchase failed due to an unknown StoreKit result."
            }
        } catch {
            errorMessage = "Purchase could not be verified with backend."
        }

        isBusy = false
    }

    func restorePurchases(email: String, token: String?) async {
        guard !email.isEmpty else {
            errorMessage = "Email is required to restore a hosted cloud account."
            return
        }

        isBusy = true
        errorMessage = nil
        statusMessage = "Restoring App Store purchases..."

        do {
            try await AppStore.sync()
            let transactions = try await currentVerifiedTransactions()
            guard let latest = transactions.max(by: { $0.purchaseDate < $1.purchaseDate }) else {
                errorMessage = "No active App Store purchases were found to restore."
                isBusy = false
                return
            }

            try await submit(transaction: latest, email: email, token: token)
            statusMessage = "Restore verified with backend."
        } catch {
            errorMessage = "Restore failed. Please try again."
        }

        isBusy = false
    }

    private func submit(transaction: StoreKit.Transaction, email: String, token: String?) async throws {
        let receiptData: String
        if let receiptURL = Bundle.main.appStoreReceiptURL,
           let data = try? Data(contentsOf: receiptURL) {
            receiptData = data.base64EncodedString()
        } else {
            receiptData = ""
        }

        let expiryISO = transaction.expirationDate.map(Self.isoDate)
        let payload = AppStoreVerificationPayload(
            email: email,
            receipt_data: receiptData,
            expiry_date: expiryISO,
            transaction: .init(
                id: String(transaction.id),
                original_id: String(transaction.originalID),
                product_id: transaction.productID,
                purchase_date: Self.isoDate(transaction.purchaseDate),
                expiry_date: expiryISO,
                signed_transaction_info: transaction.jwsRepresentation
            )
        )

        _ = try await BillingAPI.verifyAppStorePurchase(token: token, payload: payload)
    }

    private func currentVerifiedTransactions() async throws -> [StoreKit.Transaction] {
        var items: [StoreKit.Transaction] = []
        for await entitlement in StoreKit.Transaction.currentEntitlements {
            let transaction = try checkVerified(entitlement)
            items.append(transaction)
        }
        return items
    }

    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified:
            throw APIErrorEnvelope(error: "Unverified App Store transaction", code: "storekit_unverified", status: 422, fields: nil)
        case .verified(let safe):
            return safe
        }
    }

    private static func isoDate(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }
}
