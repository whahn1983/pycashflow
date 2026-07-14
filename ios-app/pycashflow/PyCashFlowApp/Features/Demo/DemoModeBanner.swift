import Combine
import SwiftUI

/// Shared Demo-mode navigation state so the persistent banner and the Settings
/// card can both open the subscription paywall.
@MainActor
final class DemoNavigation: ObservableObject {
    @Published var showPaywall = false

    func openPaywall() { showPaywall = true }
}

/// The "Local Mode Only - Subscribe" banner pinned to the top of every Local
/// Mode screen. Tapping it opens the subscription paywall.
struct DemoModeBanner: View {
    @EnvironmentObject private var nav: DemoNavigation

    var body: some View {
        Button {
            nav.openPaywall()
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "lock.circle.fill")
                    .font(.subheadline)
                Text("Local Mode Only")
                    .fontWeight(.semibold)
                Text("-")
                    .foregroundStyle(AppTheme.textPrimary.opacity(0.7))
                Text("Subscribe")
                    .fontWeight(.bold)
                    .underline()
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
            }
            .foregroundStyle(AppTheme.textPrimary)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity)
            .background(AppTheme.warning.opacity(0.95))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Local Mode only. Tap to subscribe.")
        .accessibilityAddTraits(.isButton)
    }
}
