import SwiftUI

struct ScenariosView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Scenarios")
                .font(.title2.bold())
                .foregroundStyle(AppTheme.textPrimary)
            Text("Scenario screens now use matching slate surfaces and blue accents.")
                .foregroundStyle(AppTheme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(20)
        .appBackground()
        .navigationTitle("Scenarios")
        .toolbarBackground(AppTheme.secondaryDark, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }
}
