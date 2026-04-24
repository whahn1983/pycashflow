import SwiftUI

struct SchedulesView: View {
    @EnvironmentObject var session: SessionManager
    @State private var schedules: [ScheduleDTO] = []
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
                Text("Schedules")
                    .font(.title2.bold())
                    .foregroundStyle(AppTheme.textPrimary)
                    .listRowBackground(Color.clear)

                VStack(spacing: 8) {
                    TextField("Name", text: $name).fieldStyle()
                    TextField("Amount", text: $amount).keyboardType(.decimalPad).fieldStyle()
                    pickerRow(label: "Type", selection: $type, options: types)
                    pickerRow(label: "Frequency", selection: $frequency, options: frequencies)
                    TextField("Start date (YYYY-MM-DD)", text: $startDate).fieldStyle()
                    Button("Add Schedule") { Task { await addSchedule() } }
                        .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()
                .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                .listRowBackground(Color.clear)

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .listRowBackground(Color.clear)
                }
            }

            Section("Existing Schedules") {
                if schedules.isEmpty {
                    Text("No schedules yet.")
                        .foregroundStyle(AppTheme.textMuted)
                }

                ForEach(schedules) { schedule in
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(schedule.name)
                                .foregroundStyle(AppTheme.textPrimary)
                                .lineLimit(1)
                                .truncationMode(.tail)
                            Text("\(schedule.frequency) · \(schedule.start_date)")
                                .font(.caption)
                                .foregroundStyle(AppTheme.textMuted)
                                .lineLimit(1)
                                .minimumScaleFactor(0.85)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        Text("$\(schedule.amount)")
                            .foregroundStyle(schedule.type == "Expense" ? AppTheme.danger : AppTheme.success)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .layoutPriority(1)

                        Button(role: .destructive) { Task { await deleteSchedule(schedule.id) } } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
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
        .navigationTitle("Schedules")
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

    private func load() async {
        guard let token = session.token else { return }
        do {
            let response: APIListEnvelope<ScheduleDTO> = try await APIClient.shared.request(
                "schedules",
                queryItems: [
                    URLQueryItem(name: "limit", value: "100"),
                    URLQueryItem(name: "offset", value: "0")
                ],
                token: token,
                as: APIListEnvelope<ScheduleDTO>.self
            )
            await MainActor.run { schedules = response.data }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load schedules" }
        }
    }

    private func addSchedule() async {
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
                "schedules",
                method: "POST",
                token: token,
                body: Payload(name: name, amount: amount, type: type, frequency: frequency, start_date: startDate),
                as: APIEnvelope<ScheduleDTO>.self
            )
            await load()
            await MainActor.run { name = ""; amount = "" }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to add schedule" }
        }
    }

    private func deleteSchedule(_ id: Int) async {
        guard let token = session.token else { return }
        do {
            let _: EmptyResponse = try await APIClient.shared.request("schedules/\(id)", method: "DELETE", token: token, as: EmptyResponse.self)
            await load()
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to delete schedule" }
        }
    }
}
