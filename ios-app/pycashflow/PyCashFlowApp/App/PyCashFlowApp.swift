import SwiftUI

@main
struct PyCashFlowApp: App {
    @StateObject private var session = SessionManager()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
        }
        .onChange(of: scenePhase) { _, newPhase in
            guard newPhase == .active, session.isAuthenticated else { return }
            Task {
                await session.refreshSubscriptionState(forceProfileRefresh: false)
            }
        }
    }
}
