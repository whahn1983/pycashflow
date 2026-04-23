import XCTest
@testable import pycashflow

@MainActor
final class SessionManagerModeTests: XCTestCase {
    override func tearDown() {
        super.tearDown()
        UserDefaults.standard.removeObject(forKey: "APP_MODE")
        UserDefaults.standard.removeObject(forKey: "SELF_HOSTED_API_BASE_URL")
        UserDefaults.standard.removeObject(forKey: "api_token")
    }

    func testSwitchToSelfHostedUpdatesBaseURLAndClearsSession() async {
        let session = SessionManager()
        _ = session.updateSelfHostedBaseURL("https://self-hosted.example.com/api/v1")
        session.setSession(
            token: "token123",
            user: UserDTO(
                id: 1,
                email: "user@example.com",
                name: "User",
                is_admin: true,
                is_global_admin: false,
                twofa_enabled: false,
                is_guest: false,
                subscription_status: nil,
                subscription_source: nil,
                subscription_expiry: nil
            )
        )

        session.switchMode(.selfHosted)

        XCTAssertEqual(session.appMode, .selfHosted)
        XCTAssertEqual(session.currentBaseURL.absoluteString, "https://self-hosted.example.com/api/v1")
        XCTAssertFalse(session.isAuthenticated)
    }

    func testInvalidSelfHostedURLRejected() async {
        let session = SessionManager()
        let ok = session.updateSelfHostedBaseURL("not-a-url")
        XCTAssertFalse(ok)
    }
}
