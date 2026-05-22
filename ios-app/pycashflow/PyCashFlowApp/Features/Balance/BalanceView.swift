import SwiftUI

struct BalanceView: View {
    @EnvironmentObject var session: SessionManager
    @State private var balance: BalanceDTO?
    @State private var history: [BalanceDTO] = []
    @State private var newAmount = ""
    @State private var errorText: String?
    @State private var statusText: String?
    @State private var isRefreshing: Bool = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let balance {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text("Current Balance")
                                .font(.caption)
                                .foregroundStyle(AppTheme.textMuted)
                            Spacer()
                            Button {
                                Task { await refreshRealtimeBalance() }
                            } label: {
                                Image(systemName: "arrow.clockwise.circle")
                                    .font(.title3)
                                    .foregroundStyle(AppTheme.textSecondary)
                                    .rotationEffect(.degrees(isRefreshing ? 360 : 0))
                                    .animation(
                                        isRefreshing
                                            ? .linear(duration: 1).repeatForever(autoreverses: false)
                                            : .default,
                                        value: isRefreshing
                                    )
                            }
                            .buttonStyle(.plain)
                            .disabled(isRefreshing)
                            .accessibilityLabel("Refresh balance from your bank")
                        }
                        HStack(spacing: 8) {
                            Text("$\(balance.amount)")
                                .font(.headline)
                                .foregroundStyle(AppTheme.textPrimary)
                                .lineLimit(1)
                                .minimumScaleFactor(0.6)
                            Spacer(minLength: 8)
                            Text(balance.date)
                                .font(.caption)
                                .foregroundStyle(AppTheme.textMuted)
                                .lineLimit(1)
                        }
                    }
                    .cardRow()
                }

                if let statusText {
                    Text(statusText)
                        .font(.caption)
                        .foregroundStyle(AppTheme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(spacing: 8) {
                    TextField("New balance amount", text: $newAmount)
                        .keyboardType(.decimalPad)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                    Button("Save Balance") { Task { await saveBalance() } }
                        .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Text("History")
                    .foregroundStyle(AppTheme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                ForEach(history, id: \.date) { item in
                    HStack(spacing: 12) {
                        Text(item.date)
                            .foregroundStyle(AppTheme.textSecondary)
                            .lineLimit(1)
                        Spacer(minLength: 8)
                        Text("$\(item.amount)")
                            .foregroundStyle(AppTheme.textPrimary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                    }
                    .frame(maxWidth: .infinity)
                    .surfaceCard()
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("Balance")
    }

    private func load() async {
        guard let token = session.token else { return }
        do {
            let current: APIEnvelope<BalanceDTO> = try await APIClient.shared.request(
                "balance",
                token: token,
                as: APIEnvelope<BalanceDTO>.self
            )
            let list: APIListEnvelope<BalanceDTO> = try await APIClient.shared.request(
                "balance/history",
                queryItems: [
                    URLQueryItem(name: "limit", value: "20"),
                    URLQueryItem(name: "offset", value: "0")
                ],
                token: token,
                as: APIListEnvelope<BalanceDTO>.self
            )
            balance = current.data
            history = list.data
        } catch {
            errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load balances"
        }
    }

    private func saveBalance() async {
        guard let token = session.token else { return }
        do {
            struct Payload: Encodable { let amount: String }
            _ = try await APIClient.shared.request("balance", method: "POST", token: token, body: Payload(amount: newAmount), as: APIEnvelope<BalanceDTO>.self)
            await load()
            newAmount = ""
        } catch {
            errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to save balance"
        }
    }

    private func refreshRealtimeBalance() async {
        guard let token = session.token else { return }
        // Prevent double-taps while the request is in flight. The guard
        // must exit the function, not just the MainActor closure, or a
        // second tap can still fire a duplicate network request.
        let shouldProceed = await MainActor.run { () -> Bool in
            guard !isRefreshing else { return false }
            isRefreshing = true
            errorText = nil
            statusText = nil
            return true
        }
        guard shouldProceed else { return }
        defer {
            Task { @MainActor in isRefreshing = false }
        }
        do {
            let response: APIEnvelope<PlaidRealtimeBalanceDTO> = try await APIClient.shared.request(
                "plaid/realtime-balance",
                method: "POST",
                token: token,
                as: APIEnvelope<PlaidRealtimeBalanceDTO>.self
            )
            // Reload the local balance card from the existing balance API so
            // the new amount/date show immediately, and trigger a dashboard
            // reload notification so the Dashboard view picks up the change.
            await load()
            NotificationCenter.default.post(name: .pycashflowDashboardShouldReload, object: nil)
            await MainActor.run {
                statusText = response.data.message ?? "Live balance refreshed."
            }
        } catch let envelope as APIErrorEnvelope {
            await MainActor.run {
                if envelope.code == "plaid_realtime_cooldown" {
                    statusText = envelope.error
                } else if envelope.code == "plaid_no_connection" {
                    errorText = envelope.error
                } else {
                    errorText = envelope.error
                }
            }
        } catch {
            await MainActor.run { errorText = "Failed to refresh balance" }
        }
    }
}

extension Notification.Name {
    /// Posted by features that mutate the user's balance so the Dashboard
    /// view can re-fetch its data without a full app refresh.
    static let pycashflowDashboardShouldReload = Notification.Name(
        "PyCashFlowDashboardShouldReload"
    )
}
