import SwiftUI

struct RootView: View {
    @EnvironmentObject var session: SessionManager
    @State private var selectedSection: AppSection = .dashboard

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
                        selectedView
                    case .blocked:
                        if session.appMode == .cloud {
                            SubscriptionPaywallView()
                        } else {
                            selectedView
                        }
                    }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if shouldShowBottomBar {
                        if session.user?.is_guest == true {
                            GuestSettingsButton()
                        } else {
                            FloatingNavBar(items: navItems, selectedSection: $selectedSection)
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
    var shouldShowBottomBar: Bool {
        switch session.accessState {
        case .allowed:
            return true
        case .blocked:
            return session.appMode != .cloud
        case .unknown, .checking:
            return false
        }
    }

    var navItems: [FloatingNavItem] {
        [
            FloatingNavItem(title: "Balance", systemImage: "dollarsign.circle", section: .balance),
            FloatingNavItem(title: "Schedules", systemImage: "calendar", section: .schedules),
            FloatingNavItem(title: "Scenarios", systemImage: "slider.horizontal.3", section: .scenarios),
            FloatingNavItem(title: "Holds", systemImage: "pause.circle", section: .holds),
            FloatingNavItem(title: "AI Insights", systemImage: "sparkles", section: .aiInsights),
            FloatingNavItem(title: "Settings", systemImage: "gearshape", section: .settings)
        ]
    }

    @ViewBuilder
    var selectedView: some View {
        switch selectedSection {
        case .dashboard:
            DashboardView()
        case .balance:
            BalanceView()
        case .schedules:
            SchedulesView()
        case .scenarios:
            ScenariosView()
        case .holds:
            HoldsView()
        case .aiInsights:
            AIInsightsView()
        case .settings:
            SettingsView()
        }
    }
}

enum AppSection {
    case dashboard
    case balance
    case schedules
    case scenarios
    case holds
    case aiInsights
    case settings
}
