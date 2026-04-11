import Foundation
import Security

@MainActor
final class SessionManager: ObservableObject {
    enum AccessState: Equatable {
        case unknown
        case checking
        case allowed
        case blocked(message: String)
    }

    @Published var token: String? = TokenKeychainStore.readTokenMigratingLegacy()
    @Published var user: UserDTO?
    @Published var billingStatus: BillingStatusDTO?
    @Published var accessState: AccessState = .unknown

    var isAuthenticated: Bool { token != nil }

    func bootstrap() async {
        guard token != nil else {
            accessState = .unknown
            return
        }
        await refreshSubscriptionState(forceProfileRefresh: true)
    }

    func setSession(token: String, user: UserDTO) {
        self.token = token
        self.user = user
        if TokenKeychainStore.saveToken(token) {
            UserDefaults.standard.removeObject(forKey: "api_token")
        } else {
            UserDefaults.standard.set(token, forKey: "api_token")
        }
    }

    func establishSession(token: String, user: UserDTO) async {
        setSession(token: token, user: user)
        await refreshSubscriptionState(forceProfileRefresh: true)
    }

    func refreshSubscriptionState(forceProfileRefresh: Bool = false) async {
        guard let token else {
            accessState = .unknown
            return
        }

        accessState = .checking

        do {
            if forceProfileRefresh || user == nil {
                let me: APIEnvelope<UserDTO> = try await APIClient.shared.request(
                    "auth/me",
                    token: token,
                    as: APIEnvelope<UserDTO>.self
                )
                user = me.data
            }

            let status = try await BillingAPI.fetchBillingStatus(token: token)
            billingStatus = status
            accessState = status.effectiveAccessAllowed
                ? .allowed
                : .blocked(message: status.accessMessage)
        } catch let apiError as APIErrorEnvelope {
            if apiError.status == 401 {
                clear()
                accessState = .unknown
                return
            }
            accessState = .blocked(message: apiError.error)
        } catch {
            accessState = .blocked(message: "Unable to refresh account status. Please try again.")
        }
    }

    func clear() {
        token = nil
        user = nil
        billingStatus = nil
        accessState = .unknown
        TokenKeychainStore.deleteToken()
        UserDefaults.standard.removeObject(forKey: "api_token")
    }
}

private enum TokenKeychainStore {
    private static let service = "PyCashFlow"
    private static let account = "api_token"

    static func saveToken(_ token: String) -> Bool {
        guard let data = token.data(using: .utf8) else { return false }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data
        ]
        let addStatus = SecItemAdd(query as CFDictionary, nil)
        if addStatus == errSecSuccess {
            return true
        }

        guard addStatus == errSecDuplicateItem else {
            return false
        }

        let matchQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        let attributesToUpdate: [String: Any] = [
            kSecValueData as String: data
        ]
        let updateStatus = SecItemUpdate(
            matchQuery as CFDictionary,
            attributesToUpdate as CFDictionary
        )
        return updateStatus == errSecSuccess
    }

    static func readTokenMigratingLegacy() -> String? {
        if let token = readToken() {
            return token
        }

        let defaults = UserDefaults.standard
        guard let legacyToken = defaults.string(forKey: account), !legacyToken.isEmpty else {
            return nil
        }

        if saveToken(legacyToken) {
            defaults.removeObject(forKey: account)
        }
        return legacyToken
    }

    private static func readToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess,
              let data = item as? Data,
              let token = String(data: data, encoding: .utf8) else {
            return nil
        }
        return token
    }

    static func deleteToken() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
