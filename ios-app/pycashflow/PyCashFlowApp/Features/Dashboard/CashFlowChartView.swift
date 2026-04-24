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

    private static let horizonDays = 90

    @State private var selectedDate: Date?
    @State private var selectedAmount: Double?

    private var xDomain: ClosedRange<Date> {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? calendar.timeZone
        let today = calendar.startOfDay(for: Date())
        let end = calendar.date(byAdding: .day, value: Self.horizonDays, to: today) ?? today
        return today...end
    }

    private var visibleSchedulePoints: [CashFlowPoint] {
        let domain = xDomain
        return schedulePoints.filter { domain.contains($0.date) }
    }

    private var visibleScenarioPoints: [CashFlowPoint] {
        let domain = xDomain
        return scenarioPoints.filter { domain.contains($0.date) }
    }

    private var allPointsInHorizon: [CashFlowPoint] {
        visibleSchedulePoints + visibleScenarioPoints
    }

    private var yDomain: ClosedRange<Double> {
        let values = allPointsInHorizon.map(\.amount)
        guard let rawMin = values.min(), let rawMax = values.max() else {
            return 0...1
        }
        let lower = min(rawMin, 0)
        let upper = max(rawMax * 1.1, lower + 1)
        return lower...upper
    }

    private var selectedPoint: SelectedChartPoint? {
        guard let selectedDate else { return nil }
        let candidates: [(point: CashFlowPoint, series: SelectedChartPoint.Series)] = [
            nearestPoint(to: selectedDate, in: visibleSchedulePoints).map { ($0, .schedule) },
            nearestPoint(to: selectedDate, in: visibleScenarioPoints).map { ($0, .scenario) }
        ].compactMap { $0 }
        guard let best = candidates.min(by: { lhs, rhs in
            let lhsX = abs(lhs.point.date.timeIntervalSince(selectedDate))
            let rhsX = abs(rhs.point.date.timeIntervalSince(selectedDate))
            if lhsX != rhsX { return lhsX < rhsX }
            // Tie-break by y-proximity so a tap near the scenario line
            // selects it even when schedule has a point on the same date.
            guard let selectedAmount else { return false }
            return abs(lhs.point.amount - selectedAmount)
                < abs(rhs.point.amount - selectedAmount)
        }) else { return nil }
        return SelectedChartPoint(point: best.point, series: best.series)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "chart.xyaxis.line")
                    .foregroundStyle(AppTheme.accent)
                Text("Cash Flow")
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }

            if hasScenario {
                legend()
            }

            if schedulePoints.isEmpty && scenarioPoints.isEmpty {
                Text("No projection data yet.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.textMuted)
                    .frame(maxWidth: .infinity, minHeight: 180, alignment: .center)
            } else {
                chart
                    .frame(maxWidth: .infinity)
                    .frame(height: 240)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .surfaceCard()
    }

    @ViewBuilder
    private var chart: some View {
        Chart {
            ForEach(visibleScenarioPoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Balance", point.amount),
                    series: .value("Series", "With Scenarios")
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Self.scenarioColor)
                .lineStyle(StrokeStyle(lineWidth: 2, dash: [6, 4]))
            }

            ForEach(visibleSchedulePoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Balance", point.amount),
                    series: .value("Series", "Schedule")
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Self.scheduleColor)
                .lineStyle(StrokeStyle(lineWidth: 2))
            }

            if let selected = selectedPoint {
                RuleMark(x: .value("Selected", selected.point.date))
                    .foregroundStyle(AppTheme.textMuted.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                PointMark(
                    x: .value("Date", selected.point.date),
                    y: .value("Balance", selected.point.amount)
                )
                .symbolSize(90)
                .foregroundStyle(selected.series == .scenario ? Self.scenarioColor : Self.scheduleColor)
                .annotation(
                    position: .top,
                    alignment: .center,
                    spacing: 6,
                    overflowResolution: .init(x: .fit(to: .chart), y: .fit(to: .chart))
                ) {
                    tooltip(for: selected)
                }
            }
        }
        .chartXScale(domain: xDomain)
        .chartYScale(domain: yDomain)
        .chartXSelection(value: $selectedDate)
        .chartYSelection(value: $selectedAmount)
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

    private func nearestPoint(to date: Date, in points: [CashFlowPoint]) -> CashFlowPoint? {
        points.min(by: { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) })
    }

    private func tooltip(for selection: SelectedChartPoint) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(Self.tooltipDateFormatter.string(from: selection.point.date))
                .font(.caption2)
                .foregroundStyle(AppTheme.textMuted)
            Text(currencyTooltipLabel(selection.point.amount))
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.textPrimary)
            Text(selection.series == .scenario ? "With Scenarios" : "Schedule")
                .font(.caption2)
                .foregroundStyle(selection.series == .scenario ? Self.scenarioColor : Self.scheduleColor)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(AppTheme.primaryDark.opacity(0.95))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(AppTheme.border, lineWidth: 1)
        )
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
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
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

    private func currencyTooltipLabel(_ amount: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.maximumFractionDigits = 2
        formatter.minimumFractionDigits = 2
        return formatter.string(from: NSNumber(value: amount)) ?? "$\(amount)"
    }

    private func formatNumber(_ value: Double) -> String {
        if value >= 10 || value.rounded() == value {
            return String(format: "%.0f", value)
        }
        return String(format: "%.1f", value)
    }

    private static let tooltipDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "MMM d, yyyy"
        return formatter
    }()
}

private struct SelectedChartPoint: Equatable {
    enum Series { case schedule, scenario }
    let point: CashFlowPoint
    let series: Series

    static func == (lhs: SelectedChartPoint, rhs: SelectedChartPoint) -> Bool {
        lhs.point.date == rhs.point.date && lhs.series == rhs.series
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

struct CashFlowPoint: Identifiable, Equatable {
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
