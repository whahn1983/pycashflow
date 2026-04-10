import Foundation

final class SessionManager: ObservableObject {
    @Published var token: String? = UserDefaults.standard.string(forKey: "api_token")
    @Published var user: UserDTO?

    var isAuthenticated: Bool { token != nil }

    func setSession(token: String, user: UserDTO) {
        self.token = token
        self.user = user
        UserDefaults.standard.set(token, forKey: "api_token")
    }

    func clear() {
        token = nil
        user = nil
        UserDefaults.standard.removeObject(forKey: "api_token")
    }
}
