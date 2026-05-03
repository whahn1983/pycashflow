import SwiftUI

/// Floating bottom navigation bar with a native-feeling glass treatment,
/// springy morphing selection pill, and reduced-motion fallback.
struct FloatingNavBar: View {
    let items: [FloatingNavItem]
    @Binding var selectedSection: AppSection
    let isDisabled: Bool

    @Namespace private var selectionNamespace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ViewThatFits(in: .horizontal) {
            navContainer {
                HStack(spacing: 6) {
                    navButtons
                }
            }

            navContainer {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        navButtons
                    }
                    .padding(.horizontal, 4)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 8)
    }

    @ViewBuilder
    private var navButtons: some View {
        ForEach(items) { item in
            let isSelected = selectedSection == item.section

            Button {
                withAnimation(tabSelectionAnimation) {
                    selectedSection = item.section
                }
            } label: {
                FloatingNavItemLabel(item: item, isSelected: isSelected)
                    .frame(maxWidth: .infinity)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .background {
                if isSelected {
                    selectionPill
                } else {
                    Capsule(style: .continuous)
                        .fill(.clear)
                }
            }
            .accessibilityLabel(item.title)
            .disabled(isDisabled)
            .animation(reduceMotion ? .easeOut(duration: 0.15) : tabSelectionAnimation, value: isSelected)
        }
    }

    private var selectionPill: some View {
        Capsule(style: .continuous)
            .fill(.white.opacity(0.18))
            .overlay {
                Capsule(style: .continuous)
                    .stroke(.white.opacity(0.24), lineWidth: 0.8)
            }
            .shadow(color: .black.opacity(0.18), radius: 8, x: 0, y: 4)
            .matchedGeometryEffect(id: "tab-selection", in: selectionNamespace)
    }

    private var tabSelectionAnimation: Animation {
        reduceMotion
            ? .easeOut(duration: 0.14)
            : .spring(response: 0.38, dampingFraction: 0.82, blendDuration: 0.12)
    }

    private func navContainer<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background {
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        RoundedRectangle(cornerRadius: 28, style: .continuous)
                            .stroke(.white.opacity(0.12), lineWidth: 0.6)
                    }
                    .shadow(color: .black.opacity(0.18), radius: 16, x: 0, y: 6)
            }
        }
}

/// Small circular button cluster used as the navigation affordance for
/// guest users (Dashboard + Settings).
struct GuestSettingsButton: View {
    @Binding var selectedSection: AppSection
    let isDisabled: Bool

    var body: some View {
        HStack(spacing: 12) {
            guestButton(systemImage: "house", label: "Dashboard", section: .dashboard)
            guestButton(systemImage: "gearshape", label: "Settings", section: .settings)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 8)
    }

    private func guestButton(systemImage: String, label: String, section: AppSection) -> some View {
        Button {
            selectedSection = section
        } label: {
            Image(systemName: systemImage)
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(AppTheme.textPrimary)
                .frame(width: 48, height: 48)
        }
        .buttonStyle(.plain)
        .background(
            Circle()
                .fill(selectedSection == section ? AnyShapeStyle(.white.opacity(0.2)) : AnyShapeStyle(.ultraThinMaterial))
                .overlay(Circle().stroke(.white.opacity(0.14), lineWidth: 0.8))
        )
        .shadow(color: .black.opacity(0.16), radius: 10, x: 0, y: 4)
        .disabled(isDisabled)
        .accessibilityLabel(label)
    }
}

struct FloatingNavItem: Identifiable {
    let id = UUID()
    let title: String
    let systemImage: String
    let section: AppSection
}

private struct FloatingNavItemLabel: View {
    let item: FloatingNavItem
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 2) {
            Image(systemName: item.systemImage)
                .font(.system(size: 18, weight: isSelected ? .semibold : .medium))
            Text(item.title)
                .font(.caption2.weight(isSelected ? .semibold : .medium))
                .lineLimit(1)
        }
        .foregroundStyle(isSelected ? AppTheme.textPrimary : AppTheme.textSecondary.opacity(0.9))
        .frame(minWidth: 64, minHeight: 44)
    }
}
