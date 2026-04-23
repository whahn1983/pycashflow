import SwiftUI

struct ScenariosView: View {
    @EnvironmentObject var session: SessionManager
    @State private var scenarios: [ScenarioDTO] = []
    @State private var name = ""
    @State private var amount = ""
    @State private var type = "Expense"
    @State private var frequency = "Monthly"
    @State private var startDate = "2026-01-01"
    @State private var errorText: String?

    private let types = ["Expense", "Income"]
    private let frequencies = ["Monthly", "Quarterly", "Yearly", "Weekly", "BiWeekly", "Onetime"]

    var body: some View {
        List {
            Section {
                Text("Scenarios")
                    .font(.title2.bold())
                    .foregroundStyle(AppTheme.textPrimary)
                    .listRowBackground(Color.clear)

                VStack(spacing: 8) {
                    TextField("Name", text: $name).fieldStyle()
                    TextField("Amount", text: $amount).keyboardType(.decimalPad).fieldStyle()
                    Picker("Type", selection: $type) { ForEach(types, id: \.self, content: Text.init) }
                    Picker("Frequency", selection: $frequency) { ForEach(frequencies, id: \.self, content: Text.init) }
                    TextField("Start date (YYYY-MM-DD)", text: $startDate).fieldStyle()
                    Button("Add Scenario") { Task { await addScenario() } }
                        .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()
                .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                .listRowBackground(Color.clear)

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .listRowBackground(Color.clear)
                }
            }

            Section("Existing Scenarios") {
                if scenarios.isEmpty {
                    Text("No scenarios yet.")
                        .foregroundStyle(AppTheme.textMuted)
                }

                ForEach(scenarios) { scenario in
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 14) {
                            VStack(alignment: .leading) {
                                Text(scenario.name).foregroundStyle(AppTheme.textPrimary)
                                Text("\(scenario.frequency) · \(scenario.start_date)").font(.caption).foregroundStyle(AppTheme.textMuted)
                            }
                            Spacer(minLength: 16)
                            Text("$\(scenario.amount)")
                                .foregroundStyle(scenario.type == "Expense" ? AppTheme.danger : AppTheme.success)
                            Button(role: .destructive) { Task { await deleteScenario(scenario.id) } } label: {
                                Image(systemName: "trash")
                            }
                        }
                        .frame(minWidth: 340, alignment: .leading)
                    }
                    .surfaceCard()
                    .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                    .listRowBackground(Color.clear)
                }
            }
        }
        .listStyle(.plain)
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("Scenarios")
    }

    private func load() async {
        guard let token = session.token else { return }
        do {
            let response: APIListEnvelope<ScenarioDTO> = try await APIClient.shared.request(
                "scenarios",
                queryItems: [
                    URLQueryItem(name: "limit", value: "100"),
                    URLQueryItem(name: "offset", value: "0")
                ],
                token: token,
                as: APIListEnvelope<ScenarioDTO>.self
            )
            await MainActor.run { scenarios = response.data }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load scenarios" }
        }
    }

    private func addScenario() async {
        guard let token = session.token else { return }
        do {
            struct Payload: Encodable {
                let name: String
                let amount: String
                let type: String
                let frequency: String
                let start_date: String
            }
            _ = try await APIClient.shared.request(
                "scenarios",
                method: "POST",
                token: token,
                body: Payload(name: name, amount: amount, type: type, frequency: frequency, start_date: startDate),
                as: APIEnvelope<ScenarioDTO>.self
            )
            await load()
            await MainActor.run { name = ""; amount = "" }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to add scenario" }
        }
    }

    private func deleteScenario(_ id: Int) async {
        guard let token = session.token else { return }
        do {
            let _: EmptyResponse = try await APIClient.shared.request("scenarios/\(id)", method: "DELETE", token: token, as: EmptyResponse.self)
            await load()
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to delete scenario" }
        }
    }
}
