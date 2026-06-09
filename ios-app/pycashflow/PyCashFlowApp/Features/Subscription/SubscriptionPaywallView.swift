import SwiftUI
import StoreKit

struct SubscriptionPaywallView: View {
    @EnvironmentObject var session: SessionManager
    @StateObject private var manager = StoreKitSubscriptionManager()
    @State private var cloudEmail: String
    private let showsEmailField: Bool

    init(prefilledEmail: String? = nil, showsEmailField: Bool = true) {
        _cloudEmail = State(initialValue: prefilledEmail ?? "")
        self.showsEmailField = showsEmailField
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if showsEmailField {
                    Text("Enter the email address you would like to use for your PyCashFlow Cloud account.")
                        .font(.footnote)
                        .foregroundStyle(AppTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    TextField("Cloud account email", text: $cloudEmail)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                        .foregroundStyle(AppTheme.textPrimary)
                } else if !resolvedEmail.isEmpty {
                    statusLine(label: "Cloud account email", value: resolvedEmail)
                        .cardRow()
                }

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
                            SubscriptionDisclosure(product: product)
                            Text("Your 7 day free trial begins when activated. The \(product.displayPrice) subscription begins after the 7 day trial if not cancelled.")
                                .font(.footnote)
                                .foregroundStyle(AppTheme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                            Button("Start 7-Day Free Trial") {
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
            if showsEmailField && cloudEmail.isEmpty {
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
