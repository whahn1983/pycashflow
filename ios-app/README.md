# PyCashFlow iOS App

SwiftUI client for PyCashFlow backed by `/api/v1` endpoints.

## Architecture
- `Core/Networking`: `APIClient`, endpoint construction, envelope decoding.
- `Core/Auth`: session/token state, secure token persistence, and launch-time access enforcement.
- `Core/Billing`: StoreKit purchase + restore integration and backend billing API adapters.
- `Core/Models`: DTOs aligned to backend response shapes.
- `Features/*`: screen-level view models and views.

## Payments & Subscription Enforcement (App Store only)

The iOS app supports **Apple App Store** purchase flow only. Stripe is intentionally not implemented on iOS.

### Launch/session flow
1. App restores bearer token from Keychain.
2. `SessionManager.bootstrap()` refreshes `/auth/me` and `/billing/status`.
3. Backend billing status decides UI access:
   - active/effective active => app content unlocked
   - expired/inactive => paywall screen

### Purchase flow
1. `SubscriptionPaywallView` loads StoreKit products from `APP_STORE_PRODUCT_IDS`.
2. User taps Subscribe.
3. StoreKit purchase completes and returns verified transaction.
4. App sends receipt + signed transaction metadata to `POST /api/v1/billing/verify-appstore`.
5. App refreshes `GET /api/v1/billing/status` and unlocks only if backend confirms active.

### Restore flow
1. User taps Restore Purchases.
2. App runs `AppStore.sync()` and reads current entitlements.
3. App submits latest verified entitlement to `POST /api/v1/billing/verify-appstore`.
4. App refreshes backend billing status and updates lock/unlock UI.

### Authority model
- Backend is source of truth for activation.
- Guests follow backend effective account status (owner-based access).
- Global-admin bypass is backend-driven and respected by client state.

## Runtime configuration
Set these values via Info.plist (or environment for debug tooling):

- `API_BASE_URL` => e.g. `https://api.example.com/api/v1`
- `APP_STORE_PRODUCT_IDS` => comma-separated product IDs, e.g. `com.pycashflow.premium.monthly`

`APIClient` will not default to localhost.
