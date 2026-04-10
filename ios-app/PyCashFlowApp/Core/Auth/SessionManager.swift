import Foundation

final class SessionManager: ObservableObject {
    @Published var token: String? = nil
    @Published var user: UserDTO? = nil

    var isAuthenticated: Bool { token != nil }

    func setSession(token: String, user: UserDTO) {
        self.token = token
        self.user = user
    }

    func clear() {
        token = nil
        user = nil
    }
}
