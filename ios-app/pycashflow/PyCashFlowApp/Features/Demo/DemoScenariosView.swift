import SwiftUI

struct DemoScenariosView: View {
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

    private let types = DemoStore.validTypes
    private let frequencies = DemoStore.validFrequencies

    private var sortedScenarios: [DemoScenario] {
        store.state.scenarios.sorted {
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
                        DatePicker("Start date", selection: $startDate, displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .fieldStyle()
                        Button("Save Scenario") { addScenario() }
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
                if store.state.scenarios.isEmpty {
                    Text("No scenarios yet.")
                        .foregroundStyle(AppTheme.textMuted)
                }

                ForEach(sortedScenarios) { scenario in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(scenario.name)
                                    .foregroundStyle(AppTheme.textPrimary)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                Text("\(scenario.frequency) · \(scenario.startDate)")
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.textMuted)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.85)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            Text("$\(scenario.amountString)")
                                .foregroundStyle(scenario.type == "Expense" ? AppTheme.danger : AppTheme.success)
                                .lineLimit(1)
                                .minimumScaleFactor(0.7)
                                .layoutPriority(1)
                        }

                        if editingID == scenario.id {
                            VStack(spacing: 8) {
                                TextField("Name", text: $editName).fieldStyle()
                                TextField("Amount", text: $editAmount).keyboardType(.decimalPad).fieldStyle()
                                pickerRow(label: "Type", selection: $editType, options: types)
                                pickerRow(label: "Frequency", selection: $editFrequency, options: frequencies)
                                DatePicker("Start date", selection: $editStartDate, displayedComponents: .date)
                                    .datePickerStyle(.compact)
                                    .fieldStyle()
                                HStack(spacing: 8) {
                                    Button("Save") { saveEdit(scenario.id) }
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
                            beginEdit(scenario)
                        } label: {
                            Label("Edit", systemImage: "pencil.circle.fill")
                        }
                        .tint(AppTheme.accent)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            store.deleteScenario(id: scenario.id)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .tint(AppTheme.danger)
                    }
                }
            }
        }
        .listStyle(.plain)
        .appBackground()
        .navigationTitle("Scenarios")
        .localModeBanner()
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

    private func beginEdit(_ scenario: DemoScenario) {
        editingID = scenario.id
        editName = scenario.name
        editAmount = scenario.amountString
        editType = scenario.type
        editFrequency = scenario.frequency
        editStartDate = DemoScheduleDateFormat.date(from: scenario.startDate)
    }

    private func addScenario() {
        if let error = store.addScenario(
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
        if let error = store.updateScenario(
            id: id, name: editName, amountText: editAmount, type: editType, frequency: editFrequency,
            startDate: DemoScheduleDateFormat.demoDate(from: editStartDate)
        ) {
            errorText = error
            return
        }
        errorText = nil
        editingID = nil
    }
}
