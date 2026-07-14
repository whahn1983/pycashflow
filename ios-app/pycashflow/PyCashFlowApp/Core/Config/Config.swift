import Foundation

enum AppConfig {
    static let apiBaseURL = "https://app.pycashflow.com/api/v1"
    static let selfHostedAPIBaseURL = "http://127.0.0.1:5000/api/v1"
    /// Comma-separated App Store product identifiers offered on the paywall.
    /// The monthly and annual auto-renewing subscriptions unlock the same
    /// PyCashFlow Cloud access; the annual plan is the lower-cost cadence.
    static let appStoreProductIDs = "com.h3consultingpartners.pycashflow.cloud.monthly,com.h3consultingpartners.pycashflow.cloud.annual"
}
