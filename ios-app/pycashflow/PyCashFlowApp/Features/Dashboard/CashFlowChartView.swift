import SwiftUI
import Charts

struct CashFlowChartView: View {
    let schedule: [ProjectionPointDTO]
    let scenario: [ProjectionPointDTO]

    private static let scheduleColor = Color(red: 59/255, green: 130/255, blue: 246/255)   // #3b82f6
    private static let scenarioColor = Color(red: 245/255, green: 158/255, blue: 11/255)   // #f59e0b

    private var schedulePoints: [CashFlowPoint] { CashFlowPoint.parse(schedule) }
    private var scenarioPoints: [CashFlowPoint] { CashFlowPoint.parse(scenario) }

    private var hasScenario: Bool { !scenarioPoints.isEmpty }

    private var xDomain: ClosedRange<Date> {
        let today = Calendar.current.startOfDay(for: Date())
        let end = Calendar.current.date(byAdding: .day, value: 90, to: today) ?? today
        return today...end
    }

    private var yDomain: ClosedRange<Double> {
        let horizonEnd = xDomain.upperBound
        let inWindow: (CashFlowPoint) -> Bool = { $0.date <= horizonEnd }
        let values = (schedulePoints + scenarioPoints).filter(inWindow).map(\.amount)
        guard let rawMin = values.min(), let rawMax = values.max() else {
            return 0...1
        }
        let lower = rawMin >= 0 ? 0 : rawMin * 1.1
        let upper = max(rawMax * 1.1, lower + 1)
        return lower...upper
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "chart.xyaxis.line")
                    .foregroundStyle(AppTheme.accent)
                Text("Cash Flow")
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)
                Spacer()
                if hasScenario {
                    legend()
                }
            }

            if schedulePoints.isEmpty && scenarioPoints.isEmpty {
                Text("No projection data yet.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.textMuted)
                    .frame(maxWidth: .infinity, minHeight: 180, alignment: .center)
            } else {
                chart
                    .frame(height: 220)
            }
        }
        .surfaceCard()
    }

    @ViewBuilder
    private var chart: some View {
        Chart {
            ForEach(scenarioPoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Balance", point.amount),
                    series: .value("Series", "With Scenarios")
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Self.scenarioColor)
                .lineStyle(StrokeStyle(lineWidth: 2, dash: [6, 4]))
            }

            ForEach(schedulePoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Balance", point.amount),
                    series: .value("Series", "Schedule")
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Self.scheduleColor)
                .lineStyle(StrokeStyle(lineWidth: 2))
            }
        }
        .chartXScale(domain: xDomain)
        .chartYScale(domain: yDomain)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                AxisGridLine().foregroundStyle(AppTheme.border.opacity(0.5))
                AxisTick().foregroundStyle(AppTheme.border)
                AxisValueLabel()
                    .foregroundStyle(AppTheme.textMuted)
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 5)) { value in
                AxisGridLine().foregroundStyle(AppTheme.border.opacity(0.5))
                AxisTick().foregroundStyle(AppTheme.border)
                AxisValueLabel {
                    if let amount = value.as(Double.self) {
                        Text(currencyAxisLabel(amount))
                            .foregroundStyle(AppTheme.textMuted)
                    }
                }
            }
        }
    }

    private func legend() -> some View {
        HStack(spacing: 10) {
            if hasScenario {
                legendItem(color: Self.scenarioColor, dashed: true, label: "With Scenarios")
            }
            legendItem(color: Self.scheduleColor, dashed: false, label: "Schedule")
        }
        .font(.caption2)
        .foregroundStyle(AppTheme.textSecondary)
    }

    private func legendItem(color: Color, dashed: Bool, label: String) -> some View {
        HStack(spacing: 4) {
            LegendSwatch(color: color, dashed: dashed)
                .frame(width: 18, height: 2)
            Text(label)
        }
    }

    private func currencyAxisLabel(_ amount: Double) -> String {
        let absValue = abs(amount)
        let sign = amount < 0 ? "-" : ""
        if absValue >= 1_000_000 {
            return "\(sign)$\(formatNumber(absValue / 1_000_000))M"
        }
        if absValue >= 1_000 {
            return "\(sign)$\(formatNumber(absValue / 1_000))k"
        }
        return "\(sign)$\(Int(absValue.rounded()))"
    }

    private func formatNumber(_ value: Double) -> String {
        if value >= 10 || value.rounded() == value {
            return String(format: "%.0f", value)
        }
        return String(format: "%.1f", value)
    }
}

private struct LegendSwatch: View {
    let color: Color
    let dashed: Bool

    var body: some View {
        GeometryReader { geo in
            Path { path in
                let y = geo.size.height / 2
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: geo.size.width, y: y))
            }
            .stroke(
                color,
                style: StrokeStyle(lineWidth: 2, dash: dashed ? [4, 3] : [])
            )
        }
    }
}

struct CashFlowPoint: Identifiable {
    let date: Date
    let amount: Double
    var id: Date { date }

    static func parse(_ points: [ProjectionPointDTO]) -> [CashFlowPoint] {
        points.compactMap { dto in
            guard let date = dateFormatter.date(from: dto.date),
                  let amount = Double(dto.amount) else { return nil }
            return CashFlowPoint(date: date, amount: amount)
        }
        .sorted { $0.date < $1.date }
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}
