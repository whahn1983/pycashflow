import SwiftUI

struct DemoHoldsView: View {
    @EnvironmentObject private var store: DemoStore
    @State private var selectedTab: Tab = .holds

    private enum Tab: String, CaseIterable, Identifiable {
        case holds = "Holds"
        case skips = "Skips"
        var id: String { rawValue }
    }

    private var sortedSkips: [DemoSkip] {
        store.state.skips.sorted {
            let l = DemoScheduleDateFormat.parse($0.date)
            let r = DemoScheduleDateFormat.parse($1.date)
            if l == r { return $0.id < $1.id }
            return l < r
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            Picker("View", selection: $selectedTab) {
                ForEach(Tab.allCases) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 12)

            List {
                switch selectedTab {
                case .holds:
                    holdsSection
                case .skips:
                    skipsSection
                }
            }
            .listStyle(.plain)
        }
        .appBackground()
        .navigationTitle("Holds")
    }

    @ViewBuilder
    private var holdsSection: some View {
        Section("Current Holds") {
            if store.state.holds.isEmpty {
                Text("No holds.")
                    .foregroundStyle(AppTheme.textMuted)
                    .listRowBackground(Color.clear)
            }

            ForEach(store.state.holds) { hold in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(hold.name)
                            .foregroundStyle(AppTheme.textPrimary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                        Text(hold.type)
                            .font(.caption)
                            .foregroundStyle(AppTheme.textMuted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    Text("$\(hold.amountString)")
                        .foregroundStyle(hold.type == "Expense" ? AppTheme.danger : AppTheme.success)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .layoutPriority(1)
                }
                .surfaceCard()
                .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                .listRowBackground(Color.clear)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    Button(role: .destructive) {
                        store.deleteHold(id: hold.id)
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .tint(AppTheme.danger)
                }
            }
        }
    }

    @ViewBuilder
    private var skipsSection: some View {
        Section("Current Skips") {
            if store.state.skips.isEmpty {
                Text("No skips.")
                    .foregroundStyle(AppTheme.textMuted)
                    .listRowBackground(Color.clear)
            }

            ForEach(sortedSkips) { skip in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(skip.name)
                            .foregroundStyle(AppTheme.textPrimary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                        Text(skip.date)
                            .font(.caption)
                            .foregroundStyle(AppTheme.textMuted)
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    Text("$\(skip.amountString)")
                        .foregroundStyle(skip.type == "Expense" ? AppTheme.danger : AppTheme.success)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .layoutPriority(1)
                }
                .surfaceCard()
                .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                .listRowBackground(Color.clear)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    Button(role: .destructive) {
                        store.deleteSkip(id: skip.id)
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .tint(AppTheme.danger)
                }
            }
        }
    }
}
