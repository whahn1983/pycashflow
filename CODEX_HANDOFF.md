# PyCashFlow — Codex Handoff

> Snapshot of what exists as of commit `08e6c32` (2026-04-09).
> Intended for the next coding agent or human developer picking up this repo.

---

## 1. What Was Implemented

### API v1 Foundation (commits #131–#137)

A REST API layer was added on top of the existing Flask server-rendered app.
The API lives under `/api/v1/` as a separate Flask Blueprint with CSRF
exemption and Bearer-token authentication.

**Auth endpoints (3):**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/auth/login` | Email + password → Bearer token |
| POST | `/api/v1/auth/logout` | Revoke current Bearer token |
| GET | `/api/v1/auth/me` | Current user profile |

**Read-only data endpoints (6):**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/dashboard` | Balance, risk score, upcoming transactions, min balance |
| GET | `/api/v1/schedules` | List recurring scheduled transactions |
| GET | `/api/v1/projections` | Running-balance time series (schedule + scenario) |
| GET | `/api/v1/scenarios` | List what-if scenario items |
| GET | `/api/v1/holds` | List held (paused) schedule items |
| GET | `/api/v1/skips` | List skipped transaction instances |

**Supporting infrastructure:**

- `UserToken` model — SHA-256 hashed tokens, 30-day TTL
- `app/api/auth_utils.py` — token lifecycle, dual-mode auth (Bearer + session fallback)
- `app/api/serializers.py` — ORM → JSON with decimal-string amounts, ISO 8601 dates
- `app/api/errors.py` — standardized error envelope (`error`, `code`, `status`, `fields`)
- `app/api/responses.py` — `api_ok`, `api_list`, `api_created`, `api_no_content`
- Alembic migration for `user_tokens` table
- Credential-validation oracle fix (constant-time checks, 2FA blocks token issuance)

**Documentation added:**

- `API_CONVENTIONS.md` — response shapes, serialization rules, pagination spec
- `AUTH_API.md` — token lifecycle, client behavior guide
- `SAMPLE_PAYLOADS.md` — curl examples for all endpoints
- `API_GAP_REPORT.md` — architecture analysis and phased implementation plan

---

## 2. What Remains Incomplete

### Write endpoints (none exist)

The API is entirely read-only. An iOS app cannot yet:

- Create, update, or delete a schedule
- Create, update, or delete a scenario
- Add or remove holds or skips
- Update the current balance
- Manage user settings or password

### Pagination

`api_list()` accepts `limit`/`offset` parameters but no data endpoint actually
reads or applies `?limit=` or `?offset=` query parameters from the request.
All list endpoints return every record. This is documented as "coming later"
in `API_CONVENTIONS.md` but not implemented.

### 2FA via API

Users with TOTP enabled are **blocked from API login** (returns 401). There is
no `POST /api/v1/auth/login/2fa` endpoint. This means any user who enables 2FA
loses mobile API access entirely.

### Token refresh

There is no token refresh endpoint. When a token expires after 30 days the
client must re-authenticate with email + password. There is no way to extend a
token's lifetime.

### Passkey auth via API

Passkey (WebAuthn) authentication is only available through the server-rendered
web routes. No API equivalent exists.

### Balance history

Only the latest balance is exposed (via `/dashboard`). There is no endpoint to
list historical balances or create a new balance entry.

### AI Insights

The AI insights engine (`ai_insights.py`) is not exposed through the API.
Mobile clients cannot trigger insight generation or read cached insights.

### Email ingestion config

No API for reading or updating IMAP email configuration.

---

## 3. Known API Inconsistencies

1. **`meta` shape varies.** List endpoints include `meta.total` but never
   `meta.limit` or `meta.offset` because pagination is not wired up. The
   `API_CONVENTIONS.md` says `meta` should include all three when paginated.

2. **`/dashboard` returns `risk` as a raw dict** from `calculate_cash_risk_score()`.
   The risk dict keys (`score`, `status`, `color`, `runway_days`,
   `lowest_balance`, etc.) are not formally serialized through a dedicated
   serializer — they pass through as-is from the engine, including Python
   floats rather than decimal strings.

3. **`upcoming_transactions` in `/dashboard`** uses `_amount()` and `_date()`
   for serialization but does not go through a named serializer function. The
   shape differs from `/schedules` (no `id`, `frequency`, or `start_date`).

4. **Guest user auth inconsistency.** The API `@api_login_required` decorator
   accepts guest users and `_effective_user_id()` maps them to their owner's
   data. But there is no way for a guest to obtain a Bearer token if the
   account owner has configured the guest — guests authenticate with their own
   email/password, which works correctly, but no test covers the guest-login →
   owner-data flow end-to-end via Bearer token.

5. **`/projections` returns `[]` vs `null`.** If `run` is empty,
   `_series(run) or []` returns `[]`. If `run_scenario` is `None`,
   `_series(run_scenario)` returns `None`. This is intentional but
   underdocumented — clients must handle both shapes.

6. **Appendix in `API_CONVENTIONS.md` is stale.** It only lists the 3 auth
   endpoints; the 6 data endpoints added in #136 were not appended.

---

## 4. Auth Model Summary

### Three tiers of access

| Role | `admin` | `is_global_admin` | `account_owner_id` | Capabilities |
|------|---------|-------------------|---------------------|-------------|
| Global Admin | true | true | null | User approval, system settings |
| Account Owner | true | false | null | Full cash-flow CRUD, guest management |
| Guest | false | false | owner's ID | Read-only, sees owner's data |

### Authentication methods

| Method | Web app | API v1 | Notes |
|--------|---------|--------|-------|
| Email + password | Yes | Yes | Scrypt hashing |
| TOTP 2FA | Yes | **Blocked** | Returns 401 — no API 2FA flow |
| Passkeys (WebAuthn) | Yes | **No** | Web-only routes |
| Bearer token | N/A | Yes | 256-bit, SHA-256 hashed at rest, 30-day TTL |
| Session cookie | Yes | Fallback | Accepted for read ops from same-origin JS |

### Security measures

- Constant-time password comparison (prevents timing oracle)
- Dummy hash checked when user not found (prevents user enumeration)
- Rate limiting: 10/min on login endpoints
- Fernet encryption for stored secrets (email passwords, TOTP secrets, OpenAI keys)
- CSRF exempt on API blueprint; CSRF enforced on web routes
- Max request body: 2 MB

---

## 5. Test Status

**173 tests, all passing** (as of this snapshot).

| Test file | Count | Scope |
|-----------|-------|-------|
| `test_api_foundation.py` | ~35 | Token auth lifecycle, response/error shapes, serialization |
| `test_api_data.py` | ~50 | All 6 data endpoints, guest isolation |
| `test_routes.py` | ~45 | Web routes, form validation, authorization |
| `test_projection_engine.py` | ~50 | Business-day adjustments, frequency expansion, 90-day window |
| `test_scenarios.py` | ~20 | Scenario projections, baseline immutability |
| `test_cash_risk_score.py` | ~40 | Score banding, edge cases, cyclical income |
| `test_imports.py` | ~20 | CSV import validation |
| `test_passkey_auth.py` | ~3 | Passkey challenge/registration basics |

### Notable gaps in test coverage

- No tests for write operations via API (none exist yet)
- No tests for schedule/scenario update or delete via web routes
- No tests for hold/skip creation flow
- No tests for TOTP 2FA setup or verification
- No tests for email ingestion configuration
- No tests for AI settings or insight generation
- No concurrent / race-condition tests
- No tests for token expiry cleanup
- 38 SQLAlchemy `LegacyAPIWarning` deprecation warnings (`Query.get()` → `Session.get()`)

---

## 6. Biggest Risks Before iOS Development Begins

1. **No write endpoints.** The API cannot mutate any data. An iOS app that
   only displays information has limited value — users will still need the
   web app to manage schedules, balance, etc.

2. **2FA blocks API access entirely.** Security-conscious users who enable
   TOTP will be locked out of the mobile app. This needs a 2FA-aware login
   flow before launch.

3. **Dashboard side effect.** The web `GET /` route **deletes and recreates**
   the Balance row on every page load (lines 67–76 of `main.py`). The API
   `/dashboard` does NOT do this — so balance dates may diverge between web
   and API views. This is a latent data-consistency risk.

4. **Risk score dict is untyped.** The `calculate_cash_risk_score()` return
   dict is passed through raw. Any change to its keys or value types will
   silently break mobile clients.

5. **No input validation on future write endpoints.** The web routes validate
   via procedural Flask form handling (`main.py` lines 177–225). This logic
   is not reusable for JSON API inputs — it will need to be rebuilt or
   extracted.

6. **SQLAlchemy 2.0 deprecation.** 38 warnings about `Query.get()`. This
   will break on SQLAlchemy 2.x upgrade.

---

## 7. Recommended Next Tasks (Priority Order)

1. **Add CRUD endpoints for schedules** — POST/PUT/DELETE with JSON
   validation. This is the minimum for a useful mobile app.

2. **Add `POST /api/v1/balance`** — allow mobile clients to update the
   current balance.

3. **Implement 2FA-aware API login** — add `POST /api/v1/auth/login/2fa`
   so TOTP users can authenticate.

4. **Wire up pagination** — read `?limit=` and `?offset=` query params in
   list endpoints; pass them through to `api_list()`.

5. **Add CRUD endpoints for scenarios, holds, skips.**

6. **Extract validation logic** — pull form-validation rules from `main.py`
   into a shared module usable by both web and API routes.

7. **Add a risk-score serializer** — formalize the dict shape with decimal
   strings and document it in `API_CONVENTIONS.md`.

8. **Fix `Query.get()` deprecation** — migrate to `Session.get()` across
   the codebase.

9. **Add token refresh endpoint** — `POST /api/v1/auth/refresh` to extend
   token lifetime without re-entering credentials.

10. **Expose AI insights via API** — `GET /api/v1/insights` and
    `POST /api/v1/insights/refresh`.
