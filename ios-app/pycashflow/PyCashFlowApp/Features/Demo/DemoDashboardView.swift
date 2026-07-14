import SwiftUI

struct DemoDashboardView: View {
    @EnvironmentObject private var store: DemoStore

    var body: some View {
        let result = store.projection()
        let balance = store.currentBalance

        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                metricsGrid {
                    statCard(title: "Balance", value: "$\(balance?.amountString ?? "0.00")")
                    statCard(title: "Min (90d)", value: "$\(result.minBalance)")
                }
                metricsGrid {
                    statCard(title: "Risk", value: "\(result.risk.score) · \(result.risk.status)")
                    statCard(title: "Runway", value: runwayText(result.risk.runwayDays))
                }

                CashFlowChartView(
                    schedule: points(result.scheduleRun),
                    scenario: points(result.scenarioRun ?? [])
                )

                Text("Upcoming")
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)

                if result.upcoming.isEmpty {
                    Text("No upcoming transactions in the next 90 days.")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .cardRow()
                } else {
                    ForEach(Array(result.upcoming.prefix(5).enumerated()), id: \.offset) { _, tx in
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tx.name)
                                    .foregroundStyle(AppTheme.textPrimary)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                Text(tx.date.isoString)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.textMuted)
                                    .lineLimit(1)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            Text("$\(DemoAmount.string(tx.amount))")
                                .foregroundStyle(tx.type == "Expense" ? AppTheme.danger : AppTheme.success)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .surfaceCard()
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 20)
        }
        .appBackground()
        .navigationTitle("Dashboard")
    }

    private func points(_ series: [DemoProjectionEngine.SeriesPoint]) -> [ProjectionPointDTO] {
        series.map {
            ProjectionPointDTO(date: $0.date.isoString, amount: DemoAmount.string(fromDouble: $0.amount))
        }
    }

    private func metricsGrid<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { content() }
            VStack(spacing: 10) { content() }
        }
    }

    private func runwayText(_ runwayDays: Double?) -> String {
        guard let runwayDays else { return "Unavailable" }
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
}
