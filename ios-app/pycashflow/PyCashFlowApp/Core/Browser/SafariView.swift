import SwiftUI
import SafariServices

/// Wraps `SFSafariViewController` so SwiftUI sheets can present links inside
/// the app instead of bouncing the user out to Safari.
struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let controller = SFSafariViewController(url: url)
        controller.preferredBarTintColor = UIColor(AppTheme.primaryDark)
        controller.preferredControlTintColor = UIColor(AppTheme.accent)
        controller.dismissButtonStyle = .done
        return controller
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}

extension View {
    /// Presents a `SafariView` sheet whenever the bound URL becomes non-nil.
    func inAppBrowser(url: Binding<URL?>) -> some View {
        sheet(isPresented: Binding(
            get: { url.wrappedValue != nil },
            set: { isPresented in
                if !isPresented { url.wrappedValue = nil }
            }
        )) {
            if let target = url.wrappedValue {
                SafariView(url: target)
                    .ignoresSafeArea()
            }
        }
    }
}
