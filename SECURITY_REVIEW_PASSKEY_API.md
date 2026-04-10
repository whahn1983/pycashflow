# Security Review: Passkey + REST API

Date: 2026-04-10  
Scope: `app/auth.py`, `app/api/*`, supporting auth/session wiring.

## Executive summary

I reviewed the new passkey and REST API authentication/data flows for common authn/authz, CSRF, replay, and account-enumeration issues.

**Overall:** the implementation includes several good controls (hashed API tokens, challenge TTLs, RP/origin validation, user-verification-required passkeys), but there are some meaningful risks that should be addressed.

## Findings

### 1) Account enumeration in passkey login options (Medium)

**Where**
- `POST /passkey_login/options` returns a specific error when a user has no registered passkeys (or account is inactive/nonexistent).  
  (`"No passkeys are registered for this account."`)

**Why it matters**
- This leaks account state to unauthenticated callers and can be used for targeted phishing/password-spraying prep.

**Evidence**
- `app/auth.py` `passkey_login_options()` distinguishes on user/passkey existence and returns specific message.

**Recommendation**
- Return a single generic response for all non-success cases (e.g., `{"error": "Unable to start passkey login."}`) and keep details in server logs only.

---

### 2) 2FA API challenge appears replayable within TTL (Medium)

**Where**
- API login challenge is signed+timestamped, but not server-side one-time tracked.
- `_build_twofa_challenge()` includes a nonce, yet `_verify_twofa_challenge()` validates only signature+age and user id.

**Why it matters**
- If a challenge token is intercepted/leaked, it can be retried until expiry (5 minutes).
- This is mitigated by TOTP freshness and rate limiting, but still weaker than one-time semantics.

**Evidence**
- `app/api/routes/auth.py`: `_build_twofa_challenge()` embeds `nonce`; `_verify_twofa_challenge()` does not consume/check nonce state.

**Recommendation**
- Persist challenge IDs/nonces server-side and mark them consumed on first valid attempt.
- Optionally tie challenge to client metadata (e.g., UA hash) to reduce replay utility.

---

### 3) Password change does not revoke existing API tokens (High)

**Where**
- `PUT /api/v1/auth/password` updates password only.

**Why it matters**
- If bearer tokens are stolen, they remain valid after a password reset/change, allowing persistent account access until token expiry.

**Evidence**
- `app/api/routes/auth.py` `api_change_password()` commits new password but does not delete `UserToken` rows for that user.

**Recommendation**
- Revoke all active API tokens on password change (and ideally on 2FA/passkey disable/reset as well).

---

### 4) CSRF-exempt API + session-auth fallback increases blast radius (Medium)

**Where**
- API blueprint is CSRF-exempt globally.
- `@api_login_required` accepts Flask session cookie fallback in addition to bearer token.
- API includes many state-changing endpoints (`POST/PUT/DELETE`).

**Why it matters**
- Current cookie hardening (`SameSite=Lax`) reduces classic cross-site CSRF, but combining write-capable session auth with CSRF exemption is risky defense-in-depth-wise.
- Any regression in cookie policy, same-site gadget, or browser quirk increases exposure.

**Evidence**
- `app/__init__.py`: `csrf.exempt(api_blueprint)`.
- `app/api/auth_utils.py`: `api_login_required` accepts `current_user.is_authenticated` fallback.
- `app/api/routes/data.py` and `app/api/routes/auth.py`: write endpoints use `@api_login_required`.

**Recommendation**
- Restrict session fallback to read-only API endpoints, or
- require bearer tokens for mutating API routes, or
- re-enable CSRF protection for session-authenticated API writes.

## Positive controls observed

- Passwords and backup codes use `scrypt` hashing.
- API tokens are randomly generated and stored as SHA-256 hashes only.
- Passkey verification requires expected origin + RP ID + user verification.
- Passkey challenge TTL implemented for registration/login.
- Login endpoint includes dummy hash behavior to reduce timing-based username enumeration.
- Cookie flags are hardened (`HttpOnly`, `Secure` default, `SameSite=Lax`).

## Suggested remediation order

1. **High**: revoke all API tokens on password change.
2. **Medium**: remove passkey account-state enumeration response differences.
3. **Medium**: make API 2FA challenges one-time.
4. **Medium**: reduce/remove session-auth writes on CSRF-exempt API.
