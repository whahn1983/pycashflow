import SwiftUI

struct LoginView: View {
    @EnvironmentObject var session: SessionManager
    @State private var email = ""
    @State private var password = ""
    @State private var challenge: String?
    @State private var twoFACode = ""
    @State private var errorText: String?
    @State private var isLoading = false

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("PyCashFlow")
                        .font(.largeTitle.bold())
                        .foregroundStyle(AppTheme.textPrimary)
                    Text(challenge == nil ? "Sign in to continue" : "Enter your verification code")
                        .foregroundStyle(AppTheme.textSecondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(spacing: 12) {
                    if challenge == nil {
                        TextField("Email", text: $email)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)

                        SecureField("Password", text: $password)
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)
                    } else {
                        TextField("6-digit code or backup code", text: $twoFACode)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)
                    }

                    if let errorText {
                        Text(errorText)
                            .foregroundStyle(AppTheme.danger)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button(challenge == nil ? "Login" : "Verify 2FA") {
                        Task { await submit() }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(isLoading)
                }
                .surfaceCard()
            }
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Login")
    }

    private func submit() async {
        await MainActor.run { isLoading = true; errorText = nil }
        if challenge == nil {
            await login()
        } else {
            await completeTwoFA()
        }
        await MainActor.run { isLoading = false }
    }

    private func login() async {
        do {
            struct Payload: Encodable { let email: String; let password: String }
            let response: APIEnvelope<LoginResponseDTO> = try await APIClient.shared.request(
                "auth/login",
                method: "POST",
                body: Payload(email: email, password: password),
                as: APIEnvelope<LoginResponseDTO>.self
            )

            if response.data.twofa_required == true {
                await MainActor.run { challenge = response.data.challenge }
                return
            }
            guard let token = response.data.token else {
                await MainActor.run { errorText = "Login token missing" }
                return
            }
            await MainActor.run { session.setSession(token: token, user: response.data.user) }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "Login failed" }
        }
    }

    private func completeTwoFA() async {
        guard let challenge else { return }
        do {
            struct Payload: Encodable { let challenge: String; let code: String }
            let response: APIEnvelope<LoginResponseDTO> = try await APIClient.shared.request(
                "auth/login/2fa",
                method: "POST",
                body: Payload(challenge: challenge, code: twoFACode),
                as: APIEnvelope<LoginResponseDTO>.self
            )
            guard let token = response.data.token else {
                await MainActor.run { errorText = "2FA login token missing" }
                return
            }
            await MainActor.run { session.setSession(token: token, user: response.data.user) }
        } catch {
            await MainActor.run { errorText = (error as? APIErrorEnvelope)?.error ?? "2FA failed" }
        }
    }
}
