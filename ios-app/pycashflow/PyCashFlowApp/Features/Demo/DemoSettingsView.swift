import SwiftUI

struct DemoSettingsView: View {
    @EnvironmentObject private var session: SessionManager
    @EnvironmentObject private var nav: DemoNavigation

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Demo Mode")
                            .font(.headline)
                            .foregroundStyle(AppTheme.textPrimary)
                        Text("You're exploring PyCashFlow with sample data stored only on this device. Subscribe to unlock the full app with cloud sync, automatic balances, and AI insights.")
                            .font(.footnote)
                            .foregroundStyle(AppTheme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    Button("Subscribe") {
                        nav.openPaywall()
                    }
                    .buttonStyle(PrimaryButtonStyle())

                    Button("Switch to Self-Hosted Mode") {
                        session.switchMode(.selfHosted)
                        session.exitDemoMode()
                    }
                    .buttonStyle(PrimaryButtonStyle())

                    Button("Logout", role: .destructive) {
                        session.exitDemoMode()
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Settings")
    }
}
