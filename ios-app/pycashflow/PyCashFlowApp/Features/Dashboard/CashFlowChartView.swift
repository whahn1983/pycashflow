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
    private static let visibleDays = 90
    private static let nearTermDays = 30

    @State private var selectedPoint: SelectedChartPoint?

    private var xDomain: ClosedRange<Date> {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? calendar.timeZone
        let today = calendar.startOfDay(for: Date())
        let end = calendar.date(byAdding: .day, value: Self.horizonDays, to: today) ?? today
        return today...end
    }

    private var visibleXDomainLength: TimeInterval {
        TimeInterval(Self.visibleDays * 24 * 60 * 60)
    }

    private var allPointsInHorizon: [CashFlowPoint] {
        let end = xDomain.upperBound
        return (schedulePoints + scenarioPoints).filter { $0.date <= end }
    }

    private var yDomain: ClosedRange<Double> {
        let values = allPointsInHorizon.map(\.amount)
        guard let rawMin = values.min(), let rawMax = values.max() else {
            return 0...1
        }
        let lower = rawMin >= 0 ? 0 : rawMin * 1.1
        let upper = max(rawMax * 1.1, lower + 1)
        return lower...upper
    }

    /// Visible Y length based on the near-term window so that when the projection
    /// trends sharply up or down across the horizon the user can scroll vertically
    /// to follow the line, matching the horizontal scroll behaviour.
    private var visibleYDomainLength: Double {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? calendar.timeZone
        let today = calendar.startOfDay(for: Date())
        let nearEnd = calendar.date(byAdding: .day, value: Self.nearTermDays, to: today) ?? today
        let nearValues = allPointsInHorizon
            .filter { $0.date <= nearEnd }
            .map(\.amount)
        let full = yDomain.upperBound - yDomain.lowerBound
        guard let nearMin = nearValues.min(), let nearMax = nearValues.max(), full > 0 else {
            return full
        }
        let nearSpan = max(nearMax - nearMin, full * 0.25)
        let padded = nearSpan * 1.2
        return min(max(padded, full * 0.25), full)
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
                    .frame(height: 240)
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

            if let selected = selectedPoint {
                RuleMark(x: .value("Selected", selected.point.date))
                    .foregroundStyle(AppTheme.textMuted.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(
                        position: annotationPosition(for: selected.point.date),
                        alignment: .center,
                        spacing: 6
                    ) {
                        tooltip(for: selected)
                    }
                PointMark(
                    x: .value("Date", selected.point.date),
                    y: .value("Balance", selected.point.amount)
                )
                .symbolSize(90)
                .foregroundStyle(selected.series == .scenario ? Self.scenarioColor : Self.scheduleColor)
            }
        }
        .chartXScale(domain: xDomain)
        .chartYScale(domain: yDomain)
        .chartScrollableAxes([.horizontal, .vertical])
        .chartXVisibleDomain(length: visibleXDomainLength)
        .chartYVisibleDomain(length: visibleYDomainLength)
        .chartScrollPosition(initialX: xDomain.lowerBound)
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
        .chartOverlay { proxy in
            GeometryReader { geo in
                Rectangle()
                    .fill(Color.clear)
                    .contentShape(Rectangle())
                    .onTapGesture { location in
                        updateSelection(location: location, proxy: proxy, geometry: geo)
                    }
                    // Require a brief hold before drag-to-scrub activates so
                    // regular drags fall through to the chart's horizontal
                    // and vertical scroll gestures.
                    .simultaneousGesture(
                        LongPressGesture(minimumDuration: 0.2)
                            .sequenced(before: DragGesture(minimumDistance: 0))
                            .onChanged { value in
                                if case .second(true, let drag?) = value {
                                    updateSelection(location: drag.location, proxy: proxy, geometry: geo)
                                }
                            }
                    )
            }
        }
    }

    private func updateSelection(location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard let plotFrameAnchor = proxy.plotFrame else { return }
        let plotFrame = geometry[plotFrameAnchor]
        let x = location.x - plotFrame.origin.x
        let y = location.y - plotFrame.origin.y
        guard x >= 0, x <= plotFrame.width else { return }
        guard let date: Date = proxy.value(atX: x) else { return }

        // Consider the nearest candidate from each series and pick whichever
        // is closer to the tap in screen space, so both lines remain
        // independently selectable when scenario data is present.
        let tap = CGPoint(x: x, y: y)
        let candidates: [(point: CashFlowPoint, series: SelectedChartPoint.Series)] = [
            nearestPoint(to: date, in: schedulePoints).map { ($0, .schedule) },
            nearestPoint(to: date, in: scenarioPoints).map { ($0, .scenario) }
        ].compactMap { $0 }

        guard let best = candidates.min(by: {
            screenDistance(from: tap, to: $0.point, proxy: proxy)
                < screenDistance(from: tap, to: $1.point, proxy: proxy)
        }) else {
            selectedPoint = nil
            return
        }
        selectedPoint = SelectedChartPoint(point: best.point, series: best.series)
    }

    private func nearestPoint(to date: Date, in points: [CashFlowPoint]) -> CashFlowPoint? {
        points.min(by: { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) })
    }

    private func screenDistance(from tap: CGPoint, to point: CashFlowPoint, proxy: ChartProxy) -> CGFloat {
        guard let px = proxy.position(forX: point.date),
              let py = proxy.position(forY: point.amount) else {
            return .greatestFiniteMagnitude
        }
        let dx = tap.x - px
        let dy = tap.y - py
        return sqrt(dx * dx + dy * dy)
    }

    private func annotationPosition(for date: Date) -> AnnotationPosition {
        let midpoint = xDomain.lowerBound.addingTimeInterval(visibleXDomainLength / 2)
        return date > midpoint ? .topLeading : .topTrailing
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
