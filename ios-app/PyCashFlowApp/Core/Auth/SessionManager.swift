import Foundation
import Security

@MainActor
final class SessionManager: ObservableObject {
    enum AppMode: String, CaseIterable, Identifiable {
        case cloud
        case selfHosted

        var id: String { rawValue }
        var label: String {
            switch self {
            case .cloud: return "PyCashFlow Cloud"
            case .selfHosted: return "Self-Hosted"
            }
        }
    }

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
    @Published var appMode: AppMode = Self.loadMode()
    @Published var selfHostedBaseURLText: String = Self.loadSelfHostedURL().absoluteString

    var isAuthenticated: Bool { token != nil }
    var currentBaseURL: URL { APIClient.shared.baseURL }

    init() {
        applyBaseURLForMode()
    }

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

    func switchMode(_ newMode: AppMode) {
        guard newMode != appMode else { return }
        appMode = newMode
        UserDefaults.standard.set(newMode.rawValue, forKey: Self.modeKey)
        applyBaseURLForMode()
        clear()
    }

    @discardableResult
    func updateSelfHostedBaseURL(_ value: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = URL(string: trimmed), parsed.scheme != nil, parsed.host != nil else {
            return false
        }
        selfHostedBaseURLText = parsed.absoluteString
        UserDefaults.standard.set(parsed.absoluteString, forKey: Self.selfHostedURLKey)
        if appMode == .selfHosted {
            APIClient.shared.baseURL = parsed
        }
        return true
    }

    private func applyBaseURLForMode() {
        switch appMode {
        case .cloud:
            APIClient.shared.baseURL = AppEnvironment.cloudAPIBaseURL
        case .selfHosted:
            APIClient.shared.baseURL = Self.loadSelfHostedURL()
        }
    }

    private static let modeKey = "APP_MODE"
    private static let selfHostedURLKey = "SELF_HOSTED_API_BASE_URL"

    private static func loadMode() -> AppMode {
        let raw = UserDefaults.standard.string(forKey: modeKey)
        return AppMode(rawValue: raw ?? "") ?? .cloud
    }

    private static func loadSelfHostedURL() -> URL {
        if let raw = UserDefaults.standard.string(forKey: selfHostedURLKey),
           let url = URL(string: raw),
           url.scheme != nil,
           url.host != nil {
            return url
        }
        return AppEnvironment.defaultSelfHostedAPIBaseURL
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
