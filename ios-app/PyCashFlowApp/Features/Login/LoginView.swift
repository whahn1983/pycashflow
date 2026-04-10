import SwiftUI

struct LoginView: View {
    @EnvironmentObject var session: SessionManager
    @State private var email = ""
    @State private var password = ""
    @State private var errorText: String?

    var body: some View {
        Form {
            TextField("Email", text: $email)
                .textInputAutocapitalization(.never)
            SecureField("Password", text: $password)
            if let errorText { Text(errorText).foregroundStyle(.red) }
            Button("Login") {
                Task { await login() }
            }
        }
        .navigationTitle("Login")
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
