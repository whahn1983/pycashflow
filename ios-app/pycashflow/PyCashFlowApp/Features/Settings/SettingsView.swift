import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var session: SessionManager
    @State private var settings: SettingsDTO?
    @State private var insights: InsightsDTO?
    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Settings")
                    .font(.title2.bold())
                    .foregroundStyle(AppTheme.textPrimary)

                if let settings {
                    Text("Signed in as: \(settings.user.email)").surfaceCard()
                    Text("App Version: \(settings.app.version)").surfaceCard()
                    Text("AI Configured: \(settings.ai.configured ? "Yes" : "No")").surfaceCard()
                }

                Text("Mode: \(session.appMode.label)").surfaceCard()
                Text("API: \(session.currentBaseURL.absoluteString)").surfaceCard()

                if let billing = session.billingStatus {
                    Text("Subscription: \(billing.subscription_status ?? "inactive") via \(billing.subscription_source ?? "none")")
                        .surfaceCard()
                    if let expiry = billing.subscription_expiry {
                        Text("Subscription expiry: \(expiry)").surfaceCard()
                    }
                }

                if let insights {
                    Text("Insights: \((insights.insights ?? []).joined(separator: "\n• "))")
                        .surfaceCard()
                }

                Button("Refresh AI Insights") { Task { await refreshInsights() } }
                    .buttonStyle(PrimaryButtonStyle())

                VStack(spacing: 8) {
                    Text("Change Password").foregroundStyle(AppTheme.textPrimary)
                    SecureField("Current password", text: $currentPassword).fieldStyle()
                    SecureField("New password", text: $newPassword).fieldStyle()
                    Button("Update Password") { Task { await changePassword() } }
                        .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()

                Button("Refresh Subscription Status") { Task { await session.refreshSubscriptionState(forceProfileRefresh: true) } }
                    .buttonStyle(PrimaryButtonStyle())

                Button("Switch to Self-Hosted Mode") {
                    session.switchMode(.selfHosted)
                }
                .buttonStyle(PrimaryButtonStyle())

                Button("Logout", role: .destructive) { Task { await logout() } }
                    .buttonStyle(PrimaryButtonStyle())

                if let errorText {
                    Text(errorText).foregroundStyle(AppTheme.danger)
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

    private func load() async {
        guard let token = session.token else { return }
        do {
            async let settingsCall: APIEnvelope<SettingsDTO> = APIClient.shared.request("settings", token: token, as: APIEnvelope<SettingsDTO>.self)
            async let insightsCall: APIEnvelope<InsightsDTO> = APIClient.shared.request("insights", token: token, as: APIEnvelope<InsightsDTO>.self)
            let (settingsRes, insightsRes) = try await (settingsCall, insightsCall)
            await MainActor.run {
                settings = settingsRes.data
                insights = insightsRes.data
            }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to load settings" }
        }
    }

    private func refreshInsights() async {
        guard let token = session.token else { return }
        do {
            let response: APIEnvelope<InsightsDTO> = try await APIClient.shared.request("insights/refresh", method: "POST", token: token, as: APIEnvelope<InsightsDTO>.self)
            await MainActor.run { insights = response.data }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to refresh insights" }
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
            await MainActor.run {
                currentPassword = ""
                newPassword = ""
                session.clear()
            }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Failed to change password" }
        }
    }

    private func logout() async {
        guard let token = session.token else {
            await MainActor.run { session.clear() }
            return
        }
        _ = try? await APIClient.shared.request("auth/logout", method: "POST", token: token, as: APIEnvelope<[String: String]>.self)
        await MainActor.run { session.clear() }
    }
}
