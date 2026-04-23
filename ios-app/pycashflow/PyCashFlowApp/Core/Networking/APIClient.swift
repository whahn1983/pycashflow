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
        normalizedAPIBaseURL(from: AppConfig.apiBaseURL)!
    }()

    static let defaultSelfHostedAPIBaseURL: URL = {
        normalizedAPIBaseURL(from: AppConfig.selfHostedAPIBaseURL)!
    }()

    static let appStoreProductIDs: [String] = {
        AppConfig.appStoreProductIDs
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
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
}
