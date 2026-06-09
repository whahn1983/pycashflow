import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

@main
struct PyCashFlowApp: App {
    @StateObject private var session = SessionManager()
    @StateObject private var subscriptionManager = StoreKitSubscriptionManager()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        configureMoreMenuAppearance()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(subscriptionManager)
        }
        .onChange(of: scenePhase) { _, newPhase in
            guard newPhase == .active, session.isAuthenticated else { return }
            Task {
                await session.refreshSubscriptionState(forceProfileRefresh: false)
                await subscriptionManager.reprocessPendingTransactions()
            }
        }
    }

    private func configureMoreMenuAppearance() {
#if canImport(UIKit)
        guard
            let moreListController = NSClassFromString("UIMoreListController") as? UIAppearanceContainer.Type
        else {
            return
        }

        let moreListTableView = UITableView.appearance(whenContainedInInstancesOf: [moreListController])
        moreListTableView.backgroundColor = UIColor(AppTheme.primaryDark)

        let moreListCell = UITableViewCell.appearance(whenContainedInInstancesOf: [moreListController])
        moreListCell.backgroundColor = UIColor(AppTheme.primaryDark)
#endif
    }
}
