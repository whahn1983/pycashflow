import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var session: SessionManager
    @State private var settings: SettingsDTO?
    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let settings {
                    infoRow(label: "Signed in as", value: settings.user.email)
                    infoRow(label: "App Version", value: settings.app.version)
                    infoRow(label: "AI Configured", value: settings.ai.configured ? "Yes" : "No")
                }

                infoRow(label: "Mode", value: session.appMode.label)
                infoRow(label: "API", value: session.currentBaseURL.absoluteString)

                if let billing = session.billingStatus {
                    infoRow(
                        label: "Subscription",
                        value: "\(billing.subscription_status ?? "inactive") via \(billing.subscription_source ?? "none")"
                    )
                    if let expiry = billing.subscription_expiry {
                        infoRow(label: "Subscription expiry", value: expiry)
                    }
                }

                VStack(spacing: 8) {
                    Text("Change Password").foregroundStyle(AppTheme.textPrimary)
                    SecureField("Current password", text: $currentPassword).fieldStyle()
                    SecureField("New password", text: $newPassword).fieldStyle()
                    Button("Update Password") { Task { await changePassword() } }
                        .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()

                if let moreSettingsURL {
                    Link("More Settings", destination: moreSettingsURL)
                        .buttonStyle(PrimaryButtonStyle())
                }

                Button("Refresh Subscription Status") { Task { await session.refreshSubscriptionState(forceProfileRefresh: true) } }
                    .buttonStyle(PrimaryButtonStyle())

                Button("Switch to Self-Hosted Mode") {
                    session.switchMode(.selfHosted)
                }
                .buttonStyle(PrimaryButtonStyle())

                Button("Logout", role: .destructive) { Task { await logout() } }
                    .buttonStyle(PrimaryButtonStyle())

                if let errorText {
                    Text(errorText)
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .task { await load() }
        .refreshable { await load() }
        .appBackground()
        .navigationTitle("Settings")
    }

    private var moreSettingsURL: URL? {
        guard var components = URLComponents(url: session.currentBaseURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.path = "/settings"
        components.query = nil
        components.fragment = nil
        return components.url
    }

    private func infoRow(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(AppTheme.textMuted)
            Text(value)
                .foregroundStyle(AppTheme.textPrimary)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .cardRow()
    }

    private func load() async {
        guard let token = session.token else { return }
        do {
            let settingsResponse: APIEnvelope<SettingsDTO> = try await APIClient.shared.request(
                "settings",
                token: token,
                as: APIEnvelope<SettingsDTO>.self
            )
            settings = settingsResponse.data
        } catch {
            errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load settings"
        }
    }

    private func changePassword() async {
        guard let token = session.token else { return }
        do {
            struct Payload: Encodable { let current_password: String; let new_password: String }
            let _: APIEnvelope<[String: String]> = try await APIClient.shared.request(
                "auth/password",
                method: "PUT",
                token: token,
                body: Payload(current_password: currentPassword, new_password: newPassword),
                as: APIEnvelope<[String: String]>.self
            )
            currentPassword = ""
            newPassword = ""
            session.clear()
        } catch {
            errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to change password"
        }
    }

    private func logout() async {
        guard let token = session.token else {
            session.clear()
            return
        }
        _ = try? await APIClient.shared.request("auth/logout", method: "POST", token: token, as: APIEnvelope<[String: String]>.self)
        session.clear()
    }
}
