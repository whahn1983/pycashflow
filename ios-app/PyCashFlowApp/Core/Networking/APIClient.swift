import Foundation

final class APIClient {
    static let shared = APIClient()
    var baseURL = URL(string: "http://localhost:5000/api/v1")!

    func request<T: Decodable>(
        _ path: String,
        method: String = "GET",
        token: String? = nil,
        body: Encodable? = nil,
        as: T.Type
    ) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
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
