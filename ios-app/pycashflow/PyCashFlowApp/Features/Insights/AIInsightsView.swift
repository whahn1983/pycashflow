import SwiftUI

struct AIInsightsView: View {
    @EnvironmentObject var session: SessionManager
    @State private var insights: InsightsDTO?
    @State private var errorText: String?
    @State private var isRefreshing = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let insights {
                    if let model = insights.model, !model.isEmpty {
                        infoRow(label: "Model", value: model)
                    }
                    if let lastUpdated = insights.last_updated, !lastUpdated.isEmpty {
                        infoRow(label: "Last Updated", value: Self.formatLastUpdated(lastUpdated))
                    }
                    infoRow(label: "AI Configured", value: insights.configured ? "Yes" : "No")
                }

                if let items = insights?.insights, !items.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Insights")
                            .font(.caption)
                            .foregroundStyle(AppTheme.textMuted)
                        ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                            VStack(alignment: .leading, spacing: 2) {
                                if let title = item.title, !title.isEmpty {
                                    Text(title)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(AppTheme.textPrimary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                if let description = item.description, !description.isEmpty {
                                    Text(description)
                                        .foregroundStyle(AppTheme.textSecondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .cardRow()
                } else if insights != nil {
                    Text("No insights yet. Tap Refresh AI Insights to generate them.")
                        .foregroundStyle(AppTheme.textMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .cardRow()
                }

                Button(isRefreshing ? "Refreshing..." : "Refresh AI Insights") {
                    Task { await refreshInsights() }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(isRefreshing)

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("AI Insights")
    }

    private func infoRow(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(AppTheme.textMuted)
            Text(value)
                .foregroundStyle(AppTheme.textPrimary)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .cardRow()
    }

    private func load() async {
        guard let token = session.token else { return }
        do {
            let response: APIEnvelope<InsightsDTO> = try await APIClient.shared.request(
                "insights",
                token: token,
                as: APIEnvelope<InsightsDTO>.self
            )
            insights = response.data
            errorText = nil
        } catch {
            errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load insights"
        }
    }

    private static let lastUpdatedParser: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let lastUpdatedDisplayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        formatter.doesRelativeDateFormatting = true
        formatter.locale = .autoupdatingCurrent
        formatter.timeZone = .autoupdatingCurrent
        return formatter
    }()

    static func formatLastUpdated(_ raw: String) -> String {
        guard let date = lastUpdatedParser.date(from: raw) else { return raw }
        return lastUpdatedDisplayFormatter.string(from: date)
    }

    private func refreshInsights() async {
        guard let token = session.token else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            let response: APIEnvelope<InsightsDTO> = try await APIClient.shared.request(
                "insights/refresh",
                method: "POST",
                token: token,
                as: APIEnvelope<InsightsDTO>.self
            )
            insights = response.data
            errorText = nil
        } catch {
            errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to refresh insights"
        }
    }
}
