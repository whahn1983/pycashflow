import Foundation

final class APIClient {
    static let shared = APIClient()
    var baseURL = URL(string: "http://localhost:5000/api/v1")!

    func request<T: Decodable>(_ path: String, method: String = "GET", token: String? = nil, body: Data? = nil, as: T.Type) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }

        let (data, response) = try await URLSession.shared.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 500
        let decoder = JSONDecoder()
        if (200..<300).contains(code) {
            return try decoder.decode(T.self, from: data)
        }
        throw try decoder.decode(APIErrorEnvelope.self, from: data)
    }
}
