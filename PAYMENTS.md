# Payments & Subscription Architecture

## Overview

PyCashFlow supports three activation sources:

1. **Stripe subscriptions** (web checkout + webhook truth source)
2. **Apple App Store subscriptions** (server-side verification via App Store Server API JWT auth)
3. **Self-hosted/manual** activation when `PAYMENTS_ENABLED=false`

Subscription truth is normalized into a dedicated `subscription` table and
enforced centrally for both web and API auth paths.

## Subscription Table (Source of Truth)

- `user_id` (owner `user.id`, non-null)
- `source` (`apple | stripe | manual`)
- `environment` (`production | sandbox | null/manual`)
- `product_id` (provider product SKU/id)
- `original_transaction_id` (Apple lifecycle identity)
- `latest_transaction_id` (latest Apple transaction id)
- `external_subscription_id` (Stripe subscription id or provider id)
- `status` (`active | trial | grace_period | expired | canceled | inactive`)
- `expires_at`
- `raw_last_verified_at`
- `created_at`, `updated_at`

### Uniqueness and ownership constraints

- Apple ownership lock: unique (`source`, `environment`, `original_transaction_id`)
- Stripe uniqueness: unique (`source`, `external_subscription_id`)

This prevents one Apple original transaction lifecycle from activating more
than one account owner in the same environment.

## User Access Fields

- `is_account_owner`: explicit owner marker
- `owner_user_id`: owner link for guests (legacy `account_owner_id` is still respected)
- `is_global_admin`: bypasses payment checks and is always active

## Global Toggle

Set `PAYMENTS_ENABLED=true|false`.

- `true`: enforce owner subscription status/expiry for non-global-admin users.
- `false`: bypass subscription validation; rely only on `is_active` (manual/self-hosted mode).

Default behavior in this repository is `PAYMENTS_ENABLED=false`.

## Stripe Flow

### `POST /api/v1/billing/create-checkout-session`
- Requires bearer auth and account owner role.
- Returns a Stripe-style checkout session payload (`id`, `checkout_url`).

### `POST /api/v1/billing/webhook/stripe`
- Public endpoint; validates `Stripe-Signature` using `STRIPE_WEBHOOK_SECRET`.
- Trusted source of Stripe subscription state.
- Handles:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_failed`
- Auto-creates user by email when needed and sets owner + active subscription.
- For first-time paid users only, creates a one-time password setup token and
  sends an onboarding email. Existing users do not receive setup email.

## App Store Flow

### `POST /api/v1/billing/verify-appstore`
- Public endpoint for iOS receipt/transaction payload.
- Uses Apple App Store Server API (`/inApps/v1/subscriptions/{originalTransactionId}`)
  with ES256 JWT bearer auth generated from App Store Connect credentials.
- Supports `APPLE_ENVIRONMENT=production|sandbox|auto` (`auto` tries production then sandbox).
- Optionally validates `APPLE_BUNDLE_ID` against Apple-signed transaction payload.
- Applies subscription lifecycle transitions from Apple truth source:
  - Active statuses (`1`, `3`, `4`) => `status=active`, owner active
  - Non-active statuses => `status=expired`, owner inactive
- Uses `originalTransactionId` as the Apple lifecycle identity.
- Stores `transactionId` as `latest_transaction_id`.
- Ownership enforcement:
  - If no matching subscription exists, create one for the owner.
  - If the same owner re-verifies, update idempotently.
  - If another owner attempts same `originalTransactionId` + environment,
    verification is rejected and no activation occurs.
- Creates/updates account owner by email and writes provider state only to `subscription`.
- For first-time paid users only, creates a one-time password setup token and
  sends an onboarding email. Existing users do not receive setup email.
- Optional local/dev stub mode remains available with
  `APPSTORE_ALLOW_STUB_VERIFICATION=true` (returns `verification_status=verified_stub`).

## Paid User Onboarding Lifecycle

When a subscription event creates a brand-new user:

1. User is auto-created by normalized email and activated.
2. A cryptographically random one-time password setup token is generated.
3. Only the token hash is stored in `password_setup_tokens` (never plaintext).
4. Token has a short TTL (default 60 minutes), is tied to a user, and is
   invalid after first successful use.
5. Email contains a user-facing setup link using frontend origin:
   `{FRONTEND_BASE_URL}/auth/set-password/{token}`.
6. User completes setup via `POST /api/v1/auth/complete-password-setup` and
   then logs in normally with email/password.

If subscription events match an existing user email, subscription state is
updated silently and no password setup email is sent.

## FRONTEND_BASE_URL Usage

- `FRONTEND_BASE_URL` is used for all payment-onboarding links sent to users.
- The configured base URL is normalized by stripping trailing slashes before
  route concatenation.
- Password setup route is fixed and hardcoded as `/auth/set-password`.
- Backend/internal URLs are never used in user-facing setup email links.

## Guest Access Rules

Guest users inherit access from their owner (`owner_user_id` or legacy `account_owner_id`).
If owner subscription expires (and payments are enabled), guests are denied and marked inactive.

## Cancel / Expire / Resubscribe Behavior

- Same user + same Apple `originalTransactionId`: update existing row and
  reactivate when Apple status returns active.
- Same user + new Apple `originalTransactionId`: create a new row; older rows
  may remain expired/canceled for history.
- Same Apple lifecycle id + different user: rejected by ownership rule.
- Sandbox and production are treated separately by the `(source, environment, original_transaction_id)`
  unique constraint.

## Admin Behavior

Global admins always remain active and bypass subscription checks.

## Security Notes

- Client-provided payment status is never trusted for final access control.
- Stripe webhooks must pass signature verification.
- Subscription transitions are logged with user id, source, status changes, and expiry.


## App Store Server Credentials

Set these environment variables for real App Store verification:

- `APPLE_ISSUER_ID`
- `APPLE_KEY_ID`
- `APPLE_PRIVATE_KEY` **or** `APPLE_PRIVATE_KEY_PATH`
- `APPLE_ENVIRONMENT` (`production`, `sandbox`, or `auto`)
- `APPLE_BUNDLE_ID` (recommended for payload binding)

If credentials are missing and stub mode is disabled, verification requests are rejected.
