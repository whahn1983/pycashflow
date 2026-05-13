import SwiftUI
import AuthenticationServices

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
    @State private var isPasskeyLoading = false
    @State private var showPasswordLoginFields = false
    @State private var showPasskeyEmailField = false
    @State private var inAppBrowserURL: URL?
    @FocusState private var focusedField: Field?

    private static let forgotPasswordURL = URL(string: "https://cash.hahn3.com/forgot-password")!

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

                HStack(spacing: 4) {
                    Text("Logging in on:")
                        .foregroundStyle(AppTheme.textSecondary)
                    Picker("App Mode", selection: Binding(
                        get: { session.appMode },
                        set: { newValue in
                            guard newValue != session.appMode else { return }
                            dismissKeyboard()
                            focusedField = nil
                            session.switchMode(newValue)
                            authErrorText = nil
                            selfHostedErrorText = nil
                        }
                    )) {
                        ForEach(SessionManager.AppMode.allCases) { mode in
                            Text(mode.label).tag(mode)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(minWidth: 190, alignment: .leading)
                    .tint(AppTheme.accent)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(spacing: 12) {
                    if challenge == nil && showPasswordLoginFields {
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
                            .onSubmit { submitFromKeyboard() }
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)

                        Button("Forgot password?") {
                            inAppBrowserURL = Self.forgotPasswordURL
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(AppTheme.accent)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else if challenge != nil {
                        TextField("6-digit code or backup code", text: $twoFACode)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .submitLabel(.go)
                            .focused($focusedField, equals: .twoFACode)
                            .onSubmit { submitFromKeyboard() }
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
                        submitFromKeyboard()
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(isLoading || isPasskeyLoading)

                    if challenge == nil && showPasskeyEmailField && !showPasswordLoginFields {
                        TextField("Email", text: $email)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .submitLabel(.go)
                            .focused($focusedField, equals: .email)
                            .onSubmit { startPasskeyLogin() }
                            .padding(12)
                            .background(AppTheme.surfaceLight.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                            .foregroundStyle(AppTheme.textPrimary)
                    }

                    if challenge == nil {
                        Button {
                            if !showPasskeyEmailField {
                                showPasskeyEmailField = true
                                showPasswordLoginFields = false
                                focusedField = .email
                                return
                            }
                            startPasskeyLogin()
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "person.badge.key.fill")
                                Text(isPasskeyLoading ? "Signing in…" : "Sign in with Passkey")
                            }
                        }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(isLoading || isPasskeyLoading)
                    }
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
                        Text("Use HTTPS for remote servers. HTTP is allowed only for localhost/127.0.0.1 during local development.")
                            .font(.caption)
                            .foregroundStyle(AppTheme.textMuted)
                        Button("Save Server URL") {
                            dismissKeyboard()
                            focusedField = nil
                            if !session.updateSelfHostedBaseURL(selfHostedURL) {
                                selfHostedErrorText = "Enter a valid server URL. Use HTTPS for remote hosts; HTTP is only allowed for localhost."
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
                    NavigationLink("Sign up for PyCashFlow Cloud") {
                        SubscriptionPaywallView()
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }

            }
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Login")
        .navigationBarTitleDisplayMode(.inline)
        // Interactive dismissal installs a pan recognizer that competes with
        // the system home-indicator gesture while the keyboard is visible;
        // when the gesture gate times out iOS hands the swipe to SpringBoard,
        // which manifests as the app "dropping to the home screen" while the
        // user is typing. `.immediately` keeps scroll-to-dismiss UX without
        // the conflicting drag recognizer.
        .scrollDismissesKeyboard(.immediately)
        .inAppBrowser(url: $inAppBrowserURL)
        .onAppear {
            selfHostedURL = session.selfHostedBaseURLText
        }
    }

    /// Dismiss the keyboard up front, then launch the submit task on the
    /// next runloop tick so SwiftUI can finish applying the focus state
    /// mutation before `isLoading` triggers another view update. Doing both
    /// in the same tick is what triggers `UIKeyboardTaskQueue` timeouts.
    private func submitFromKeyboard() {
        dismissKeyboard()
        focusedField = nil
        guard !isLoading else { return }
        if challenge == nil && !showPasswordLoginFields {
            showPasswordLoginFields = true
            showPasskeyEmailField = false
            focusedField = .email
            return
        }
        Task { @MainActor in
            await Task.yield()
            guard !isLoading else { return }
            isLoading = true
            await submit()
        }
    }

    @MainActor
    private func submit() async {
        defer { isLoading = false }
        authErrorText = nil
        if challenge == nil {
            await login()
        } else {
            await completeTwoFA()
        }
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

    private func startPasskeyLogin() {
        dismissKeyboard()
        focusedField = nil
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedEmail.isEmpty else {
            authErrorText = "Please enter your email first, then select Sign in with Passkey."
            return
        }
        guard !isPasskeyLoading, !isLoading else { return }
        Task { @MainActor in
            isPasskeyLoading = true
            defer { isPasskeyLoading = false }
            authErrorText = nil
            await passkeyLogin(email: trimmedEmail)
        }
    }

    @MainActor
    private func passkeyLogin(email: String) async {
        let optionsResponse: PasskeyLoginOptionsDTO
        do {
            struct Payload: Encodable { let email: String }
            let envelope: APIEnvelope<PasskeyLoginOptionsDTO> = try await APIClient.shared.request(
                "auth/passkey/options",
                method: "POST",
                body: Payload(email: email),
                as: APIEnvelope<PasskeyLoginOptionsDTO>.self
            )
            optionsResponse = envelope.data
        } catch {
            authErrorText = (error as? APIErrorEnvelope)?.error ?? "Unable to start passkey sign-in"
            return
        }

        guard let challengeData = Base64URL.decode(optionsResponse.options.challenge) else {
            authErrorText = "Server returned an invalid passkey challenge"
            return
        }

        let rpId = optionsResponse.options.rpId ?? APIClient.shared.baseURL.host ?? ""
        guard !rpId.isEmpty else {
            authErrorText = "Passkey sign-in is not available for this server"
            return
        }
        if session.appMode == .cloud {
            let expectedCloudRPID = AppEnvironment.cloudAPIBaseURL.host?.lowercased() ?? ""
            if rpId.lowercased() != expectedCloudRPID {
                authErrorText = "Passkey sign-in is unavailable due to an unexpected cloud security domain."
                return
            }
        }

        let allowedCredentialIDs: [Data] = (optionsResponse.options.allowCredentials ?? [])
            .compactMap { Base64URL.decode($0.id) }

        let controller = PasskeyLoginController()
        let assertion: ASAuthorizationPlatformPublicKeyCredentialAssertion
        do {
            assertion = try await controller.performAssertion(
                relyingPartyIdentifier: rpId,
                challenge: challengeData,
                allowedCredentialIDs: allowedCredentialIDs
            )
        } catch PasskeyLoginError.cancelled {
            return
        } catch {
            authErrorText = (error as? LocalizedError)?.errorDescription ?? "Passkey sign-in failed"
            return
        }

        do {
            struct CredentialResponse: Encodable {
                let authenticatorData: String
                let clientDataJSON: String
                let signature: String
                let userHandle: String?
            }
            struct Credential: Encodable {
                let id: String
                let rawId: String
                let type: String
                let response: CredentialResponse
            }
            struct VerifyPayload: Encodable {
                let challenge_token: String
                let credential: Credential
            }

            let credentialID = Base64URL.encode(assertion.credentialID)
            let payload = VerifyPayload(
                challenge_token: optionsResponse.challenge_token,
                credential: Credential(
                    id: credentialID,
                    rawId: credentialID,
                    type: "public-key",
                    response: CredentialResponse(
                        authenticatorData: Base64URL.encode(assertion.rawAuthenticatorData),
                        clientDataJSON: Base64URL.encode(assertion.rawClientDataJSON),
                        signature: Base64URL.encode(assertion.signature),
                        userHandle: assertion.userID.map { Base64URL.encode($0) }
                    )
                )
            )

            let response: APIEnvelope<LoginResponseDTO> = try await APIClient.shared.request(
                "auth/passkey/verify",
                method: "POST",
                body: payload,
                as: APIEnvelope<LoginResponseDTO>.self
            )
            guard let token = response.data.token else {
                authErrorText = "Passkey sign-in token missing"
                return
            }
            await session.establishSession(token: token, user: response.data.user)
        } catch {
            authErrorText = (error as? APIErrorEnvelope)?.error ?? "Passkey sign-in failed"
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
