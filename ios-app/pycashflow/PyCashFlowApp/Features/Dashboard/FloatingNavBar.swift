import SwiftUI

/// Floating bottom navigation bar rendered with the iOS 26 Liquid Glass
/// material so it matches the translucent back button SwiftUI renders in
/// the navigation bar. Scrolls horizontally when buttons overflow.
struct FloatingNavBar: View {
    let items: [FloatingNavItem]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(items) { item in
                    NavigationLink {
                        item.destination
                    } label: {
                        FloatingNavItemLabel(item: item)
                    }
                    .buttonStyle(FloatingNavButtonStyle())
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
        }
        .glassEffect(.regular.interactive(), in: Capsule(style: .continuous))
        .padding(.horizontal, 16)
    }
}

struct FloatingNavItem: Identifiable {
    let id = UUID()
    let title: String
    let systemImage: String
    let destination: AnyView

    init<Destination: View>(title: String, systemImage: String, @ViewBuilder destination: () -> Destination) {
        self.title = title
        self.systemImage = systemImage
        self.destination = AnyView(destination())
    }
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
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                Capsule(style: .continuous)
                    .fill(configuration.isPressed ? AppTheme.accent.opacity(0.25) : Color.clear)
            )
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
