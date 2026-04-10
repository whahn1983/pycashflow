import SwiftUI

struct ProjectionsView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Projections")
                .font(.title2.bold())
                .foregroundStyle(AppTheme.textPrimary)
            Text("Projection views now use the same dark palette as the web app.")
                .foregroundStyle(AppTheme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(20)
        .appBackground()
        .navigationTitle("Projections")
        .toolbarBackground(AppTheme.secondaryDark, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }
}
