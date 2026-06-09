import SwiftUI

/// Lightweight email collector shown before the StoreKit paywall. It captures
/// only the address the customer wants to use for PyCashFlow Cloud, then hands
/// it off to `SubscriptionPaywallView` so the subscribe/restore flow is
/// pre-filled without asking for any other registration details.
struct CloudActivationEmailView: View {
    @State private var email = ""
    @FocusState private var emailFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Create your Cloud account")
                        .font(.title2.bold())
                        .foregroundStyle(AppTheme.textPrimary)
                    Text("Enter the email you want to use for PyCashFlow Cloud.")
                        .foregroundStyle(AppTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(alignment: .leading, spacing: 12) {
                    TextField("Email", text: $email)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.emailAddress)
                        .submitLabel(.continue)
                        .focused($emailFocused)
                        .onSubmit { emailFocused = false }
                        .fieldStyle()

                    Text("We’ll send your setup link here after Apple confirms your subscription.")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textMuted)
                        .fixedSize(horizontal: false, vertical: true)

                    NavigationLink {
                        SubscriptionPaywallView(prefilledEmail: trimmedEmail, showsEmailField: false)
                    } label: {
                        Text("Continue")
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!isValidEmail)
                    .simultaneousGesture(TapGesture().onEnded { dismissKeyboard() })
                }
                .surfaceCard()
            }
            .padding(20)
        }
        .appBackground()
        .navigationTitle("Cloud Account")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.immediately)
    }

    private var trimmedEmail: String {
        email.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Non-empty and shaped like an address (`local@domain.tld`). Kept
    /// deliberately permissive — final ownership is confirmed via the setup
    /// link emailed after Apple verifies the subscription.
    private var isValidEmail: Bool {
        let value = trimmedEmail
        guard !value.isEmpty else { return false }
        let pattern = "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"
        return value.range(of: pattern, options: .regularExpression) != nil
    }
}
