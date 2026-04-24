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
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 96)
        }
        .task { await loadAll() }
        .refreshable { await loadAll() }
        .appBackground()
        .navigationTitle("Dashboard")
        .safeAreaInset(edge: .bottom, spacing: 0) {
            FloatingNavBar(items: navItems)
        }
    }

    private var navItems: [FloatingNavItem] {
        [
            FloatingNavItem(title: "Accounts", systemImage: "creditcard") { AccountsView() },
            FloatingNavItem(title: "Schedules", systemImage: "calendar") { SchedulesView() },
            FloatingNavItem(title: "Scenarios", systemImage: "slider.horizontal.3") { ScenariosView() },
            FloatingNavItem(title: "AI Insights", systemImage: "sparkles") { AIInsightsView() },
            FloatingNavItem(title: "Settings", systemImage: "gearshape") { SettingsView() }
        ]
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

}
