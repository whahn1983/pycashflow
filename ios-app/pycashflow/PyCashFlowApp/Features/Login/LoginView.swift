import SwiftUI

struct LoginView: View {
    private enum Field: Hashable {
        case email
        case password
        case twoFACode
        case selfHostedURL
    }

    @EnvironmentObject var session: SessionManager
    @State private var email = ""
    @State private var password = ""
    @State private var challenge: String?
    @State private var twoFACode = ""
    @State private var selfHostedURL = ""
    @State private var authErrorText: String?
    @State private var selfHostedErrorText: String?
    @State private var isLoading = false
    @FocusState private var focusedField: Field?

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

                Picker("App Mode", selection: $session.appMode) {
                    ForEach(SessionManager.AppMode.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                .onChange(of: session.appMode) { _, newValue in
                    session.switchMode(newValue)
                    authErrorText = nil
                    selfHostedErrorText = nil
                }
                .surfaceCard()

                VStack(spacing: 12) {
                    if challenge == nil {
                        TextField("Email", text: $email)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .submitLabel(.next)
                            .focused($focusedField, equals: .email)
                            .onSubmit { focusedField = .password }
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)

                        SecureField("Password", text: $password)
                            .submitLabel(.go)
                            .focused($focusedField, equals: .password)
                            .onSubmit {
                                focusedField = nil
                                Task { await submit() }
                            }
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)
                    } else {
                        TextField("6-digit code or backup code", text: $twoFACode)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .submitLabel(.go)
                            .focused($focusedField, equals: .twoFACode)
                            .onSubmit {
                                focusedField = nil
                                Task { await submit() }
                            }
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)
                    }

                    if let authErrorText {
                        Text(authErrorText)
                            .foregroundStyle(AppTheme.danger)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button(challenge == nil ? "Login" : "Verify 2FA") {
                        focusedField = nil
                        Task { await submit() }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(isLoading)
                }
                .surfaceCard()

                if session.appMode == .selfHosted {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Self-Hosted API Base URL")
                            .foregroundStyle(AppTheme.textPrimary)
                        TextField("https://your-server.example.com/api/v1", text: $selfHostedURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .submitLabel(.done)
                            .focused($focusedField, equals: .selfHostedURL)
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)
                        Button("Save Server URL") {
                            if !session.updateSelfHostedBaseURL(selfHostedURL) {
                                selfHostedErrorText = "Please enter a valid URL, including /api/v1."
                            } else {
                                selfHostedErrorText = nil
                            }
                        }
                        .buttonStyle(PrimaryButtonStyle())

                        if let selfHostedErrorText {
                            Text(selfHostedErrorText)
                                .foregroundStyle(AppTheme.danger)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .surfaceCard()
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Using PyCashFlow Cloud hosted service.")
                            .foregroundStyle(AppTheme.textSecondary)
                        NavigationLink("Activate or Restore Cloud Subscription") {
                            SubscriptionPaywallView(message: "Use App Store subscription to activate or restore your hosted PyCashFlow Cloud account.")
                        }
                        .buttonStyle(PrimaryButtonStyle())
                    }
                    .surfaceCard()
                }

            }
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Login")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .onAppear {
            selfHostedURL = session.selfHostedBaseURLText
        }
    }

    private func submit() async {
        await MainActor.run {
            isLoading = true
            authErrorText = nil
        }
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
                await MainActor.run { authErrorText = "Login token missing" }
                return
            }
            await session.establishSession(token: token, user: response.data.user)
        } catch {
            await MainActor.run { authErrorText = (error as? APIErrorEnvelope)?.error ?? "Login failed" }
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
                await MainActor.run { authErrorText = "2FA login token missing" }
                return
            }
            await session.establishSession(token: token, user: response.data.user)
        } catch {
            await MainActor.run { authErrorText = (error as? APIErrorEnvelope)?.error ?? "2FA failed" }
        }
    }
}
