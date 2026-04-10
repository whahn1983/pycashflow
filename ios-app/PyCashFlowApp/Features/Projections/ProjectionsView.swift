import SwiftUI

struct ProjectionsView: View {
    @EnvironmentObject var session: SessionManager
    @State private var scheduleSeries: [ProjectionPointDTO] = []
    @State private var scenarioSeries: [ProjectionPointDTO] = []
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Projections")
                    .font(.title2.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                Text("Schedule projection points: \(scheduleSeries.count)")
                    .foregroundStyle(AppTheme.textSecondary)
                Text("Scenario projection points: \(scenarioSeries.count)")
                    .foregroundStyle(AppTheme.textSecondary)

                if let point = scheduleSeries.first {
                    Text("Next Schedule Point: \(point.date) · $\(point.amount)")
                        .surfaceCard()
                }
                if let point = scenarioSeries.first {
                    Text("Next Scenario Point: \(point.date) · $\(point.amount)")
                        .surfaceCard()
                }

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("Projections")
    }

    private func load() async {
        guard let token = session.token else { return }
        do {
            let response: APIEnvelope<ProjectionsDTO> = try await APIClient.shared.request("projections", token: token, as: APIEnvelope<ProjectionsDTO>.self)
            await MainActor.run {
                scheduleSeries = response.data.schedule
                scenarioSeries = response.data.scenario ?? []
            }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load projections" }
        }
    }
}
