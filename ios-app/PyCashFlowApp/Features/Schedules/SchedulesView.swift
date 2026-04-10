import SwiftUI

struct SchedulesView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Schedules")
                .font(.title2.bold())
                .foregroundStyle(AppTheme.textPrimary)
            Text("Schedule screens now align with the web color tokens and contrast.")
                .foregroundStyle(AppTheme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(20)
        .appBackground()
        .navigationTitle("Schedules")
        .toolbarBackground(AppTheme.secondaryDark, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }
}
