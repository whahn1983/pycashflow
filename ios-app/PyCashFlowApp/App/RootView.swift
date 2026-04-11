import SwiftUI

struct RootView: View {
    @EnvironmentObject var session: SessionManager

    var body: some View {
        NavigationStack {
            if !session.isAuthenticated {
                LoginView()
            } else {
                switch session.accessState {
                case .unknown, .checking:
                    ProgressView("Checking account status...")
                        .foregroundStyle(AppTheme.textPrimary)
                case .allowed:
                    DashboardView()
                case .blocked(let message):
                    if session.appMode == .cloud {
                        SubscriptionPaywallView(message: message)
                    } else {
                        DashboardView()
                    }
                }
            }
        }
        .task {
            await session.bootstrap()
        }
        .preferredColorScheme(.dark)
    }
}
