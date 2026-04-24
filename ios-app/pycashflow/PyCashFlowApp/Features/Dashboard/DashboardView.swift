import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var session: SessionManager
    @State private var dashboard: DashboardDTO?
    @State private var projections: ProjectionsDTO?
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let dashboard {
                    metricsGrid {
                        statCard(title: "Balance", value: "$\(dashboard.balance)")
                        statCard(title: "Min (90d)", value: "$\(dashboard.min_balance)")
                    }
                    if let risk = dashboard.risk_v2 {
                        metricsGrid {
                            statCard(title: "Risk", value: riskSummaryText(risk))
                            statCard(title: "Runway", value: runwayText(risk))
                        }
                    }

                    if let projections {
                        CashFlowChartView(
                            schedule: projections.schedule,
                            scenario: projections.scenario ?? []
                        )
                    }

                    Text("Upcoming")
                        .font(.headline)
                        .foregroundStyle(AppTheme.textPrimary)
                    ForEach(dashboard.upcoming_transactions.prefix(5)) { tx in
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tx.name)
                                    .foregroundStyle(AppTheme.textPrimary)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                Text(tx.date)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.textMuted)
                                    .lineLimit(1)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            Text("$\(tx.amount)")
                                .foregroundStyle(tx.type == "Expense" ? AppTheme.danger : AppTheme.success)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .surfaceCard()
                    }
                }

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(spacing: 10) {
                    navRow("Accounts", systemImage: "creditcard", destination: AccountsView())
                    navRow("Projections", systemImage: "chart.line.uptrend.xyaxis", destination: ProjectionsView())
                    navRow("Schedules", systemImage: "calendar", destination: SchedulesView())
                    navRow("Scenarios", systemImage: "slider.horizontal.3", destination: ScenariosView())
                    navRow("AI Insights", systemImage: "sparkles", destination: AIInsightsView())
                    navRow("Settings", systemImage: "gearshape", destination: SettingsView())
                }
            }
            .padding(20)
        }
        .task { await loadAll() }
        .refreshable { await loadAll() }
        .appBackground()
        .navigationTitle("Dashboard")
    }

    private func metricsGrid<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) {
                content()
            }
            VStack(spacing: 10) {
                content()
            }
        }
    }


    private func riskSummaryText(_ risk: RiskScoreDTO) -> String {
        let scoreText = risk.score.map(String.init) ?? "—"
        let statusText = risk.status ?? "Unavailable"
        return "\(scoreText) · \(statusText)"
    }

    private func runwayText(_ risk: RiskScoreDTO) -> String {
        guard let runwayDays = risk.runway_days else {
            return "Unavailable"
        }
        let rounded = runwayDays.rounded()
        if abs(runwayDays - rounded) < 0.05 {
            return "\(Int(rounded)) days"
        }
        return String(format: "%.1f days", runwayDays)
    }

    private func statCard(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(AppTheme.textMuted)
                .lineLimit(1)
            Text(value)
                .font(.headline)
                .foregroundStyle(AppTheme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .truncationMode(.tail)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .surfaceCard()
    }

    private func loadAll() async {
        async let dashboardTask: Void = loadDashboard()
        async let projectionsTask: Void = loadProjections()
        _ = await (dashboardTask, projectionsTask)
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

    private func loadProjections() async {
        guard let token = session.token else {
            await MainActor.run { projections = nil }
            return
        }
        do {
            let response: APIEnvelope<ProjectionsDTO> = try await APIClient.shared.request("projections", token: token, as: APIEnvelope<ProjectionsDTO>.self)
            await MainActor.run { projections = response.data }
        } catch {
            // Clear stale data so the chart hides silently; dashboard error surfaces other issues.
            await MainActor.run { projections = nil }
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
                    .lineLimit(1)
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.textMuted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .surfaceCard()
        }
    }
}
