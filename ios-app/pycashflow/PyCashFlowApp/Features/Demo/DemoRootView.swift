import SwiftUI

enum DemoSection: Hashable {
    case dashboard, balance, schedules, scenarios, holds, settings
}

/// Root scaffold for standalone Local Mode: a tab layout mirroring the real app
/// (minus AI Insights, which requires a backend), with the persistent
/// "Local Mode Only - Subscribe" banner pinned above every tab and the
/// subscription paywall reachable from the banner or Settings.
struct DemoRootView: View {
    @EnvironmentObject private var session: SessionManager
    @EnvironmentObject private var subscriptionManager: StoreKitSubscriptionManager
    @StateObject private var store = DemoStore()
    @StateObject private var nav = DemoNavigation()
    @State private var selected: DemoSection = .dashboard

    var body: some View {
        NavigationStack {
            TabView(selection: $selected) {
                DemoDashboardView()
                    .tabItem { Label("Dashboard", systemImage: "house") }
                    .tag(DemoSection.dashboard)

                DemoBalanceView()
                    .tabItem { Label("Balance", systemImage: "dollarsign.circle") }
                    .tag(DemoSection.balance)

                DemoSchedulesView()
                    .tabItem { Label("Schedules", systemImage: "calendar") }
                    .tag(DemoSection.schedules)

                DemoScenariosView()
                    .tabItem { Label("Scenarios", systemImage: "slider.horizontal.3") }
                    .tag(DemoSection.scenarios)

                DemoHoldsView()
                    .tabItem { Label("Holds", systemImage: "pause.circle") }
                    .tag(DemoSection.holds)

                DemoSettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
                    .tag(DemoSection.settings)
            }
        }
        .environmentObject(store)
        .environmentObject(nav)
        .preferredColorScheme(.dark)
        .sheet(isPresented: $nav.showPaywall) {
            // Open the 2-step paywall: collect the Cloud email first, then hand
            // off to SubscriptionPaywallView (matching the login trial flow),
            // rather than dropping the user straight onto the subscribe screen.
            NavigationStack {
                CloudActivationEmailView()
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("Done") { nav.showPaywall = false }
                        }
                    }
            }
            .environmentObject(session)
            .environmentObject(subscriptionManager)
            .preferredColorScheme(.dark)
        }
    }
}
