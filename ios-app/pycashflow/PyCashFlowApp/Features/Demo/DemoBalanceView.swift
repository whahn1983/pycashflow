import SwiftUI

struct DemoBalanceView: View {
    @EnvironmentObject private var store: DemoStore
    @State private var newAmount = ""
    @State private var errorText: String?
    @State private var isEditingBalance = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                let balance = store.currentBalance

                VStack(alignment: .leading, spacing: 2) {
                    Text("Current Balance")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textMuted)
                    HStack(spacing: 8) {
                        Text("$\(balance?.amountString ?? "0.00")")
                            .font(.headline)
                            .foregroundStyle(AppTheme.textPrimary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.6)
                        Button {
                            withAnimation { isEditingBalance.toggle() }
                        } label: {
                            Image(systemName: "pencil.circle")
                                .font(.title3)
                                .foregroundStyle(AppTheme.textSecondary)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Edit balance")
                        Spacer(minLength: 8)
                        Text(balance?.date ?? DemoStore.todayLocal.isoString)
                            .font(.caption)
                            .foregroundStyle(AppTheme.textMuted)
                            .lineLimit(1)
                    }
                }
                .cardRow()

                if isEditingBalance {
                    VStack(spacing: 8) {
                        TextField("New balance amount", text: $newAmount)
                            .keyboardType(.decimalPad)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                        Button("Save Balance") { saveBalance() }
                            .buttonStyle(PrimaryButtonStyle())
                    }
                    .surfaceCard()
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Text("History")
                    .foregroundStyle(AppTheme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if store.balanceHistory.isEmpty {
                    Text("No balance entries yet.")
                        .foregroundStyle(AppTheme.textMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .surfaceCard()
                } else {
                    ForEach(store.balanceHistory) { item in
                        HStack(spacing: 12) {
                            Text(item.date)
                                .foregroundStyle(AppTheme.textSecondary)
                                .lineLimit(1)
                            Spacer(minLength: 8)
                            Text("$\(item.amountString)")
                                .foregroundStyle(AppTheme.textPrimary)
                                .lineLimit(1)
                                .minimumScaleFactor(0.7)
                        }
                        .frame(maxWidth: .infinity)
                        .surfaceCard()
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Balance")
    }

    private func saveBalance() {
        if let error = store.setBalance(amountText: newAmount) {
            errorText = error
            return
        }
        errorText = nil
        newAmount = ""
        withAnimation { isEditingBalance = false }
    }
}
