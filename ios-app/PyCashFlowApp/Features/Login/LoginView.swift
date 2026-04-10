import SwiftUI

struct LoginView: View {
    @EnvironmentObject var session: SessionManager
    @State private var email = ""
    @State private var password = ""
    @State private var errorText: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("PyCashFlow")
                        .font(.largeTitle.bold())
                        .foregroundStyle(AppTheme.textPrimary)
                    Text("Sign in to continue")
                        .foregroundStyle(AppTheme.textSecondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(spacing: 12) {
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

                    if let errorText {
                        Text(errorText)
                            .foregroundStyle(AppTheme.danger)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button("Login") {
                        Task { await login() }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }
                .surfaceCard()
            }
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Login")
        .toolbarBackground(AppTheme.secondaryDark, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }

    private func login() async {
        do {
            let payload = ["email": email, "password": password]
            let body = try JSONSerialization.data(withJSONObject: payload)
            let response: APIEnvelope<LoginResponseDTO> = try await APIClient.shared.request("auth/login", method: "POST", body: body, as: APIEnvelope<LoginResponseDTO>.self)
            guard let token = response.data.token else {
                errorText = "2FA is required."
                return
            }
            session.setSession(token: token, user: response.data.user)
        } catch {
            errorText = "Login failed"
        }
    }
}
