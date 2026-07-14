import SwiftUI

struct DemoSchedulesView: View {
    @EnvironmentObject private var store: DemoStore

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

    private let types = DemoStore.validTypes
    private let frequencies = DemoStore.validFrequencies

    private var sortedSchedules: [DemoSchedule] {
        store.state.schedules.sorted {
            let l = DemoScheduleDateFormat.parse($0.startDate)
            let r = DemoScheduleDateFormat.parse($1.startDate)
            if l == r { return $0.id < $1.id }
            return l < r
        }
    }

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
                        Button("Save Schedule") { addSchedule() }
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
                if store.state.schedules.isEmpty {
                    Text("No schedules yet.")
                        .foregroundStyle(AppTheme.textMuted)
                }

                ForEach(sortedSchedules) { schedule in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(schedule.name)
                                    .foregroundStyle(AppTheme.textPrimary)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                Text("\(schedule.frequency) · \(schedule.startDate)")
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.textMuted)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.85)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            Text("$\(schedule.amountString)")
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
                                    Button("Save") { saveEdit(schedule.id) }
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
                            store.deleteSchedule(id: schedule.id)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .tint(AppTheme.danger)

                        Button {
                            addHold(schedule.id)
                        } label: {
                            Label("Hold", systemImage: "pause.circle.fill")
                        }
                        .tint(AppTheme.warning)

                        Button {
                            addSkip(schedule.id)
                        } label: {
                            Label("Skip", systemImage: "forward.circle.fill")
                        }
                        .tint(AppTheme.warning)
                    }
                }
            }
        }
        .listStyle(.plain)
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

    private func resetAddForm() {
        name = ""
        amount = ""
        type = "Expense"
        frequency = "Monthly"
        startDate = Date()
        errorText = nil
    }

    private func beginEdit(_ schedule: DemoSchedule) {
        editingID = schedule.id
        editName = schedule.name
        editAmount = schedule.amountString
        editType = schedule.type
        editFrequency = schedule.frequency
        editStartDate = DemoScheduleDateFormat.date(from: schedule.startDate)
    }

    private func addSchedule() {
        if let error = store.addSchedule(
            name: name, amountText: amount, type: type, frequency: frequency,
            startDate: DemoScheduleDateFormat.demoDate(from: startDate)
        ) {
            errorText = error
            return
        }
        resetAddForm()
        showAddForm = false
    }

    private func saveEdit(_ id: Int) {
        if let error = store.updateSchedule(
            id: id, name: editName, amountText: editAmount, type: editType, frequency: editFrequency,
            startDate: DemoScheduleDateFormat.demoDate(from: editStartDate)
        ) {
            errorText = error
            return
        }
        errorText = nil
        editingID = nil
    }

    private func addHold(_ scheduleID: Int) {
        if let error = store.addHold(fromScheduleID: scheduleID) {
            errorText = error
            statusText = nil
        } else {
            statusText = "Added to Holds"
            errorText = nil
        }
    }

    private func addSkip(_ scheduleID: Int) {
        if let error = store.addSkip(fromScheduleID: scheduleID) {
            errorText = error
            statusText = nil
        } else {
            statusText = "Added to Skips"
            errorText = nil
        }
    }
}

/// Shared `yyyy-MM-dd` <-> `Date`/`DemoDate` conversion for the Demo form
/// pickers (uses the device calendar so the `DatePicker` value round-trips).
enum DemoScheduleDateFormat {
    private static let formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    static func parse(_ value: String) -> Date {
        formatter.date(from: value) ?? Date()
    }

    static func date(from value: String) -> Date {
        formatter.date(from: value) ?? Date()
    }

    static func string(from value: Date) -> String {
        formatter.string(from: value)
    }

    static func demoDate(from value: Date) -> DemoDate {
        let comps = Calendar.current.dateComponents([.year, .month, .day], from: value)
        return DemoDate(comps.year ?? 2000, comps.month ?? 1, comps.day ?? 1)
    }
}
