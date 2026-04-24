import SwiftUI

struct HoldsView: View {
    @EnvironmentObject var session: SessionManager
    @State private var holds: [HoldDTO] = []
    @State private var skips: [SkipDTO] = []
    @State private var selectedTab: Tab = .holds
    @State private var holdsError: String?
    @State private var skipsError: String?
    @State private var holdsStatus: String?
    @State private var skipsStatus: String?

    private enum Tab: String, CaseIterable, Identifiable {
        case holds = "Holds"
        case skips = "Skips"

        var id: String { rawValue }
    }

    private var currentError: String? {
        switch selectedTab {
        case .holds: return holdsError
        case .skips: return skipsError
        }
    }

    private var currentStatus: String? {
        switch selectedTab {
        case .holds: return holdsStatus
        case .skips: return skipsStatus
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
                if let currentError {
                    Text(currentError)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .listRowBackground(Color.clear)
                }

                if let currentStatus {
                    Text(currentStatus)
                        .foregroundStyle(AppTheme.success)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .listRowBackground(Color.clear)
                }

                switch selectedTab {
                case .holds:
                    holdsSection
                case .skips:
                    skipsSection
                }
            }
            .listStyle(.plain)
        }
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("Holds")
    }

    @ViewBuilder
    private var holdsSection: some View {
        Section("Current Holds") {
            if holds.isEmpty {
                Text("No holds.")
                    .foregroundStyle(AppTheme.textMuted)
                    .listRowBackground(Color.clear)
            }

            ForEach(holds) { hold in
                VStack(alignment: .leading, spacing: 10) {
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

                        Text("$\(hold.amount)")
                            .foregroundStyle(hold.type == "Expense" ? AppTheme.danger : AppTheme.success)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .layoutPriority(1)
                    }

                    HStack {
                        Spacer()
                        iconButton(systemName: "trash", color: AppTheme.danger, label: "Delete") {
                            Task { await deleteHold(hold.id) }
                        }
                    }
                }
                .surfaceCard()
                .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                .listRowBackground(Color.clear)
            }
        }
    }

    @ViewBuilder
    private var skipsSection: some View {
        Section("Current Skips") {
            if skips.isEmpty {
                Text("No skips.")
                    .foregroundStyle(AppTheme.textMuted)
                    .listRowBackground(Color.clear)
            }

            ForEach(skips) { skip in
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(skip.name)
                                .foregroundStyle(AppTheme.textPrimary)
                                .lineLimit(1)
                                .truncationMode(.tail)
                            Text(skip.date ?? skip.type)
                                .font(.caption)
                                .foregroundStyle(AppTheme.textMuted)
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        Text("$\(skip.amount)")
                            .foregroundStyle(skip.type == "Expense" ? AppTheme.danger : AppTheme.success)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .layoutPriority(1)
                    }

                    HStack {
                        Spacer()
                        iconButton(systemName: "trash", color: AppTheme.danger, label: "Delete") {
                            Task { await deleteSkip(skip.id) }
                        }
                    }
                }
                .surfaceCard()
                .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                .listRowBackground(Color.clear)
            }
        }
    }

    private func iconButton(systemName: String, color: Color, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: systemName)
                    .font(.system(size: 14, weight: .semibold))
                Text(label)
                    .font(.caption)
            }
            .foregroundStyle(color)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(color.opacity(0.15), in: Capsule())
        }
        .buttonStyle(.borderless)
    }

    private func load() async {
        async let holdsTask = loadHolds()
        async let skipsTask = loadSkips()
        _ = await (holdsTask, skipsTask)
    }

    @discardableResult
    private func loadHolds() async -> Bool {
        guard let token = session.token else { return false }
        do {
            let response: APIListEnvelope<HoldDTO> = try await APIClient.shared.request(
                "holds",
                queryItems: [
                    URLQueryItem(name: "limit", value: "100"),
                    URLQueryItem(name: "offset", value: "0")
                ],
                token: token,
                as: APIListEnvelope<HoldDTO>.self
            )
            await MainActor.run {
                holds = response.data
                holdsError = nil
            }
            return true
        } catch {
            await MainActor.run {
                holdsError = (error as? APIErrorEnvelope)?.error ?? "Failed to load holds"
            }
            return false
        }
    }

    @discardableResult
    private func loadSkips() async -> Bool {
        guard let token = session.token else { return false }
        do {
            let response: APIListEnvelope<SkipDTO> = try await APIClient.shared.request(
                "skips",
                queryItems: [
                    URLQueryItem(name: "limit", value: "100"),
                    URLQueryItem(name: "offset", value: "0")
                ],
                token: token,
                as: APIListEnvelope<SkipDTO>.self
            )
            await MainActor.run {
                skips = response.data
                skipsError = nil
            }
            return true
        } catch {
            await MainActor.run {
                skipsError = (error as? APIErrorEnvelope)?.error ?? "Failed to load skips"
            }
            return false
        }
    }

    private func deleteHold(_ id: Int) async {
        guard let token = session.token else { return }
        do {
            let _: EmptyResponse = try await APIClient.shared.request(
                "holds/\(id)",
                method: "DELETE",
                token: token,
                as: EmptyResponse.self
            )
            let refreshed = await loadHolds()
            await MainActor.run {
                if refreshed {
                    holdsStatus = "Hold removed"
                } else {
                    holdsStatus = nil
                }
            }
        } catch {
            await MainActor.run {
                holdsError = (error as? APIErrorEnvelope)?.error ?? "Failed to delete hold"
                holdsStatus = nil
            }
        }
    }

    private func deleteSkip(_ id: Int) async {
        guard let token = session.token else { return }
        do {
            let _: EmptyResponse = try await APIClient.shared.request(
                "skips/\(id)",
                method: "DELETE",
                token: token,
                as: EmptyResponse.self
            )
            let refreshed = await loadSkips()
            await MainActor.run {
                if refreshed {
                    skipsStatus = "Skip removed"
                } else {
                    skipsStatus = nil
                }
            }
        } catch {
            await MainActor.run {
                skipsError = (error as? APIErrorEnvelope)?.error ?? "Failed to delete skip"
                skipsStatus = nil
            }
        }
    }
}
