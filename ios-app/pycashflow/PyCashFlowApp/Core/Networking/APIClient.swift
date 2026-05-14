import Foundation

final class APIClient {
    static let shared = APIClient()

    var baseURL: URL = AppEnvironment.cloudAPIBaseURL
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        config.timeoutIntervalForRequest = 240
        config.timeoutIntervalForResource = 240
        return URLSession(configuration: config)
    }()

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

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            let urlError = error as? URLError
            throw APIErrorEnvelope(
                error: urlError?.localizedDescription ?? "Network request failed: \(error.localizedDescription)",
                code: "network_error",
                status: 0,
                fields: nil
            )
        }

        let code = (response as? HTTPURLResponse)?.statusCode ?? 500
        let decoder = JSONDecoder()

        if (200..<300).contains(code) {
            if code == 204 {
                if T.self == EmptyResponse.self,
                   let empty = EmptyResponse() as? T {
                    return empty
                }
                throw APIErrorEnvelope(
                    error: "Unexpected empty response body",
                    code: "empty_response_body",
                    status: code,
                    fields: nil
                )
            }
            do {
                return try decoder.decode(T.self, from: data)
            } catch let decodingError as DecodingError {
                throw APIErrorEnvelope(
                    error: "Could not read server response: \(Self.describe(decodingError))",
                    code: "decoding_error",
                    status: code,
                    fields: nil
                )
            } catch {
                throw APIErrorEnvelope(
                    error: "Could not read server response: \(error.localizedDescription)",
                    code: "decoding_error",
                    status: code,
                    fields: nil
                )
            }
        }

        if let apiError = try? decoder.decode(APIErrorEnvelope.self, from: data) {
            throw apiError
        }

        let bodyPreview = String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .prefix(200)
        let suffix = (bodyPreview?.isEmpty == false) ? ": \(bodyPreview!)" : ""
        throw APIErrorEnvelope(
            error: "Request failed (HTTP \(code))\(suffix)",
            code: "request_failed",
            status: code,
            fields: nil
        )
    }

    private static func describe(_ error: DecodingError) -> String {
        switch error {
        case .typeMismatch(_, let ctx):
            return "type mismatch at \(Self.path(ctx.codingPath)) — \(ctx.debugDescription)"
        case .valueNotFound(_, let ctx):
            return "missing value at \(Self.path(ctx.codingPath)) — \(ctx.debugDescription)"
        case .keyNotFound(let key, let ctx):
            return "missing key '\(key.stringValue)' at \(Self.path(ctx.codingPath))"
        case .dataCorrupted(let ctx):
            return "corrupted data at \(Self.path(ctx.codingPath)) — \(ctx.debugDescription)"
        @unknown default:
            return "\(error)"
        }
    }

    private static func path(_ keys: [CodingKey]) -> String {
        let rendered = keys.map { $0.stringValue }.joined(separator: ".")
        return rendered.isEmpty ? "(root)" : rendered
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
        normalizedAPIBaseURL(from: AppConfig.apiBaseURL)
            ?? URL(string: "https://app.pycashflow.com/api/v1")!
    }()

    static let defaultSelfHostedAPIBaseURL: URL = {
        normalizedAPIBaseURL(from: AppConfig.selfHostedAPIBaseURL)
            ?? URL(string: "http://127.0.0.1:5000/api/v1")!
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

        var normalized = candidate
        if candidate.host?.lowercased() == "cloud.pycashflow.com",
           var components = URLComponents(url: candidate, resolvingAgainstBaseURL: false) {
            components.host = "app.pycashflow.com"
            if let migrated = components.url {
                normalized = migrated
            }
        }

        if normalized.path.isEmpty || normalized.path == "/" {
            return normalized.appending(path: "api/v1")
        }

        return normalized
    }
}
