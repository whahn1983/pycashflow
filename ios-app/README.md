# PyCashFlow iOS App

SwiftUI client for PyCashFlow backed by `/api/v1` endpoints.

## Architecture
- `Core/Networking`: `APIClient`, endpoint construction, envelope decoding.
- `Core/Auth`: session/token state, app mode (Cloud vs Self-Hosted), Local Mode flag, and secure token persistence.
- `Core/Billing`: StoreKit purchase + restore integration and backend billing API adapters.
- `Core/Models`: DTOs aligned to backend response shapes.
- `Core/Demo`: standalone **Local Mode** — on-device storage and a pure-Swift
  reimplementation of the backend cash-flow projection (no network). See
  [Local Mode](#local-mode-offline).
- `Features/*`: screen-level view models and views (including `Features/Demo`,
  the Local Mode screens).

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

3. **Local Mode** (offline)
   - Fully standalone: no backend, no account, no network.
   - See [Local Mode](#local-mode-offline) below.

There is **no global app paywall** on launch. Subscription prompts appear in hosted-cloud activation and restore contexts only.

## Local Mode (offline)

Local Mode lets someone use the app with no backend at all. It is entered from
the **Enter Local Mode** button on the login screen and is remembered across
launches (persisted via `SessionManager.isDemoMode`); it takes precedence over
the login/authenticated flow in `RootView`.

What works in Local Mode:

- **Dashboard**, **Balance** (manual add/edit), **Schedules**, **Scenarios**,
  and **Holds/Skips** — all backed by on-device data only.
- The cash-flow **projection, running-balance chart, 90-day minimum, upcoming
  transactions, and cash-risk score** are computed entirely on-device.

What is intentionally absent (all require a backend):

- No AI Insights, no Plaid, no automatic balance refresh.
- No sync of any kind — balance, schedules, scenarios, holds/skips, and
  projections are stored only on this device and never leave the app.

Behavior and UI:

- A persistent **"Local Mode Only - Subscribe"** banner sits at the top of every
  screen; tapping it opens the subscription paywall.
- **Settings** in Local Mode shows only a *Local Mode* card with **Subscribe**
  (opens the paywall), **Switch to Self-Hosted Mode**, and **Logout** (which
  exits Local Mode back to the login screen). Local data is left on-device, so
  re-entering Local Mode restores it.

Implementation notes:

- `Core/Demo/DemoStore` owns all Local Mode data, persisting it to
  `UserDefaults` (`DEMO_STATE_V1`) with the same validation rules as the API.
- `Core/Demo/DemoProjectionEngine` re-implements the backend projection
  (`app/cashflow.py`: `calc_schedule` → `calc_transactions` →
  `calculate_cash_risk_score`) in pure Swift, including the fast-forward,
  month-end day restoration, and business-day weekend rolls. `Core/Demo/DemoDate`
  does pure-integer Gregorian date math so results are independent of
  `Foundation.Calendar`/timezone behavior.
- The engine was verified field-for-field against the real backend; ground-truth
  vectors are embedded in `pycashflowTests/DemoProjectionTests`.

> Note: Local Mode types keep the `Demo`-prefixed identifiers used during
> development (`DemoStore`, `DemoProjectionEngine`, `isDemoMode`, …); only the
> user-facing copy says "Local Mode".

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

- `API_BASE_URL` => `https://app.pycashflow.com/api/v1`
- `SELF_HOSTED_API_BASE_URL` => `http://127.0.0.1:5000/api/v1`
- `APP_STORE_PRODUCT_IDS` => `com.h3consultingpartners.pycashflow.cloud.monthly,com.h3consultingpartners.pycashflow.cloud.annual`

`APP_STORE_PRODUCT_IDS` is a comma-separated list. Both the monthly and annual
auto-renewing subscriptions unlock the same PyCashFlow Cloud access; the paywall
lists every configured product, orders them cheapest-first, and flags the plan
with the lowest per-month price as the best value. Add or remove product IDs
here to change which plans appear — no other code changes are required.

`APIClient` normalizes base URLs so host-only values automatically use `/api/v1`.
For security, remote self-hosted servers must use HTTPS. Plain HTTP is only
allowed for localhost development endpoints.

## Licensing

The iOS app in this directory is **not** licensed under the repository root GNU GPLv3 license.

- iOS app license: see [`LICENSE`](LICENSE) in this directory.
- App Store distributions are additionally licensed under Apple's Standard EULA:
  https://www.apple.com/legal/internet-services/itunes/dev/stdeula/

Backend/server components remain licensed under GNU GPLv3 per the root [`../LICENSE`](../LICENSE) file.
