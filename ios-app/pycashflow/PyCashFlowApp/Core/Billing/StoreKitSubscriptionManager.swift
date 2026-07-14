import Foundation
import Combine
import StoreKit

@MainActor
final class StoreKitSubscriptionManager: ObservableObject {
    @Published var availableProducts: [Product] = []
    @Published var isBusy = false
    @Published var errorMessage: String?
    @Published var statusMessage: String?

    /// Long-lived task that observes transactions arriving outside the direct
    /// `purchase()` flow (Ask to Buy approvals, renewals, or purchases that were
    /// interrupted by app termination).
    private var updatesListenerTask: Task<Void, Never>?

    /// Account context from the most recent purchase/restore, used to submit
    /// out-of-band transaction updates to the backend.
    private var lastKnownEmail: String?
    private var lastKnownToken: String?

    /// Account context for the signed-in user, derived from the live session
    /// rather than persisted to disk. This lets transactions delivered outside
    /// an explicit purchase/restore (renewals, Ask to Buy approvals, or
    /// purchases redelivered on a later launch) be reconciled with the backend
    /// even when this manager's in-memory context has been lost to a relaunch.
    var accountContextProvider: (() -> AccountContext?)?

    struct AccountContext {
        let email: String
        let token: String?
    }

    /// Guards against the cold-launch and scene-activation paths sweeping
    /// `Transaction.unfinished` at the same time and submitting a transaction twice.
    private var isReprocessing = false

    init() {
        startObservingTransactionUpdates()
    }

    deinit {
        updatesListenerTask?.cancel()
    }

    func loadProducts() async {
        guard !AppEnvironment.appStoreProductIDs.isEmpty else {
            errorMessage = "Subscription products are not configured for this build."
            return
        }

        do {
            // Sort by the numeric price rather than the localized display string
            // so the monthly plan reliably precedes the higher-priced annual plan
            // regardless of currency formatting.
            availableProducts = try await Product.products(for: AppEnvironment.appStoreProductIDs)
                .sorted { $0.price < $1.price }
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
            errorMessage = "Please enter an email address before activating your subscription."
            return
        }
        guard Self.isValidEmail(email) else {
            errorMessage = "Please enter a valid email address to activate your subscription."
            return
        }

        lastKnownEmail = email
        lastKnownToken = token

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
            errorMessage = "Please enter an email address before restoring your subscription."
            return
        }
        guard Self.isValidEmail(email) else {
            errorMessage = "Please enter a valid email address to restore your subscription."
            return
        }

        lastKnownEmail = email
        lastKnownToken = token

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

    /// Starts listening for transaction updates as soon as the manager is
    /// created so successful purchases delivered outside `purchase()` are not
    /// missed.
    private func startObservingTransactionUpdates() {
        guard updatesListenerTask == nil else { return }
        updatesListenerTask = Task { [weak self] in
            for await update in StoreKit.Transaction.updates {
                await self?.handle(transactionUpdate: update)
            }
        }
    }

    /// Submits and finishes any transactions StoreKit is still holding as
    /// unfinished. Call this once account context becomes available (for
    /// example after the session loads its user) so a purchase interrupted by
    /// app termination is reconciled with the backend on the next launch rather
    /// than only the one after that.
    func reprocessPendingTransactions() async {
        guard !isReprocessing else { return }
        isReprocessing = true
        defer { isReprocessing = false }

        for await update in StoreKit.Transaction.unfinished {
            await handle(transactionUpdate: update)
        }
    }

    private func handle(transactionUpdate result: VerificationResult<StoreKit.Transaction>) async {
        guard let transaction = try? checkVerified(result) else { return }

        guard let context = resolvedAccountContext() else {
            // No account context yet. Leave the transaction unfinished so StoreKit
            // redelivers it once the user signs in, activates, or restores a
            // subscription and account context becomes available.
            return
        }

        do {
            try await submit(transaction: transaction, email: context.email, token: context.token)
            await transaction.finish()
            errorMessage = nil
            statusMessage = "Subscription updated from the App Store."
        } catch {
            errorMessage = "A subscription update could not be verified with backend."
        }
    }

    /// Prefers the email/token captured by an in-progress purchase or restore,
    /// then falls back to the signed-in session so context survives relaunches.
    private func resolvedAccountContext() -> AccountContext? {
        if let email = lastKnownEmail, !email.isEmpty {
            return AccountContext(email: email, token: lastKnownToken)
        }
        return accountContextProvider?()
    }

    private func submit(transaction: StoreKit.Transaction, email: String, token: String?) async throws {
        let expiryISO = transaction.expirationDate.map(Self.isoDate)
        let payload = AppStoreVerificationPayload(
            email: email,
            receipt_data: "",
            expiry_date: expiryISO,
            transaction: .init(
                id: String(transaction.id),
                original_transaction_id: String(transaction.originalID),
                product_id: transaction.productID,
                purchase_date: Self.isoDate(transaction.purchaseDate),
                expiry_date: expiryISO,
                signed_transaction_info: Self.signedTransactionInfo(transaction)
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

    private static func isValidEmail(_ email: String) -> Bool {
        let pattern = #"^[^\s@]+@[^\s@]+\.[^\s@]+$"#
        return email.range(of: pattern, options: .regularExpression) != nil
    }

    private static func signedTransactionInfo(_ transaction: StoreKit.Transaction) -> String? {
        String(data: transaction.jsonRepresentation, encoding: .utf8)
    }

    private static func isoDate(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }
}
