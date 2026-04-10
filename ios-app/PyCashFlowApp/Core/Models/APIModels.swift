import Foundation

struct APIEnvelope<T: Decodable>: Decodable { let data: T }
struct APIListEnvelope<T: Decodable>: Decodable { let data: [T]; let meta: Meta? }
struct Meta: Decodable { let total: Int?; let limit: Int?; let offset: Int? }

struct APIErrorEnvelope: Decodable, Error {
    let error: String
    let code: String
    let status: Int
    let fields: [String: String]?
}

struct UserDTO: Decodable {
    let id: Int
    let email: String
    let name: String
    let is_admin: Bool
    let is_guest: Bool
}

struct LoginResponseDTO: Decodable {
    let token: String?
    let twofa_required: Bool?
    let challenge: String?
    let user: UserDTO
}
