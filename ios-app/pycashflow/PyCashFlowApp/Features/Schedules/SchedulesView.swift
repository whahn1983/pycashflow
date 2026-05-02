import SwiftUI

struct SchedulesView: View {
    @EnvironmentObject var session: SessionManager
    @State private var schedules: [ScheduleDTO] = []
    @State private var showAddForm = false
    @State private var name = ""
    @State private var amount = ""
    @State private var type = "Expense"
    @State private var frequency = "Monthly"
    @State private var startDate = Date()
    @State private var editingID: Int?
    @State private var editName = ""
    @State private var editAmount = ""
    @State private var editType = "Expense"
    @State private var editFrequency = "Monthly"
    @State private var editStartDate = Date()
    @State private var errorText: String?
    @State private var statusText: String?

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
                        Text(showAddForm ? "Cancel" : "Add Schedule")
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
                        DatePicker("Start date", selection: $startDate, displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .fieldStyle()
                        Button("Save Schedule") { Task { await addSchedule() } }
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

                if let statusText {
                    Text(statusText)
                        .foregroundStyle(AppTheme.success)
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
                    VStack(alignment: .leading, spacing: 10) {
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
                        }

                        if editingID == schedule.id {
                            VStack(spacing: 8) {
                                TextField("Name", text: $editName).fieldStyle()
                                TextField("Amount", text: $editAmount).keyboardType(.decimalPad).fieldStyle()
                                pickerRow(label: "Type", selection: $editType, options: types)
                                pickerRow(label: "Frequency", selection: $editFrequency, options: frequencies)
                                DatePicker("Start date", selection: $editStartDate, displayedComponents: .date)
                                    .datePickerStyle(.compact)
                                    .fieldStyle()
                                HStack(spacing: 8) {
                                    Button("Save") { Task { await saveEdit(schedule.id) } }
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
                    .swipeActions(edge: .leading, allowsFullSwipe: true) {
                        Button {
                            beginEdit(schedule)
                        } label: {
                            Label("Edit", systemImage: "pencil.circle.fill")
                        }
                        .tint(AppTheme.accent)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            Task { await deleteSchedule(schedule.id) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .tint(AppTheme.danger)

                        Button {
                            Task { await addHold(schedule.id) }
                        } label: {
                            Label("Hold", systemImage: "pause.circle.fill")
                        }
                        .tint(AppTheme.warning)

                        Button {
                            Task { await addSkip(schedule.id) }
                        } label: {
                            Label("Skip", systemImage: "forward.circle.fill")
                        }
                        .tint(AppTheme.warning)
                    }
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

    private static let apiDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    private static func parseAPIDate(_ value: String) -> Date {
        apiDateFormatter.date(from: value) ?? Date()
    }

    private static func formatAPIDate(_ value: Date) -> String {
        apiDateFormatter.string(from: value)
    }

    private func resetAddForm() {
        name = ""
        amount = ""
        type = "Expense"
        frequency = "Monthly"
        startDate = Date()
        errorText = nil
    }

    private func beginEdit(_ schedule: ScheduleDTO) {
        editingID = schedule.id
        editName = schedule.name
        editAmount = schedule.amount
        editType = schedule.type
        editFrequency = schedule.frequency
        editStartDate = Self.parseAPIDate(schedule.start_date)
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
                body: Payload(name: name, amount: amount, type: type, frequency: frequency, start_date: Self.formatAPIDate(startDate)),
                as: APIEnvelope<ScheduleDTO>.self
            )
            await load()
            await MainActor.run {
                resetAddForm()
                showAddForm = false
            }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to add schedule" }
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
                "schedules/\(id)",
                method: "PUT",
                token: token,
                body: Payload(name: editName, amount: editAmount, type: editType, frequency: editFrequency, start_date: Self.formatAPIDate(editStartDate)),
                as: APIEnvelope<ScheduleDTO>.self
            )
            await load()
            await MainActor.run { editingID = nil }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to update schedule" }
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

    private func addHold(_ scheduleID: Int) async {
        guard let token = session.token else { return }
        do {
            struct Payload: Encodable { let schedule_id: Int }
            let _: APIEnvelope<HoldDTO> = try await APIClient.shared.request(
                "holds",
                method: "POST",
                token: token,
                body: Payload(schedule_id: scheduleID),
                as: APIEnvelope<HoldDTO>.self
            )
            await MainActor.run { statusText = "Added to Holds"; errorText = nil }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to add hold"; statusText = nil }
        }
    }

    private func addSkip(_ scheduleID: Int) async {
        guard let token = session.token else { return }
        do {
            struct Payload: Encodable { let schedule_id: Int }
            let _: APIEnvelope<SkipDTO> = try await APIClient.shared.request(
                "skips",
                method: "POST",
                token: token,
                body: Payload(schedule_id: scheduleID),
                as: APIEnvelope<SkipDTO>.self
            )
            await MainActor.run { statusText = "Added to Skips"; errorText = nil }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to add skip"; statusText = nil }
        }
    }
}
