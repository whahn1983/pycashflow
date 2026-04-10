import SwiftUI

struct AccountsView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Accounts")
                .font(.title2.bold())
                .foregroundStyle(AppTheme.textPrimary)
            Text("Account screens will follow the web app surface and typography style.")
                .foregroundStyle(AppTheme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(20)
        .appBackground()
        .navigationTitle("Accounts")
        .toolbarBackground(AppTheme.secondaryDark, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }
}
