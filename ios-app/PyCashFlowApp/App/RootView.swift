import SwiftUI

struct RootView: View {
    @EnvironmentObject var session: SessionManager

    var body: some View {
        NavigationStack {
            if session.isAuthenticated {
                DashboardView()
            } else {
                LoginView()
            }
        }
        .preferredColorScheme(.dark)
    }
}
