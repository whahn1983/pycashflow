import SwiftUI

struct ScenariosView: View {
    @EnvironmentObject var session: SessionManager
    @State private var scenarios: [ScenarioDTO] = []
    @State private var showAddForm = false
    @State private var name = ""
    @State private var amount = ""
    @State private var type = "Expense"
    @State private var frequency = "Monthly"
    @State private var startDate = defaultStartDate()
    @State private var editingID: Int?
    @State private var editName = ""
    @State private var editAmount = ""
    @State private var editType = "Expense"
    @State private var editFrequency = "Monthly"
    @State private var editStartDate = defaultStartDate()
    @State private var errorText: String?

    private let types = ["Expense", "Income"]
    private let frequencies = ["Monthly", "Quarterly", "Yearly", "Weekly", "BiWeekly", "Onetime"]

    var body: some View {
        List {
            Section {
                Button {
                    withAnimation {
                        showAddForm.toggle()
                        if !showAddForm { resetAddForm() }
                    }
                } label: {
                    HStack {
                        Image(systemName: showAddForm ? "xmark.circle" : "plus.circle.fill")
                        Text(showAddForm ? "Cancel" : "Add Scenario")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                .listRowBackground(Color.clear)

                if showAddForm {
                    VStack(spacing: 8) {
                        TextField("Name", text: $name).fieldStyle()
                        TextField("Amount", text: $amount).keyboardType(.decimalPad).fieldStyle()
                        pickerRow(label: "Type", selection: $type, options: types)
                        pickerRow(label: "Frequency", selection: $frequency, options: frequencies)
                        TextField("Start date (YYYY-MM-DD)", text: $startDate).fieldStyle()
                        Button("Save Scenario") { Task { await addScenario() } }
                            .buttonStyle(PrimaryButtonStyle())
                    }
                    .surfaceCard()
                    .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                    .listRowBackground(Color.clear)
                }

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .listRowBackground(Color.clear)
                }
            }

            Section("Existing Scenarios") {
                if scenarios.isEmpty {
                    Text("No scenarios yet.")
                        .foregroundStyle(AppTheme.textMuted)
                }

                ForEach(scenarios) { scenario in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(scenario.name)
                                    .foregroundStyle(AppTheme.textPrimary)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                Text("\(scenario.frequency) · \(scenario.start_date)")
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.textMuted)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.85)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            Text("$\(scenario.amount)")
                                .foregroundStyle(scenario.type == "Expense" ? AppTheme.danger : AppTheme.success)
                                .lineLimit(1)
                                .minimumScaleFactor(0.7)
                                .layoutPriority(1)
                        }

                        HStack(spacing: 16) {
                            iconButton(systemName: "pencil", color: AppTheme.accent, label: "Edit") {
                                beginEdit(scenario)
                            }
                            iconButton(systemName: "trash", color: AppTheme.danger, label: "Delete") {
                                Task { await deleteScenario(scenario.id) }
                            }
                        }

                        if editingID == scenario.id {
                            VStack(spacing: 8) {
                                TextField("Name", text: $editName).fieldStyle()
                                TextField("Amount", text: $editAmount).keyboardType(.decimalPad).fieldStyle()
                                pickerRow(label: "Type", selection: $editType, options: types)
                                pickerRow(label: "Frequency", selection: $editFrequency, options: frequencies)
                                TextField("Start date (YYYY-MM-DD)", text: $editStartDate).fieldStyle()
                                HStack(spacing: 8) {
                                    Button("Save") { Task { await saveEdit(scenario.id) } }
                                        .buttonStyle(PrimaryButtonStyle())
                                    Button("Cancel") { editingID = nil }
                                        .buttonStyle(PrimaryButtonStyle())
                                }
                            }
                            .padding(.top, 4)
                        }
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

    private func iconButton(systemName: String, color: Color, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Image(systemName: systemName)
                    .font(.system(size: 16, weight: .semibold))
                Text(label)
                    .font(.caption2)
            }
            .foregroundStyle(color)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderless)
    }

    private func pickerRow(label: String, selection: Binding<String>, options: [String]) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .foregroundStyle(AppTheme.textSecondary)
                .lineLimit(1)
            Spacer(minLength: 8)
            Picker(label, selection: selection) {
                ForEach(options, id: \.self, content: Text.init)
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .tint(AppTheme.textPrimary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
    }

    private static func defaultStartDate() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private func resetAddForm() {
        name = ""
        amount = ""
        type = "Expense"
        frequency = "Monthly"
        startDate = Self.defaultStartDate()
        errorText = nil
    }

    private func beginEdit(_ scenario: ScenarioDTO) {
        editingID = scenario.id
        editName = scenario.name
        editAmount = scenario.amount
        editType = scenario.type
        editFrequency = scenario.frequency
        editStartDate = scenario.start_date
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
            await MainActor.run {
                resetAddForm()
                showAddForm = false
            }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to add scenario" }
        }
    }

    private func saveEdit(_ id: Int) async {
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
                "scenarios/\(id)",
                method: "PUT",
                token: token,
                body: Payload(name: editName, amount: editAmount, type: editType, frequency: editFrequency, start_date: editStartDate),
                as: APIEnvelope<ScenarioDTO>.self
            )
            await load()
            await MainActor.run { editingID = nil }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to update scenario" }
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
