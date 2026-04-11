# Payments & Subscription Architecture

## Overview

PyCashFlow supports three activation sources:

1. **Stripe subscriptions** (web checkout + webhook truth source)
2. **Apple App Store subscriptions** (server-side verification endpoint; currently stubbed verifier)
3. **Self-hosted/manual** activation when `PAYMENTS_ENABLED=false`

All subscription state is stored on `User` and enforced centrally for both web and API auth paths.

## User Subscription Fields

- `subscription_status`: `active | inactive | trial | expired`
- `subscription_source`: `stripe | app_store | manual | none`
- `subscription_id`: provider subscription identifier
- `subscription_expiry`: UTC datetime for access expiry
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

## App Store Flow

### `POST /api/v1/billing/verify-appstore`
- Public endpoint for iOS receipt or transaction payload.
- Current implementation has **stub verification scaffold** (`verification_status=verified_stub`) for future Apple server verification integration.
- Extracts email + expiry, creates/updates account owner, marks source `app_store`, and activates account.

## Guest Access Rules

Guest users inherit access from their owner (`owner_user_id` or legacy `account_owner_id`).
If owner subscription expires (and payments are enabled), guests are denied and marked inactive.

## Admin Behavior

Global admins always remain active and bypass subscription checks.

## Security Notes

- Client-provided payment status is never trusted for final access control.
- Stripe webhooks must pass signature verification.
- Subscription transitions are logged with user id, source, status changes, and expiry.
