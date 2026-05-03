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
                        tabScaffold
                    case .blocked:
                        if session.appMode == .cloud {
                            SubscriptionPaywallView()
                        } else {
                            tabScaffold
                        }
                    }
                }
            }
        }
        .task {
            await session.bootstrap()
        }
        .onChange(of: session.isAuthenticated) { _, isAuthenticated in
            if isAuthenticated {
                selectedSection = .dashboard
            }
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

    @ViewBuilder
    var tabScaffold: some View {
        if shouldShowBottomBar {
            tabView
        } else {
            selectedView
        }
    }

    @ViewBuilder
    var tabView: some View {
        if session.user?.is_guest == true {
            TabView(selection: $selectedSection) {
                DashboardView()
                    .tabItem { Label("Dashboard", systemImage: "house") }
                    .tag(AppSection.dashboard)

                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
                    .tag(AppSection.settings)
            }
        } else {
            TabView(selection: $selectedSection) {
                DashboardView()
                    .tabItem { Label("Dashboard", systemImage: "house") }
                    .tag(AppSection.dashboard)

                BalanceView()
                    .tabItem { Label("Balance", systemImage: "dollarsign.circle") }
                    .tag(AppSection.balance)

                SchedulesView()
                    .tabItem { Label("Schedules", systemImage: "calendar") }
                    .tag(AppSection.schedules)

                ScenariosView()
                    .tabItem { Label("Scenarios", systemImage: "slider.horizontal.3") }
                    .tag(AppSection.scenarios)

                HoldsView()
                    .tabItem { Label("Holds", systemImage: "pause.circle") }
                    .tag(AppSection.holds)

                AIInsightsView()
                    .tabItem { Label("AI Insights", systemImage: "sparkles") }
                    .tag(AppSection.aiInsights)

                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
                    .tag(AppSection.settings)
            }
        }
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
