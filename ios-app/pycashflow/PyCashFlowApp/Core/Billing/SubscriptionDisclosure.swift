import Foundation

enum SubscriptionDisclosure {
    static let title = "PyCashFlow Cloud Monthly"
    static let price = "$9.99/month"
    static let durationAndType = "Billed monthly. Auto-renewing subscription."
    static let renewalNotice = "Payment will be charged to your Apple ID. " +
        "Subscription automatically renews unless canceled at least 24 hours " +
        "before the end of the current billing period. You can manage or " +
        "cancel your subscription in Apple ID settings."

    static let termsTitle = "Terms of Use"
    static let privacyTitle = "Privacy Policy"
    static let termsURL = URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!
    static let privacyURL = URL(string: "https://www.pycashflow.com/privacy")!
}
