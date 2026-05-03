import SwiftUI

/// Floating bottom navigation bar rendered with the iOS 26 Liquid Glass
/// material. The selected tab is highlighted by a tinted glass pill that
/// morphs between buttons via `GlassEffectContainer` + `glassEffectID`,
/// producing the native liquid morphing transition.
struct FloatingNavBar: View {
    let items: [FloatingNavItem]
    @Binding var selectedSection: AppSection
    let isDisabled: Bool

    @Namespace private var glassNamespace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GlassEffectContainer(spacing: 6) {
            ViewThatFits(in: .horizontal) {
                navContent

                ScrollView(.horizontal, showsIndicators: false) {
                    navContent
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16)
    }

    private var navContent: some View {
        HStack(spacing: 4) {
            ForEach(items) { item in
                let isSelected = selectedSection == item.section

                Button {
                    withAnimation(selectionAnimation) {
                        selectedSection = item.section
                    }
                } label: {
                    FloatingNavItemLabel(item: item, isSelected: isSelected)
                }
                .buttonStyle(.plain)
                .disabled(isDisabled)
                .background {
                    if isSelected {
                        Capsule(style: .continuous)
                            .fill(Color.clear)
                            .glassEffect(
                                .regular
                                    .tint(AppTheme.accent.opacity(0.55))
                                    .interactive(),
                                in: Capsule(style: .continuous)
                            )
                            .glassEffectID("selectedTab", in: glassNamespace)
                    }
                }
                .accessibilityLabel(item.title)
                .accessibilityAddTraits(isSelected ? .isSelected : [])
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background {
            Capsule(style: .continuous)
                .fill(Color.clear)
                .glassEffect(.regular.interactive(), in: Capsule(style: .continuous))
        }
    }

    private var selectionAnimation: Animation {
        reduceMotion
            ? .easeOut(duration: 0.18)
            : .smooth(duration: 0.45, extraBounce: 0.18)
    }
}

/// Small circular Liquid Glass button cluster used as the navigation
/// affordance for guest users (Dashboard + Settings).
struct GuestSettingsButton: View {
    @Binding var selectedSection: AppSection
    let isDisabled: Bool

    @Namespace private var glassNamespace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GlassEffectContainer(spacing: 6) {
            HStack(spacing: 12) {
                guestButton(systemImage: "house", label: "Dashboard", section: .dashboard)
                guestButton(systemImage: "gearshape", label: "Settings", section: .settings)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
        }
    }

    private func guestButton(systemImage: String, label: String, section: AppSection) -> some View {
        let isSelected = selectedSection == section

        return Button {
            withAnimation(selectionAnimation) {
                selectedSection = section
            }
        } label: {
            Image(systemName: systemImage)
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(AppTheme.textPrimary)
                .frame(width: 48, height: 48)
        }
        .buttonStyle(.plain)
        .background {
            Circle()
                .fill(Color.clear)
                .glassEffect(
                    isSelected
                        ? .regular.tint(AppTheme.accent.opacity(0.55)).interactive()
                        : .regular.interactive(),
                    in: Circle()
                )
                .glassEffectID(isSelected ? "guestSelected" : "guest-\(section)", in: glassNamespace)
        }
        .disabled(isDisabled)
        .accessibilityLabel(label)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    private var selectionAnimation: Animation {
        reduceMotion
            ? .easeOut(duration: 0.18)
            : .smooth(duration: 0.4, extraBounce: 0.15)
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
        .foregroundStyle(AppTheme.textPrimary)
        .frame(minWidth: 64, minHeight: 44)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .contentShape(Capsule(style: .continuous))
    }
}
