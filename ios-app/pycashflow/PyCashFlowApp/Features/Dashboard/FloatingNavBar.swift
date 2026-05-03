import SwiftUI

/// Floating bottom navigation bar rendered with the iOS 26 Liquid Glass
/// material so it matches the translucent back button SwiftUI renders in
/// the navigation bar. Sizes to fit its buttons and stays horizontally
/// centered, falling back to a horizontal scroll view only when the
/// available width is too narrow to fit every button.
struct FloatingNavBar: View {
    let items: [FloatingNavItem]
    @Binding var selectedSection: AppSection
    let isDisabled: Bool

    var body: some View {
        ViewThatFits(in: .horizontal) {
            navContent
                .glassEffect(.regular.interactive(), in: Capsule(style: .continuous))

            ScrollView(.horizontal, showsIndicators: false) {
                navContent
            }
            .glassEffect(.regular.interactive(), in: Capsule(style: .continuous))
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16)
    }

    private var navContent: some View {
        HStack(spacing: 4) {
            ForEach(items) { item in
                Button {
                    selectedSection = item.section
                } label: {
                    FloatingNavItemLabel(item: item)
                }
                .buttonStyle(FloatingNavButtonStyle(isSelected: selectedSection == item.section))
                .disabled(isDisabled)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
    }
}

/// Small circular Liquid Glass button anchored to the bottom-right, used
/// as the only navigation affordance for guest users (Settings access).
struct GuestSettingsButton: View {
    @Binding var selectedSection: AppSection
    let isDisabled: Bool

    var body: some View {
        HStack(spacing: 12) {
            guestButton(systemImage: "house", section: .dashboard)
            guestButton(systemImage: "gearshape", section: .settings)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 8)
    }

    private func guestButton(systemImage: String, section: AppSection) -> some View {
        Button {
            selectedSection = section
        } label: {
            Image(systemName: systemImage)
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(AppTheme.textPrimary)
                .frame(width: 48, height: 48)
        }
        .buttonStyle(FloatingNavButtonStyle(isSelected: selectedSection == section))
        .disabled(isDisabled)
        .glassEffect(.regular.interactive(), in: Circle())
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

    var body: some View {
        VStack(spacing: 2) {
            Image(systemName: item.systemImage)
                .font(.system(size: 20, weight: .semibold))
            Text(item.title)
                .font(.caption2.weight(.medium))
                .lineLimit(1)
        }
        .foregroundStyle(AppTheme.textPrimary)
        .frame(minWidth: 64)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }
}

private struct FloatingNavButtonStyle: ButtonStyle {
    let isSelected: Bool

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed

        configuration.label
            .background(
                ZStack {
                    if isSelected || pressed {
                        Capsule(style: .continuous)
                            .fill(AppTheme.accent.opacity(pressed ? 0.30 : 0.22))
                            .overlay(
                                Capsule(style: .continuous)
                                    .stroke(.white.opacity(pressed ? 0.28 : 0.18), lineWidth: 1)
                            )
                            .glassEffect(.regular.interactive(), in: Capsule(style: .continuous))
                    }
                }
            )
            .scaleEffect(pressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: pressed)
            .animation(.easeOut(duration: 0.18), value: isSelected)
    }
}
