import SwiftUI

struct DashboardView: View {
    var body: some View {
        List {
            NavigationLink("Accounts", destination: AccountsView())
            NavigationLink("Projections", destination: ProjectionsView())
            NavigationLink("Schedules", destination: SchedulesView())
            NavigationLink("Scenarios", destination: ScenariosView())
            NavigationLink("Settings", destination: SettingsView())
        }
        .navigationTitle("Dashboard")
    }
}
