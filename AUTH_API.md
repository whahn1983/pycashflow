# PyCashFlow Mobile API — Authentication Guide

## Auth Model

The API uses **Bearer token authentication**. Tokens are opaque, URL-safe strings (256-bit, generated with `secrets.token_urlsafe(32)`). Only the SHA-256 hash is stored server-side; the raw token is returned to the client exactly once at login.

### Why Bearer Tokens?

- **Stateless per-request** — no cookie jar needed on mobile.
- **Coexists with the web app** — session cookies continue to work for browser clients.
- **Simple** — no OAuth dance, no JWTs to decode/verify/refresh on the client.
- **Secure** — tokens are hashed at rest, so a database breach cannot be used to impersonate users.

## Token Lifecycle

| Event | Detail |
|-------|--------|
| **Creation** | `POST /api/v1/auth/login` with valid email + password. |
| **Expiry** | 30 days from creation. Expired tokens are silently rejected (401). |
| **Revocation** | `POST /api/v1/auth/logout` deletes the token server-side. |
| **Storage** | Only the SHA-256 hash is persisted in the `user_tokens` table. |

## Required Headers

All authenticated API requests must include:

```
Authorization: Bearer <token>
Content-Type: application/json    (for POST/PUT/PATCH requests)
```

No cookies, CSRF tokens, or API keys are required. The entire `/api/v1/` blueprint is CSRF-exempt.

## Login Flow

```
1. POST /api/v1/auth/login  { "email": "...", "password": "..." }
2. Receive 200  { "data": { "token": "<raw>", "user": { ... } } }
3. Store the token securely (iOS Keychain recommended).
4. Include  Authorization: Bearer <token>  on every subsequent request.
```

### Two-Factor Authentication (2FA)

Accounts with TOTP 2FA enabled **cannot** obtain API tokens via `/api/v1/auth/login`. The server returns 401 with the message `"Two-factor authentication is required for API login"`. This is a deliberate security constraint — 2FA users must authenticate through the browser flow until a dedicated 2FA API challenge endpoint is added in a future release.

### Inactive Accounts

Accounts that are not yet activated (`is_active = false`) are rejected with 401.

## Logout

```
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

The token is immediately and permanently revoked. The client should discard its stored copy.

## Session Fallback

For convenience, the API also accepts Flask-Login session cookies (set by the web app's `/login` route). This allows same-origin browser JavaScript to call API endpoints without obtaining a separate token. Session-based requests still benefit from the standard CSRF protection on the web blueprint; the API blueprint itself is CSRF-exempt.

## Expected Client Behavior (iOS / SwiftUI)

1. **Store tokens in the Keychain** — never in `UserDefaults` or plain files.
2. **Handle 401 globally** — when any request returns 401, prompt the user to re-authenticate.
3. **Token refresh** — there is no refresh-token mechanism. When a token expires (after 30 days), the user must log in again. Consider proactively re-authenticating a few days before expiry.
4. **Concurrent tokens** — the server allows multiple active tokens per user (e.g., iPhone + iPad). Each device should manage its own token independently.
5. **Logout on sign-out** — always call `POST /api/v1/auth/logout` before discarding the local token, so it is revoked server-side.

## Rate Limiting

- `POST /api/v1/auth/login` — 10 requests per minute per IP.
- All other endpoints — default Flask-Limiter settings (currently unlimited, but subject to change).

## Error Responses

All errors follow a consistent JSON shape:

```json
{
  "error": "Human-readable message",
  "code": "machine_readable_slug",
  "status": 401
}
```

| Status | Code | Meaning |
|--------|------|---------|
| 401 | `unauthorized` | Missing/invalid/expired token, bad credentials, inactive account |
| 403 | `forbidden` | Valid token but insufficient permissions |
| 404 | `not_found` | Endpoint or resource does not exist |
| 422 | `validation_error` | Request body failed validation (includes `fields` dict) |
| 500 | `internal_error` | Unexpected server error |
