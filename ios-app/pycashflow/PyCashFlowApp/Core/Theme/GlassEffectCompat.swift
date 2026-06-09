import SwiftUI

extension View {
    /// Applies the iOS 26 Liquid Glass material when it is available and
    /// falls back to a translucent material on iOS 17–25, where
    /// `glassEffect(_:in:)` does not exist.
    ///
    /// On iOS 26 and newer this is intentionally identical to calling
    /// `.glassEffect(.regular.interactive()...)` directly, so the existing
    /// Liquid Glass appearance and themes are unchanged. Older releases get a
    /// `.ultraThinMaterial` fill with a subtle hairline border so the floating
    /// navigation chrome stays legible without the unavailable API.
    @ViewBuilder
    func glassEffectCompat<S: InsettableShape>(
        in shape: S,
        tint: Color? = nil
    ) -> some View {
        if #available(iOS 26.0, *) {
            glassEffectModern(in: shape, tint: tint)
        } else {
            background(shape.fill(.ultraThinMaterial))
                .overlay(
                    shape.strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                )
        }
    }

    /// iOS 26+ Liquid Glass path, kept in its own availability-gated helper so
    /// the `Glass` type is only referenced where it actually exists.
    @available(iOS 26.0, *)
    @ViewBuilder
    private func glassEffectModern<S: Shape>(in shape: S, tint: Color?) -> some View {
        if let tint {
            glassEffect(.regular.interactive().tint(tint), in: shape)
        } else {
            glassEffect(.regular.interactive(), in: shape)
        }
    }
}
