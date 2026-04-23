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
                    Picker("Type", selection: $type) { ForEach(types, id: \.self, content: Text.init) }
                    Picker("Frequency", selection: $frequency) { ForEach(frequencies, id: \.self, content: Text.init) }
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
                        .listRowBackground(Color.clear)
                }
            }

            Section("Existing Schedules") {
                if schedules.isEmpty {
                    Text("No schedules yet.")
                        .foregroundStyle(AppTheme.textMuted)
                }

                ForEach(schedules) { schedule in
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 14) {
                            VStack(alignment: .leading) {
                                Text(schedule.name).foregroundStyle(AppTheme.textPrimary)
                                Text("\(schedule.frequency) · \(schedule.start_date)").font(.caption).foregroundStyle(AppTheme.textMuted)
                            }
                            Spacer(minLength: 16)
                            Text("$\(schedule.amount)")
                                .foregroundStyle(schedule.type == "Expense" ? AppTheme.danger : AppTheme.success)
                            Button(role: .destructive) { Task { await deleteSchedule(schedule.id) } } label: {
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
        .navigationTitle("Schedules")
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
