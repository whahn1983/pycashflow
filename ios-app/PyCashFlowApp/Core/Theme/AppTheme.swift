import SwiftUI

/// Shared visual style aligned to the web app's `improved.css` palette.
enum AppTheme {
    // Web parity colors from CSS variables in app/static/css/improved.css.
    static let secondaryDark = Color(red: 15/255, green: 23/255, blue: 42/255)   // #0f172a
    static let primaryDark = Color(red: 30/255, green: 41/255, blue: 59/255)      // #1e293b
    static let surface = Color(red: 51/255, green: 65/255, blue: 85/255)          // #334155
    static let surfaceLight = Color(red: 71/255, green: 85/255, blue: 105/255)    // #475569

    static let accent = Color(red: 59/255, green: 130/255, blue: 246/255)         // #3b82f6
    static let accentHover = Color(red: 37/255, green: 99/255, blue: 235/255)     // #2563eb

    static let success = Color(red: 16/255, green: 185/255, blue: 129/255)        // #10b981
    static let danger = Color(red: 239/255, green: 68/255, blue: 68/255)          // #ef4444

    static let textPrimary = Color(red: 241/255, green: 245/255, blue: 249/255)   // #f1f5f9
    static let textSecondary = Color(red: 203/255, green: 213/255, blue: 225/255) // #cbd5e1
    static let textMuted = Color(red: 148/255, green: 163/255, blue: 184/255)     // #94a3b8

    static let border = Color(red: 71/255, green: 85/255, blue: 105/255)          // #475569

    static let pageGradient = LinearGradient(
        colors: [secondaryDark, primaryDark],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
}

struct AppBackground: ViewModifier {
    func body(content: Content) -> some View {
        ZStack {
            AppTheme.pageGradient
                .ignoresSafeArea()
            content
        }
        .tint(AppTheme.accent)
    }
}

struct SurfaceCard: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(16)
            .background(AppTheme.surface.opacity(0.9), in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(AppTheme.border.opacity(0.9), lineWidth: 1)
            )
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .fontWeight(.semibold)
            .foregroundStyle(AppTheme.textPrimary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(configuration.isPressed ? AppTheme.accentHover : AppTheme.accent)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .opacity(configuration.isPressed ? 0.95 : 1)
    }
}

extension View {
    func appBackground() -> some View { modifier(AppBackground()) }
    func surfaceCard() -> some View { modifier(SurfaceCard()) }
}
