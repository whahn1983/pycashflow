import SwiftUI

struct AccountsView: View {
    @EnvironmentObject var session: SessionManager
    @State private var balance: BalanceDTO?
    @State private var history: [BalanceDTO] = []
    @State private var newAmount = ""
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Accounts")
                    .font(.title2.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                if let balance {
                    Text("Current Balance: $\(balance.amount) on \(balance.date)")
                        .foregroundStyle(AppTheme.textPrimary)
                        .surfaceCard()
                }

                VStack(spacing: 8) {
                    TextField("New balance amount", text: $newAmount)
                        .keyboardType(.decimalPad)
                        .padding(12)
                        .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                    Button("Save Balance") { Task { await saveBalance() } }
                        .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()

                if let errorText { Text(errorText).foregroundStyle(AppTheme.danger) }

                Text("History").foregroundStyle(AppTheme.textPrimary)
                ForEach(history, id: \.date) { item in
                    HStack {
                        Text(item.date).foregroundStyle(AppTheme.textSecondary)
                        Spacer()
                        Text("$\(item.amount)").foregroundStyle(AppTheme.textPrimary)
                    }.surfaceCard()
                }
            }
            .padding(20)
        }
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("Accounts")
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
}
