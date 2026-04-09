# PyCashFlow — Mobile API Gap Report

> Generated: 2026-04-09
> Branch: `claude/plan-mobile-apis-3uJfS`

---

## 1. Architecture Summary

PyCashFlow is a single-server Flask application backed by SQLite (optionally PostgreSQL). It renders all UI server-side via Jinja2 templates and uses HTML forms for all data mutations. There is no existing REST or JSON API layer.

**Stack:**
- Flask + Flask-Login (session auth) + Flask-WTF (CSRF)
- SQLAlchemy ORM + Flask-Migrate (Alembic)
- pandas + Plotly for projections and charting
- Fernet symmetric encryption for sensitive fields (email passwords, TOTP secrets, API keys)
- WebAuthn/passkeys (py_webauthn) for passwordless login
- OpenAI integration for AI cash-flow insights
- Flask-Limiter for rate limiting

**App layout:**
```
app/
  __init__.py        # create_app factory; extension init; session config; CSRF
  auth.py            # Blueprint: /login, /signup, /logout, /passkey_*, /2fa
  main.py            # Blueprint: all domain routes (dashboard, schedules, etc.)
  models.py          # SQLAlchemy models
  cashflow.py        # Core business logic (pandas-based projections)
  ai_insights.py     # OpenAI integration
  crypto_utils.py    # Fernet encrypt/decrypt helpers
  totp_utils.py      # TOTP/backup-code helpers
  files.py           # CSV import/export
  getemail.py        # IMAP email balance ingestion
```

**Auth model:**
- Flask-Login session cookies (SameSite=Lax, HttpOnly, Secure)
- Three user tiers: Global Admin → Account Owner → Guest
- Optional TOTP 2FA and WebAuthn passkeys

---

## 2. Core Domain Entities

```
User (1) ──── (N) Schedule       Recurring income/expense entries
     (1) ──── (N) Scenario       What-if schedule variants
     (1) ──── (N) Balance        Historical balance snapshots
     (1) ──── (N) Hold           Pause a recurring transaction
     (1) ──── (N) Skip           Skip one occurrence of a transaction
     (1) ──── (0..1) AISettings  OpenAI key + cached insights
     (1) ──── (0..1) Email       IMAP config for auto balance import
     (1) ──── (N) PasskeyCredential  WebAuthn credentials
User (owner, 1) ── (N) User (guest)   Shared-access guest accounts

Settings (global)              Signup on/off flag
GlobalEmailSettings (global)   SMTP for system notifications
```

### Key field notes

| Entity | Notable fields |
|--------|---------------|
| Schedule / Scenario | `name`, `amount`, `type` (Income/Expense), `frequency` (Monthly/Quarterly/Yearly/Weekly/BiWeekly/Onetime), `startdate`, `firstdate` |
| Balance | `amount`, `date` — point-in-time balance entry |
| Hold | Freezes a named schedule; no date range — permanent until deleted |
| Skip | One-time exclusion: `name` + `date` |
| AISettings | Encrypted API key, `model_version`, `last_insights` (cached JSON) |

### Business-logic layer (`cashflow.py`)

The pure computation lives here and is **already decoupled from HTTP**:

| Function | Input | Output |
|----------|-------|--------|
| `update_cash(balance, schedules, holds, skips, scenarios)` | ORM objects | `(trans_df, run_df, run_scenario_df)` DataFrames |
| `calc_schedule(...)` | same | `(total_df, total_scenario_df)` |
| `calc_transactions(balance, total_df)` | balance float + df | `(trans_df, run_df)` |
| `calculate_cash_risk_score(balance, run)` | balance + run df | score dict (0-100), status, runway_days |
| `plot_cash(run, run_scenario)` | DataFrames | `(minbalance, min_scenario, graphJSON)` |

These functions can be called from API endpoints without modification.

---

## 3. Existing Routes — Grouped

### 3a. Server-Rendered Only (HTML — not reusable as-is)

These routes are tightly coupled to Jinja2 templates and WTForms. Extracting them as APIs requires separating the form-handling logic from the HTTP response.

| Route | Method | Domain |
|-------|--------|--------|
| `GET /` | GET/POST | Dashboard (balance, chart, risk, AI) |
| `GET /schedule` | GET | List schedules |
| `GET/POST /create` | GET/POST | Create schedule |
| `GET/POST /update` | GET/POST | Update schedule |
| `GET /holds` | GET | List holds + skips |
| `GET /scenarios` | GET | List scenarios |
| `GET/POST /create_scenario` | GET/POST | Create scenario |
| `GET/POST /update_scenario` | GET/POST | Update scenario |
| `GET /transactions` | GET | Expanded transaction list |
| `GET/POST /balance` | GET/POST | Enter current balance |
| `GET/POST /email` | GET/POST | IMAP config |
| `GET /settings` | GET | User settings page |
| `GET/POST /changepw` | GET/POST | Change password / name / email |
| `GET/POST /setup_2fa` | GET/POST | 2FA setup |
| `GET /setup_2fa/backup_codes` | GET | Show backup codes |
| `GET/POST /signups` | GET/POST | Global admin: toggle signups |
| `GET /global_admin` | GET | Global admin panel |
| `GET/POST /global_email_settings` | GET/POST | SMTP config |
| `GET /manage_guests` | GET | Guest list |
| `GET /login` | GET/POST | Login form + processing |
| `GET /login/2fa` | GET/POST | 2FA verification |
| `GET /signup` | GET/POST | Signup form |
| `GET /passkey_login` | GET | Passkey login form |
| `GET /passkeys` | GET | Manage passkeys |

### 3b. Already Returning JSON (Partial API Surface)

These exist today and can be referenced/adapted:

| Route | Method | Returns |
|-------|--------|---------|
| `POST /ai_insights` | POST | JSON array of insight objects |
| `POST /passkey_login/options` | POST | WebAuthn challenge JSON |
| `POST /passkey_login/verify` | POST | JSON result + sets session |
| `POST /passkeys/register/options` | POST | WebAuthn registration JSON |
| `POST /passkeys/register/verify` | POST | JSON result |
| `GET /manifest.json` | GET | PWA manifest JSON |

### 3c. Best Candidates to Expose as JSON APIs (first priority)

These have clean, already-decoupled business logic in `cashflow.py` and represent the highest-value reads for a mobile app:

| Proposed API endpoint | Source of logic | Complexity |
|----------------------|----------------|------------|
| `GET /api/v1/dashboard` | `update_cash()` + risk score | Low |
| `GET /api/v1/schedules` | DB query | Low |
| `POST /api/v1/schedules` | existing create logic | Low |
| `PUT /api/v1/schedules/<id>` | existing update logic | Low |
| `DELETE /api/v1/schedules/<id>` | existing delete logic | Low |
| `GET /api/v1/projections` | `update_cash()` → JSON | Low |
| `GET /api/v1/risk-score` | `calculate_cash_risk_score()` | Low |
| `GET /api/v1/transactions` | `calc_transactions()` | Low |
| `GET /api/v1/balances/current` | latest Balance query | Low |
| `POST /api/v1/balances` | existing balance save logic | Low |
| `POST /api/v1/auth/login` | existing auth logic | Medium |
| `POST /api/v1/auth/logout` | session.clear() | Low |
| `GET /api/v1/scenarios` | DB query | Low |
| `POST /api/v1/scenarios` | existing create logic | Low |
| `PUT/DELETE /api/v1/scenarios/<id>` | existing logic | Low |
| `GET /api/v1/holds` | DB query | Low |
| `POST /api/v1/holds/<schedule_id>` | existing addhold logic | Low |
| `DELETE /api/v1/holds/<id>` | existing deletehold logic | Low |
| `GET /api/v1/skips` | DB query | Low |
| `POST /api/v1/skips` | existing addskip logic | Low |
| `DELETE /api/v1/skips/<id>` | existing deleteskip logic | Low |
| `GET/POST /api/v1/insights` | `ai_insights.py` | Low (already JSON) |

---

## 4. Biggest Blockers for a Native Mobile Frontend

### B1 — No stateless authentication
All auth is session-cookie based. Mobile apps cannot reliably maintain a Flask session across cold starts or background refreshes. A token-based scheme (JWT or opaque bearer tokens) is required. This is the **highest-impact blocker**.

### B2 — CSRF protection applied globally
`Flask-WTF` CSRF tokens are tied to the session and baked into HTML forms. Every POST from a mobile client would be rejected by default. The API blueprint must exempt CSRF and rely on token auth instead.

### B3 — All mutation endpoints return redirects
Every POST route calls `redirect(url_for(...))` or uses `flash()`. A mobile client needs `201 Created` / `200 OK` with JSON, not an HTML redirect response.

### B4 — Business logic returns pandas DataFrames
`cashflow.py` returns DataFrames and Plotly JSON blobs. These need thin serialization wrappers to emit plain JSON for mobile clients (the computation itself is already clean).

### B5 — No pagination or filtering
`/global_admin` hard-limits at 500 rows. No list endpoint accepts query parameters. A mobile app needs cursor-based or offset pagination.

### B6 — Plotly chart is server-generated JSON
The dashboard builds a Plotly `graphJSON` blob (can be several hundred KB). Mobile clients should receive the underlying numeric data and render their own charts. A separate `GET /api/v1/projections` returning time-series arrays handles this cleanly.

### B7 — Encrypted fields require server-side decryption
OpenAI keys, IMAP passwords, and TOTP secrets are Fernet-encrypted using `APP_SECRET`. This is fine — it stays on the server — but means the API can never expose these raw values and must provide proxy operations instead.

### B8 — Guest user model is incomplete
Guests can view the account owner's data through the web app via implicit scoping, but there is no explicit API-layer access-control policy. This needs to be defined before exposing multi-user APIs.

### B9 — No API versioning convention
There is no `/api/v1/` prefix. Adding one now avoids breaking the existing web app routes.

---

## 5. Recommended First API Endpoints — v1

These 12 endpoints cover the core mobile read/write loop with minimal risk and maximum reuse of existing logic. Implement in this order:

### Phase 1 — Auth (prerequisite for everything else)

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 1 | POST | `/api/v1/auth/login` | Email + password → bearer token |
| 2 | POST | `/api/v1/auth/logout` | Invalidate token |
| 3 | GET | `/api/v1/auth/me` | Current user profile |

**Note:** Use a simple opaque token stored in a `UserToken` table (or HMAC-signed tokens) — avoid a full OAuth server for v1. Flask-Login can coexist by accepting either the session cookie or a `Bearer` token.

### Phase 2 — Dashboard read (highest mobile value)

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 4 | GET | `/api/v1/dashboard` | Current balance, 90-day projection summary, risk score, recent transactions |

This single endpoint can power the entire iOS home screen by calling `update_cash()` and `calculate_cash_risk_score()` internally and serializing the results.

### Phase 3 — Core CRUD

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 5 | GET | `/api/v1/schedules` | List all schedules |
| 6 | POST | `/api/v1/schedules` | Create schedule |
| 7 | PUT | `/api/v1/schedules/<id>` | Update schedule |
| 8 | DELETE | `/api/v1/schedules/<id>` | Delete schedule |
| 9 | POST | `/api/v1/balances` | Record current balance |
| 10 | GET | `/api/v1/balances/current` | Latest balance entry |

### Phase 4 — Projections and insights

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 11 | GET | `/api/v1/projections` | 90-day time-series (date, balance, transactions) |
| 12 | POST | `/api/v1/insights` | Trigger AI insights (proxy to ai_insights.py) |

---

## 6. Proposed Implementation Sequence

The goal is to add APIs **without touching any existing route** so the web app keeps working throughout.

### Step 0 — Preparation (no behavior change)
- [ ] Create `app/api/__init__.py` — register a new `api` blueprint with `url_prefix="/api/v1"`
- [ ] Create `app/api/errors.py` — standardize JSON error responses (`{"error": "...", "code": 400}`)
- [ ] Create `app/api/auth_utils.py` — token extraction middleware (check `Authorization: Bearer <token>` header, fall back to Flask-Login session for backwards compatibility)
- [ ] Create `UserToken` model (`id`, `user_id`, `token_hash`, `created_at`, `expires_at`) and generate Alembic migration
- [ ] Exempt the `/api/v1/*` prefix from Flask-WTF CSRF in `create_app()`

### Step 1 — Auth endpoints
- [ ] `POST /api/v1/auth/login` — validate credentials, create token, return `{"token": "...", "user": {...}}`
- [ ] `POST /api/v1/auth/logout` — delete token record
- [ ] `GET /api/v1/auth/me` — return current user fields (id, name, email, is_admin, twofa_enabled)

### Step 2 — Dashboard endpoint
- [ ] `GET /api/v1/dashboard` — call existing `update_cash()` + `calculate_cash_risk_score()`, serialize DataFrames to JSON; return: `current_balance`, `risk_score`, `risk_status`, `runway_days`, `upcoming_transactions[]`, `projection_series[]`

### Step 3 — Schedule CRUD
- [ ] Extract schedule validation logic from `main.py` into `app/api/validators.py`
- [ ] Implement `GET /api/v1/schedules` — return JSON array
- [ ] Implement `POST /api/v1/schedules` — validate + create, return `201`
- [ ] Implement `PUT /api/v1/schedules/<id>` — validate + update, return `200`
- [ ] Implement `DELETE /api/v1/schedules/<id>` — delete, return `204`

### Step 4 — Balance endpoints
- [ ] `GET /api/v1/balances/current` — latest Balance row
- [ ] `POST /api/v1/balances` — record new balance

### Step 5 — Projections endpoint
- [ ] `GET /api/v1/projections` — return `{"dates": [...], "balances": [...], "transactions": [...]}` from `update_cash()` output; omit Plotly serialization

### Step 6 — Holds, Skips, Scenarios
- [ ] Mirror the pattern from Step 3 for each entity

### Step 7 — AI Insights
- [ ] `GET /api/v1/insights` — return cached insights from `AISettings.last_insights`
- [ ] `POST /api/v1/insights/refresh` — call `fetch_insights()`, update cache, return new insights

### Step 8 — Hardening
- [ ] Add rate limiting to all `/api/v1/` routes (Flask-Limiter already present)
- [ ] Add pagination (`?limit=50&offset=0`) to all list endpoints
- [ ] Write integration tests for each endpoint
- [ ] Document endpoints (inline docstrings or OpenAPI via Flask-RESTX)

---

## 7. Risks, Assumptions, and Unknowns

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Token auth coexisting with session auth breaks existing tests | Medium | Use `@api_login_required` decorator that checks both; don't touch `@login_required` |
| pandas DataFrames are slow to serialize for every API call | Medium | Cache `update_cash()` result in Redis/memory per user with short TTL (30s) |
| CSRF exemption on `/api/v1/*` creates CSRF gap if web app ever calls those URLs | Low | Ensure web app never uses the API URLs; keep using Flask-WTF on all existing routes |
| OpenAI API latency (2–10s) makes `/api/v1/insights/refresh` slow for mobile | Medium | Make insights async; return cached `last_insights` immediately and refresh in background |
| SQLite concurrency under concurrent API + web requests | Medium | Migrate to PostgreSQL for production; SQLite WAL mode is acceptable for single-user |
| Token storage on iOS (Keychain) — token must have a reasonable expiry | Low | Set token TTL (e.g., 30 days); implement refresh tokens if needed later |
| Guest user scoping: guests can see owner data in web app but rules aren't codified | High | Define explicit guest permissions before implementing multi-user API access |

### Assumptions

- The iOS app will use HTTPS exclusively (token security depends on this)
- v1 does not need WebAuthn/passkey support on mobile (standard email+password login sufficient for v1)
- 2FA will be supported as a second step after `/api/v1/auth/login` returns `{"requires_2fa": true}` in a future iteration
- The mobile app will cache the dashboard response and use optimistic UI updates
- No new Python dependencies are needed for v1 (Flask's built-in `jsonify` + existing libraries are sufficient)

### Unknowns

- Whether the iOS app will use a dedicated API key or user-level tokens (user-level tokens assumed for v1)
- Whether scenarios should be visible to guest users via the API
- Whether the projection time horizon (currently hardcoded at 90 days) should be configurable per API call
- Whether bulk CSV import/export is needed for mobile (low priority, omitted from v1)
- Rate limit thresholds appropriate for mobile clients (background refresh intervals, etc.)
- Whether AI insights need to be user-triggerable on mobile or automatically refreshed on a schedule

---

## Appendix A — JSON Response Conventions (Recommended)

```jsonc
// Success — collection
{ "data": [...], "meta": { "total": 42, "limit": 50, "offset": 0 } }

// Success — single resource
{ "data": { "id": 1, "name": "...", ... } }

// Created
HTTP 201
{ "data": { "id": 99, ... } }

// No content
HTTP 204

// Error
{ "error": "Schedule not found", "code": "not_found", "status": 404 }
{ "error": "Validation failed", "code": "validation_error", "status": 422,
  "fields": { "amount": "Must be a positive number" } }
```

---

## Appendix B — Minimal `UserToken` Schema

```python
class UserToken(db.Model):
    __tablename__ = "user_tokens"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(256), unique=True, nullable=False)  # SHA-256 of raw token
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    user       = db.relationship("User", backref="tokens")
```

Raw token is returned to client once; only the hash is stored server-side.

---

## Appendix C — Suggested File Layout for the API Blueprint

```
app/
  api/
    __init__.py        # Blueprint definition; registers sub-modules
    auth_utils.py      # Token validation; @api_login_required decorator
    errors.py          # api_error() helper; register error handlers
    validators.py      # Shared validation logic (extracted from main.py)
    routes/
      auth.py          # /auth/login, /auth/logout, /auth/me
      dashboard.py     # /dashboard
      schedules.py     # /schedules CRUD
      balances.py      # /balances
      projections.py   # /projections
      holds.py         # /holds
      skips.py         # /skips
      scenarios.py     # /scenarios
      insights.py      # /insights
```

This layout keeps each domain self-contained and mirrors the web app's existing blueprint pattern.
