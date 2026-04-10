import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var session: SessionManager
    @State private var dashboard: DashboardDTO?
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Dashboard")
                    .font(.largeTitle.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                if let dashboard {
                    HStack {
                        statCard(title: "Balance", value: "$\(dashboard.balance)")
                        statCard(title: "Min (90d)", value: "$\(dashboard.min_balance)")
                    }
                    if let risk = dashboard.risk_v2 {
                        HStack {
                            statCard(title: "Risk", value: "\(risk.score) · \(risk.status)")
                            statCard(title: "Runway", value: "\(risk.runway_days) days")
                        }
                    }

                    Text("Upcoming")
                        .font(.headline)
                        .foregroundStyle(AppTheme.textPrimary)
                    ForEach(dashboard.upcoming_transactions.prefix(5)) { tx in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(tx.name).foregroundStyle(AppTheme.textPrimary)
                                Text(tx.date).font(.caption).foregroundStyle(AppTheme.textMuted)
                            }
                            Spacer()
                            Text("$\(tx.amount)")
                                .foregroundStyle(tx.type == "Expense" ? AppTheme.danger : AppTheme.success)
                        }
                        .surfaceCard()
                    }
                }

                if let errorText {
                    Text(errorText).foregroundStyle(AppTheme.danger)
                }

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
        .task { await loadDashboard() }
        .refreshable { await loadDashboard() }
        .appBackground()
        .navigationTitle("Dashboard")
    }

    private func statCard(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(AppTheme.textMuted)
            Text(value).font(.headline).foregroundStyle(AppTheme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .surfaceCard()
    }

    private func loadDashboard() async {
        guard let token = session.token else { return }
        do {
            let response: APIEnvelope<DashboardDTO> = try await APIClient.shared.request("dashboard", token: token, as: APIEnvelope<DashboardDTO>.self)
            await MainActor.run {
                dashboard = response.data
                errorText = nil
            }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load dashboard" }
        }
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
