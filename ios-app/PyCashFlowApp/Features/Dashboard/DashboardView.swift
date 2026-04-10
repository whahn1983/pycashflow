import SwiftUI

struct DashboardView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Dashboard")
                    .font(.largeTitle.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                Text("Use the same workflow as the web app sections below.")
                    .foregroundStyle(AppTheme.textSecondary)

                VStack(spacing: 10) {
                    navRow("Accounts", systemImage: "creditcard", destination: AccountsView())
                    navRow("Projections", systemImage: "chart.line.uptrend.xyaxis", destination: ProjectionsView())
                    navRow("Schedules", systemImage: "calendar", destination: SchedulesView())
                    navRow("Scenarios", systemImage: "slider.horizontal.3", destination: ScenariosView())
                    navRow("Settings", systemImage: "gearshape", destination: SettingsView())
                }
            }
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Dashboard")
        .toolbarBackground(AppTheme.secondaryDark, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }

    private func navRow<Destination: View>(
        _ title: String,
        systemImage: String,
        destination: Destination
    ) -> some View {
        NavigationLink(destination: destination) {
            HStack(spacing: 12) {
                Image(systemName: systemImage)
                    .foregroundStyle(AppTheme.accent)
                    .frame(width: 20)
                Text(title)
                    .foregroundStyle(AppTheme.textPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.textMuted)
            }
            .surfaceCard()
        }
    }
}
