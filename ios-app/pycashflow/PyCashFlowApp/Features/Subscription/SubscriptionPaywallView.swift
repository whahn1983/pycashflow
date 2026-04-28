import SwiftUI
import StoreKit

struct SubscriptionPaywallView: View {
    @EnvironmentObject var session: SessionManager
    @StateObject private var manager = StoreKitSubscriptionManager()
    @State private var cloudEmail = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Subscription Required")
                    .font(.title.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                Text("App Store subscription is only for PyCashFlow Cloud account activation.")
                    .foregroundStyle(AppTheme.textSecondary)
                    .cardRow()

                VStack(alignment: .leading, spacing: 8) {
                    Text(SubscriptionDisclosure.title)
                        .font(.headline)
                        .foregroundStyle(AppTheme.textPrimary)

                    Text(SubscriptionDisclosure.price)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(AppTheme.textPrimary)

                    Text(SubscriptionDisclosure.durationAndType)
                        .foregroundStyle(AppTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(SubscriptionDisclosure.renewalNotice)
                        .font(.footnote)
                        .foregroundStyle(AppTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    VStack(alignment: .leading, spacing: 6) {
                        Link(SubscriptionDisclosure.termsTitle, destination: SubscriptionDisclosure.termsURL)
                        Link(SubscriptionDisclosure.privacyTitle, destination: SubscriptionDisclosure.privacyURL)
                    }
                    .font(.footnote.weight(.semibold))
                }
                .cardRow()

                TextField("Cloud account email", text: $cloudEmail)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(AppTheme.textPrimary)

                if let status = session.billingStatus {
                    VStack(alignment: .leading, spacing: 8) {
                        statusLine(label: "Status", value: status.subscription_status ?? "inactive")
                        statusLine(label: "Source", value: status.subscription_source ?? "none")
                        if let expiry = status.subscription_expiry {
                            statusLine(label: "Expires", value: expiry)
                        }
                    }
                    .cardRow()
                }

                if manager.availableProducts.isEmpty {
                    Text("No App Store products available.")
                        .foregroundStyle(AppTheme.textMuted)
                        .cardRow()
                } else {
                    ForEach(manager.availableProducts, id: \.id) { product in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(product.displayName)
                                .font(.headline)
                                .foregroundStyle(AppTheme.textPrimary)
                                .lineLimit(2)
                                .minimumScaleFactor(0.85)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(product.description)
                                .foregroundStyle(AppTheme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
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
                        .cardRow()
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

                if let statusMessage = manager.statusMessage {
                    Text(statusMessage)
                        .foregroundStyle(AppTheme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let errorMessage = manager.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
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

    private func statusLine(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .foregroundStyle(AppTheme.textMuted)
            Text(value)
                .foregroundStyle(AppTheme.textSecondary)
                .lineLimit(2)
                .minimumScaleFactor(0.8)
                .multilineTextAlignment(.trailing)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
    }
}
