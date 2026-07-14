import SwiftUI
import StoreKit

struct SubscriptionPaywallView: View {
    @EnvironmentObject var session: SessionManager
    @EnvironmentObject private var manager: StoreKitSubscriptionManager
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
                    if manager.availableProducts.count > 1 {
                        Text("Choose your plan")
                            .font(.headline)
                            .foregroundStyle(AppTheme.textPrimary)
                    }

                    ForEach(manager.availableProducts, id: \.id) { product in
                        VStack(alignment: .leading, spacing: 8) {
                            if isBestValue(product) {
                                bestValueBadge(savings: savingsPercent(for: product))
                            }
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

    /// A small capsule highlighting the lowest per-month plan, optionally with
    /// how much it saves versus the pricier cadence.
    private func bestValueBadge(savings: Int?) -> some View {
        let label = savings.map { "Best value · Save \($0)%" } ?? "Best value"
        return Text(label)
            .font(.caption.weight(.semibold))
            .foregroundStyle(AppTheme.textPrimary)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(AppTheme.success.opacity(0.9), in: Capsule())
    }

    /// The plan's price normalized to a per-month figure, or `nil` when its
    /// subscription period is unavailable (e.g. in previews).
    private func monthlyEquivalent(for product: Product) -> Decimal? {
        guard let period = product.subscription?.subscriptionPeriod else { return nil }
        return SubscriptionPlanValue.monthlyEquivalentPrice(price: product.price, period: period)
    }

    private var monthlyEquivalents: [Decimal] {
        manager.availableProducts.compactMap { monthlyEquivalent(for: $0) }
    }

    /// True only for the single plan with the lowest per-month cost when more
    /// than one plan is offered, so ties never flag multiple "best" plans.
    private func isBestValue(_ product: Product) -> Bool {
        let values = monthlyEquivalents
        guard manager.availableProducts.count > 1,
              values.count > 1,
              let mine = monthlyEquivalent(for: product),
              let cheapest = values.min(),
              values.filter({ $0 == cheapest }).count == 1 else { return false }
        return mine == cheapest
    }

    private func savingsPercent(for product: Product) -> Int? {
        guard manager.availableProducts.count > 1,
              let mine = monthlyEquivalent(for: product) else { return nil }
        return SubscriptionPlanValue.savingsPercent(monthlyEquivalent: mine, comparedTo: monthlyEquivalents)
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
