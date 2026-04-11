import SwiftUI
import StoreKit

struct SubscriptionPaywallView: View {
    @EnvironmentObject var session: SessionManager
    @StateObject private var manager = StoreKitSubscriptionManager()

    let message: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Subscription Required")
                    .font(.title.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                Text(message)
                    .foregroundStyle(AppTheme.textSecondary)
                    .surfaceCard()

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
                                Task { await manager.purchase(product, session: session) }
                            }
                            .buttonStyle(PrimaryButtonStyle())
                            .disabled(manager.isBusy)
                        }
                        .surfaceCard()
                    }
                }

                Button("Restore Purchases") {
                    Task { await manager.restorePurchases(session: session) }
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
            }
            .padding(20)
        }
        .appBackground()
        .task {
            await manager.loadProducts()
        }
        .navigationTitle("Subscription")
    }
}
