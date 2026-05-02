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
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if session.accessState == .allowed || (session.accessState == .blocked && session.appMode != .cloud) {
                        if session.user?.is_guest == true {
                            GuestSettingsButton()
                        } else {
                            FloatingNavBar(items: navItems)
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


private extension RootView {
    var navItems: [FloatingNavItem] {
        [
            FloatingNavItem(title: "Dashboard", systemImage: "house") { DashboardView() },
            FloatingNavItem(title: "Balance", systemImage: "dollarsign.circle") { BalanceView() },
            FloatingNavItem(title: "Schedules", systemImage: "calendar") { SchedulesView() },
            FloatingNavItem(title: "Scenarios", systemImage: "slider.horizontal.3") { ScenariosView() },
            FloatingNavItem(title: "Holds", systemImage: "pause.circle") { HoldsView() },
            FloatingNavItem(title: "AI Insights", systemImage: "sparkles") { AIInsightsView() },
            FloatingNavItem(title: "Settings", systemImage: "gearshape") { SettingsView() }
        ]
    }
}
