import SwiftUI

struct RootView: View {
    @EnvironmentObject var session: SessionManager

    var body: some View {
        Group {
            if !session.isAuthenticated {
                NavigationStack {
                    LoginView()
                }
            } else {
                NavigationStack {
                    switch session.accessState {
                    case .unknown, .checking:
                        ProgressView("Checking account status...")
                            .foregroundStyle(AppTheme.textPrimary)
                    case .allowed:
                        DashboardView()
                    case .blocked:
                        if session.appMode == .cloud {
                            SubscriptionPaywallView()
                        } else {
                            DashboardView()
                        }
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
