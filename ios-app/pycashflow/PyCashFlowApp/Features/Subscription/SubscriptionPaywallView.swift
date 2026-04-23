import SwiftUI
import StoreKit

struct SubscriptionPaywallView: View {
    @EnvironmentObject var session: SessionManager
    @StateObject private var manager = StoreKitSubscriptionManager()
    @State private var cloudEmail = ""

    let message: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Subscription Required")
                    .font(.title.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                Text("App Store subscription is only for PyCashFlow Cloud account activation and maintenance.")
                    .foregroundStyle(AppTheme.textSecondary)
                    .surfaceCard()

                Text(message)
                    .foregroundStyle(AppTheme.textSecondary)
                    .surfaceCard()

                TextField("Cloud account email", text: $cloudEmail)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(AppTheme.textPrimary)

                if let status = session.billingStatus {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Status: \(status.subscription_status ?? "inactive")")
                        Text("Source: \(status.subscription_source ?? "none")")
                        if let expiry = status.subscription_expiry {
                            Text("Expires: \(expiry)")
                        }
                    }
                    .foregroundStyle(AppTheme.textSecondary)
                    .surfaceCard()
                }

                if manager.availableProducts.isEmpty {
                    Text("No App Store products available.")
                        .foregroundStyle(AppTheme.textMuted)
                        .surfaceCard()
                } else {
                    ForEach(manager.availableProducts, id: \.id) { product in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(product.displayName)
                                .foregroundStyle(AppTheme.textPrimary)
                            Text(product.description)
                                .foregroundStyle(AppTheme.textSecondary)
                            Button("Subscribe • \(product.displayPrice)") {
                                Task {
                                    await manager.purchase(
                                        product,
                                        email: resolvedEmail,
                                        token: session.token
                                    )
                                    if session.isAuthenticated {
                                        await session.refreshSubscriptionState(forceProfileRefresh: true)
                                    }
                                }
                            }
                            .buttonStyle(PrimaryButtonStyle())
                            .disabled(manager.isBusy)
                        }
                        .surfaceCard()
                    }
                }

                Button("Restore Purchases") {
                    Task {
                        await manager.restorePurchases(email: resolvedEmail, token: session.token)
                        if session.isAuthenticated {
                            await session.refreshSubscriptionState(forceProfileRefresh: true)
                        }
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(manager.isBusy)

                Button("Re-check Account Status") {
                    Task { await session.refreshSubscriptionState(forceProfileRefresh: true) }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(manager.isBusy)

                if let statusMessage = manager.statusMessage {
                    Text(statusMessage)
                        .foregroundStyle(AppTheme.textSecondary)
                }

                if let errorMessage = manager.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(AppTheme.danger)
                }

                Button("Logout", role: .destructive) {
                    session.clear()
                }
                .buttonStyle(PrimaryButtonStyle())

                Button("Switch to Self-Hosted Mode") {
                    session.switchMode(.selfHosted)
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            .padding(20)
        }
        .appBackground()
        .task {
            await manager.loadProducts()
            if cloudEmail.isEmpty {
                cloudEmail = session.user?.email ?? ""
            }
        }
        .navigationTitle("Subscription")
    }

    private var resolvedEmail: String {
        cloudEmail.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
