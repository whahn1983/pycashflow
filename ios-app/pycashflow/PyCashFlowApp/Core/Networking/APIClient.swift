import Foundation

final class APIClient {
    static let shared = APIClient()

    var baseURL: URL = AppEnvironment.cloudAPIBaseURL

    func request<T: Decodable>(
        _ path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        token: String? = nil,
        body: Encodable? = nil,
        as: T.Type
    ) async throws -> T {
        let endpoint = baseURL.appendingPathComponent(path)
        var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false)
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        guard let requestURL = components?.url else {
            throw APIErrorEnvelope(
                error: "Invalid request URL",
                code: "invalid_request_url",
                status: 500,
                fields: nil
            )
        }

        var request = URLRequest(url: requestURL)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.httpBody = try JSONEncoder().encode(AnyEncodable(body))
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 500
        let decoder = JSONDecoder()

        if (200..<300).contains(code) {
            if code == 204 { return EmptyResponse() as! T }
            return try decoder.decode(T.self, from: data)
        }

        if let apiError = try? decoder.decode(APIErrorEnvelope.self, from: data) {
            throw apiError
        }
        throw APIErrorEnvelope(error: "Request failed", code: "request_failed", status: code, fields: nil)
    }
}

private struct AnyEncodable: Encodable {
    private let encodeFn: (Encoder) throws -> Void

    init(_ wrapped: Encodable) {
        encodeFn = wrapped.encode
    }

    func encode(to encoder: Encoder) throws {
        try encodeFn(encoder)
    }
}

enum AppEnvironment {
    static let cloudAPIBaseURL: URL = {
        let key = "API_BASE_URL"

        if let plistValue = Bundle.main.object(forInfoDictionaryKey: key) as? String,
           !plistValue.isEmpty,
           let url = normalizedAPIBaseURL(from: plistValue) {
            return url
        }

        if let envValue = ProcessInfo.processInfo.environment[key],
           !envValue.isEmpty,
           let url = normalizedAPIBaseURL(from: envValue) {
            return url
        }

        return normalizedAPIBaseURL(from: "https://app.pycashflow.com")!
    }()

    static let defaultSelfHostedAPIBaseURL: URL = {
        let key = "SELF_HOSTED_API_BASE_URL"

        if let plistValue = Bundle.main.object(forInfoDictionaryKey: key) as? String,
           let url = URL(string: plistValue),
           !plistValue.isEmpty {
            return url
        }

        if let defaultsValue = UserDefaults.standard.string(forKey: key),
           let url = URL(string: defaultsValue),
           !defaultsValue.isEmpty {
            return url
        }

        return URL(string: "http://localhost:5000/api/v1")!
    }()


    private static func normalizedAPIBaseURL(from rawValue: String) -> URL? {
        guard let candidate = URL(string: rawValue.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            return nil
        }

        if candidate.path.isEmpty || candidate.path == "/" {
            return candidate.appending(path: "api/v1")
        }

        return candidate
    }

    static let appStoreProductIDs: [String] = {
        let key = "APP_STORE_PRODUCT_IDS"

        if let plistValue = Bundle.main.object(forInfoDictionaryKey: key) as? String {
            let ids = plistValue
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            if !ids.isEmpty {
                return ids
            }
        }

        if let envValue = ProcessInfo.processInfo.environment[key] {
            let ids = envValue
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            if !ids.isEmpty {
                return ids
            }
        }

        return []
    }()
}
