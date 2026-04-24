import Foundation
import AuthenticationServices
import UIKit

enum PasskeyLoginError: LocalizedError {
    case unsupported
    case invalidServerChallenge
    case cancelled
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .unsupported:
            return "Passkeys require iOS 16 or later."
        case .invalidServerChallenge:
            return "Server returned an invalid passkey challenge."
        case .cancelled:
            return "Passkey sign-in was cancelled."
        case .failed(let message):
            return message
        }
    }
}

/// Drives a single passkey assertion flow.
///
/// Retains itself for the duration of the `ASAuthorizationController`
/// presentation so the delegate callbacks are guaranteed to fire. Must be
/// invoked from the main actor because it touches `UIWindow`.
@MainActor
final class PasskeyLoginController: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {

    private var continuation: CheckedContinuation<ASAuthorizationPlatformPublicKeyCredentialAssertion, Error>?
    private var retainSelf: PasskeyLoginController?

    /// Prompt the system passkey sheet and return the raw assertion.
    ///
    /// - Parameters:
    ///   - relyingPartyIdentifier: The WebAuthn RP ID (typically the API host,
    ///     e.g. `app.pycashflow.com`). Must match an associated domain.
    ///   - challenge: The server-issued challenge, decoded from base64url.
    ///   - allowedCredentialIDs: Optional list of credential IDs returned by
    ///     the server, decoded from base64url.
    func performAssertion(
        relyingPartyIdentifier: String,
        challenge: Data,
        allowedCredentialIDs: [Data]
    ) async throws -> ASAuthorizationPlatformPublicKeyCredentialAssertion {
        guard #available(iOS 16.0, *) else {
            throw PasskeyLoginError.unsupported
        }

        let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(
            relyingPartyIdentifier: relyingPartyIdentifier
        )
        let request = provider.createCredentialAssertionRequest(challenge: challenge)
        request.allowedCredentials = allowedCredentialIDs.map {
            ASAuthorizationPlatformPublicKeyCredentialDescriptor(credentialID: $0)
        }
        request.userVerificationPreference = .required

        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self

        return try await withCheckedThrowingContinuation { cont in
            self.continuation = cont
            self.retainSelf = self
            controller.performRequests()
        }
    }

    // MARK: - ASAuthorizationControllerDelegate

    nonisolated func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        Task { @MainActor in
            defer { self.retainSelf = nil }
            guard let cont = self.continuation else { return }
            self.continuation = nil

            if let assertion = authorization.credential as? ASAuthorizationPlatformPublicKeyCredentialAssertion {
                cont.resume(returning: assertion)
            } else {
                cont.resume(throwing: PasskeyLoginError.failed("Unexpected passkey response type."))
            }
        }
    }

    nonisolated func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        Task { @MainActor in
            defer { self.retainSelf = nil }
            guard let cont = self.continuation else { return }
            self.continuation = nil

            if let asError = error as? ASAuthorizationError {
                switch asError.code {
                case .canceled:
                    cont.resume(throwing: PasskeyLoginError.cancelled)
                    return
                default:
                    break
                }
            }
            cont.resume(throwing: PasskeyLoginError.failed(error.localizedDescription))
        }
    }

    // MARK: - ASAuthorizationControllerPresentationContextProviding

    nonisolated func presentationAnchor(
        for controller: ASAuthorizationController
    ) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            Self.presentationAnchor()
        }
    }

    private static func presentationAnchor() -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let windows = scenes.flatMap(\.windows)
        if let keyWindow = windows.first(where: \.isKeyWindow) {
            return keyWindow
        }
        if let anyWindow = windows.first {
            return anyWindow
        }
        if let scene = scenes.first {
            return UIWindow(windowScene: scene)
        }
        // No connected scenes (e.g. backgrounded or mid-lifecycle transition).
        // Return a detached window so ASAuthorizationController surfaces a
        // normal auth error instead of crashing the app.
        return ASPresentationAnchor()
    }
}

/// Base64URL helpers used when exchanging WebAuthn payloads with the server.
///
/// The WebAuthn spec (and this backend) uses base64url — unlike `Data`'s
/// built-in base64 encoding, it is URL-safe and has no padding.
enum Base64URL {
    static func encode(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    static func decode(_ string: String) -> Data? {
        var value = string
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        let remainder = value.count % 4
        if remainder > 0 {
            value.append(String(repeating: "=", count: 4 - remainder))
        }
        return Data(base64Encoded: value)
    }
}
