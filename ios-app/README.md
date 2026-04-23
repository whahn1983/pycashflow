# PyCashFlow iOS App

SwiftUI client for PyCashFlow backed by `/api/v1` endpoints.

## Architecture
- `Core/Networking`: `APIClient`, endpoint construction, envelope decoding.
- `Core/Auth`: session/token state, app mode (Cloud vs Self-Hosted), and secure token persistence.
- `Core/Billing`: StoreKit purchase + restore integration and backend billing API adapters.
- `Core/Models`: DTOs aligned to backend response shapes.
- `Features/*`: screen-level view models and views.

## Product Model

The iOS app is free to download and use. It supports two modes:

1. **PyCashFlow Cloud mode**
   - Uses the managed hosted backend URL.
   - App Store subscriptions are used only to create/activate/restore hosted cloud access.
   - Backend `/billing/status` remains the source of truth for hosted account activation.

2. **Self-Hosted mode**
   - User configures a custom API base URL (for example, their own server).
   - No App Store subscription is required by the app.
   - Server-side access rules are determined by the connected backend configuration.

There is **no global app paywall** on launch. Subscription prompts appear in hosted-cloud activation and restore contexts only.

## Payments & Subscription Scope (Cloud only)

The iOS app supports **Apple App Store** purchase flow only. Stripe is intentionally not implemented on iOS.

### Hosted cloud purchase/restore flow
1. `SubscriptionPaywallView` loads StoreKit products from `APP_STORE_PRODUCT_IDS`.
2. User subscribes or restores.
3. App sends receipt + signed transaction metadata to `POST /api/v1/billing/verify-appstore`.
4. If authenticated, app refreshes `GET /api/v1/billing/status`.

### Authority model
- Backend is source of truth for activation.
- Guests follow backend effective account status (owner-based access).
- Global-admin bypass is backend-driven and respected by client state.
- App Store status is not treated as a universal entitlement for all app usage.

## Runtime configuration
These values are hardcoded in `PyCashFlowApp/Core/Config/Config.swift`:

- `API_BASE_URL` => `https://cloud.pycashflow.com/api/v1`
- `SELF_HOSTED_API_BASE_URL` => `https://localhost:5000`
- `APP_STORE_PRODUCT_IDS` => empty string for now

`APIClient` normalizes base URLs so host-only values automatically use `/api/v1`.
