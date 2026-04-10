# PyCashFlow — Mobile API Reference (v1)

> Complete endpoint-by-endpoint documentation for iOS/mobile client developers.
> Generated from source code inspection — not aspirational.

---

## Base URL and Versioning

```
https://<host>/api/v1/
```

All API endpoints are prefixed with `/api/v1/`. The web app's server-rendered
routes (no `/api/` prefix) are unaffected. Breaking changes will use a new
version prefix (`/api/v2/`).

**Content type:** All requests with a body must send `Content-Type: application/json`.
All responses return `Content-Type: application/json`.

**Max request body:** 2 MB.

---

## Authentication

### Bearer Token (primary)

```
Authorization: Bearer <raw_token>
```

Tokens are issued by `POST /api/v1/auth/login`. The raw token is returned
once — only its SHA-256 hash is stored server-side. **Default TTL: 30 days.**

After 30 days the token expires silently. The client must re-authenticate.
There is no refresh endpoint.

### Session Cookie (secondary)

Flask-Login session cookies from the web app's `/login` route are also
accepted. This is a convenience for same-origin browser JavaScript — mobile
clients should use Bearer tokens exclusively.

### CSRF

The entire `/api/v1/` blueprint is **exempt from CSRF validation**. Mobile
clients do not need CSRF tokens.

### Rate Limiting

`POST /api/v1/auth/login` is rate-limited to **10 requests per minute** per
IP address. Other endpoints inherit the application-wide default limits.

### 2FA Restriction

**Users with TOTP two-factor authentication enabled cannot obtain a Bearer
token.** The login endpoint returns 401 for these users. There is currently
no API-based 2FA verification flow.

---

## Response Shapes

### Success — Single Resource

HTTP `200 OK` or `201 Created`:

```json
{
  "data": {
    "id": 42,
    "name": "Rent",
    "amount": "1500.00"
  }
}
```

### Success — Collection

HTTP `200 OK`:

```json
{
  "data": [
    { "id": 1, "name": "Rent", "amount": "1200.00" },
    { "id": 2, "name": "Salary", "amount": "5000.00" }
  ],
  "meta": {
    "total": 2
  }
}
```

> **Note:** `meta.limit` and `meta.offset` are defined in the conventions but
> not currently populated — pagination query parameters are not yet wired up.

### Success — No Content

HTTP `204 No Content` with an empty body (used for DELETE operations — none
exist yet).

### Error — Standard

```json
{
  "error": "Authentication required",
  "code": "unauthorized",
  "status": 401
}
```

### Error — Validation (422)

```json
{
  "error": "Validation failed",
  "code": "validation_error",
  "status": 422,
  "fields": {
    "email": "Email is required",
    "password": "Password is required"
  }
}
```

### Error Code Catalogue

| `code` | HTTP | When |
|--------|------|------|
| `unauthorized` | 401 | Missing, invalid, or expired token |
| `forbidden` | 403 | Authenticated but lacks permission |
| `not_found` | 404 | Resource does not exist (API paths only) |
| `method_not_allowed` | 405 | HTTP verb not supported |
| `validation_error` | 422 | Request body fails validation |
| `internal_error` | 500 | Unhandled server exception |

---

## Serialization Rules

### Dates

| Python type | JSON format | Example |
|-------------|-------------|---------|
| `datetime.date` | `"YYYY-MM-DD"` | `"2026-04-09"` |
| `datetime.datetime` | `"YYYY-MM-DDTHH:MM:SSZ"` | `"2026-04-09T14:30:00Z"` |
| `None` | `null` | `null` |

All datetimes are UTC. Naive datetimes are treated as UTC. Clients must
handle local-time conversion.

### Monetary Amounts

Amounts are serialized as **decimal strings with 2 decimal places**:

```json
{ "amount": "1500.00" }
```

- Never JSON numbers (avoids JavaScript floating-point precision loss).
- Always 2 decimal places: `"9.90"`, `"0.00"`, `"1000.00"`.
- Amounts are always positive. The `type` field (`"Income"` or `"Expense"`)
  indicates the direction.
- Clients should parse with a decimal library (`NSDecimalNumber` on iOS),
  not native floating-point.

### Nullability

Fields documented as nullable will return JSON `null` when absent. String
fields are never empty strings — they are either populated or `null`.

---

## Endpoints

---

### POST /api/v1/auth/login

Authenticate with email and password. Returns a Bearer token.

**Auth required:** No

**Rate limit:** 10/minute

**Request:**

```json
{
  "email": "user@example.com",
  "password": "s3cr3t"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `email` | string | Yes | Trimmed and lowercased server-side |
| `password` | string | Yes | Not trimmed |

**Response `200 OK`:**

```json
{
  "data": {
    "token": "dG9rZW4tZXhhbXBsZS0xMjM0NTY3ODkw...",
    "user": {
      "id": 1,
      "email": "user@example.com",
      "name": "Alice",
      "is_admin": true,
      "is_global_admin": false,
      "twofa_enabled": false,
      "is_guest": false
    }
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `token` | string | URL-safe, 256-bit. Store in Keychain. |
| `user.id` | integer | Stable user identifier |
| `user.email` | string | Lowercase |
| `user.name` | string | Display name |
| `user.is_admin` | boolean | Account owner (not just admin role) |
| `user.is_global_admin` | boolean | System-wide administrator |
| `user.twofa_enabled` | boolean | Always `false` in successful login (2FA users are rejected) |
| `user.is_guest` | boolean | `true` if `account_owner_id` is set |

**Response `401 Unauthorized`:**

Returned when:
- Email/password combination is invalid
- User account is inactive (`is_active = false`)
- User has 2FA enabled (no API 2FA flow exists)

```json
{
  "error": "Invalid credentials or account is not active",
  "code": "unauthorized",
  "status": 401
}
```

The error message is deliberately identical for all failure reasons to prevent
credential-validation oracle attacks.

**Response `422 Validation Error`:**

```json
{
  "error": "Validation failed",
  "code": "validation_error",
  "status": 422,
  "fields": {
    "email": "Email is required",
    "password": "Password is required"
  }
}
```

---

### POST /api/v1/auth/logout

Revoke the Bearer token used in this request.

**Auth required:** Yes (Bearer or session)

**Request:** Empty body.

**Response `200 OK`:**

```json
{
  "data": {
    "message": "Logged out"
  }
}
```

**Behavior notes:**
- If the request was authenticated via Bearer token, that token is deleted
  from the database and can never be used again.
- If the request was authenticated via session cookie only (no Bearer header),
  the session is not modified. The caller should use the web `/logout` route
  to clear the session.

---

### GET /api/v1/auth/me

Return the currently authenticated user's public profile.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": {
    "id": 1,
    "email": "user@example.com",
    "name": "Alice",
    "is_admin": true,
    "is_global_admin": false,
    "twofa_enabled": false,
    "is_guest": false
  }
}
```

The user object shape is identical to the `user` field in the login response.
Sensitive fields (password, 2FA secret, backup codes) are never included.

---

### GET /api/v1/dashboard

Dashboard summary for a mobile home screen.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": {
    "balance": "5000.00",
    "balance_date": "2026-04-09",
    "risk": {
      "score": 85,
      "status": "Safe",
      "color": "green",
      "runway_days": 120,
      "lowest_balance": 2500.0,
      "days_to_lowest": 15,
      "avg_daily_expense": 45.5,
      "days_below_threshold": 0,
      "pct_below_threshold": 0.0,
      "recovery_days": 0,
      "near_term_buffer": 3200.0
    },
    "upcoming_transactions": [
      {
        "name": "Rent",
        "type": "Expense",
        "amount": "1200.00",
        "date": "2026-04-15"
      },
      {
        "name": "Salary",
        "type": "Income",
        "amount": "5000.00",
        "date": "2026-04-30"
      }
    ],
    "min_balance": "3200.00"
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `balance` | string (decimal) | Latest balance amount |
| `balance_date` | string (date) | Date of latest balance |
| `risk.score` | integer | 0–100 (higher is safer) |
| `risk.status` | string | `"Safe"` / `"Stable"` / `"Watch"` / `"Risk"` / `"Critical"` |
| `risk.color` | string | CSS color name for UI |
| `risk.runway_days` | number or `null` | Days until funds run out at current burn rate; `null` when no expense drain is observed (stable/improving balance) |
| `risk.lowest_balance` | number | **Caution: Python float, not decimal string** |
| `risk.days_to_lowest` | number | Days until projected lowest point |
| `risk.avg_daily_expense` | number | **Caution: Python float** |
| `risk.days_below_threshold` | number | Days projected below 1-month expense |
| `risk.pct_below_threshold` | number | **Caution: Python float (0.0–1.0)** |
| `risk.recovery_days` | number | Days from lowest point back to threshold |
| `risk.near_term_buffer` | number | **Caution: Python float** |
| `upcoming_transactions` | array | Transactions in next 90 days (day 1–89) |
| `upcoming_transactions[].name` | string | Transaction name |
| `upcoming_transactions[].type` | string | `"Income"` or `"Expense"` |
| `upcoming_transactions[].amount` | string (decimal) | Serialized with 2 decimal places |
| `upcoming_transactions[].date` | string (date) | ISO 8601 |
| `min_balance` | string (decimal) | Minimum projected balance within 90 days |

**Known issue:** The `risk` object values use Python float serialization (not
decimal strings). This is inconsistent with the decimal-string convention used
elsewhere. Mobile clients should treat numeric values in `risk` as
floating-point.

**Guest behavior:** Guest users receive their account owner's data
(balance, schedules, projections).

---

### GET /api/v1/schedules

List all recurring scheduled transactions.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": [
    {
      "id": 1,
      "name": "Rent",
      "amount": "1200.00",
      "type": "Expense",
      "frequency": "Monthly",
      "start_date": "2026-01-01",
      "first_date": "2026-01-01"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Stable identifier |
| `name` | string | Unique per user |
| `amount` | string (decimal) | Always positive, 2 decimal places |
| `type` | string | `"Income"` or `"Expense"` |
| `frequency` | string | One of: `"Monthly"`, `"BiWeekly"`, `"Quarterly"`, `"Yearly"`, `"Weekly"`, `"Onetime"` |
| `start_date` | string (date) | When the schedule begins |
| `first_date` | string (date) | First occurrence date |

**Note:** The model columns are `startdate` and `firstdate` (no underscore).
The serializer maps them to `start_date` and `first_date` (with underscore)
in JSON output. Any future write endpoint must accept the underscored form and
map back.

---

### GET /api/v1/projections

Running-balance projection data points for charting.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": {
    "schedule": [
      { "date": "2026-04-09", "amount": "5000.00" },
      { "date": "2026-04-15", "amount": "3800.00" },
      { "date": "2026-04-30", "amount": "8800.00" }
    ],
    "scenario": [
      { "date": "2026-04-09", "amount": "5000.00" },
      { "date": "2026-04-15", "amount": "2600.00" },
      { "date": "2026-04-30", "amount": "7600.00" }
    ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `schedule` | array | Running balance from schedules only. Empty `[]` if no data. |
| `schedule[].date` | string (date) | ISO 8601 |
| `schedule[].amount` | string (decimal) | Running balance at that date |
| `scenario` | array or `null` | Combined schedule + scenario projection. `null` if no scenarios exist. |

**Important:** `schedule` is `[]` (empty array) when no projection data exists.
`scenario` is `null` when no scenario items exist, or an array when they do.
Clients must handle both `null` and array for `scenario`.

---

### GET /api/v1/scenarios

List all what-if scenario items.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": [
    {
      "id": 1,
      "name": "Job Loss",
      "amount": "3000.00",
      "type": "Expense",
      "frequency": "Monthly",
      "start_date": "2026-05-01",
      "first_date": "2026-05-01"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

Fields are identical to the schedule object shape.

---

### GET /api/v1/holds

List all held (paused) schedule items.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": [
    {
      "id": 1,
      "name": "Gym Membership",
      "amount": "50.00",
      "type": "Expense"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Hold record identifier |
| `name` | string | Name of the held schedule item |
| `amount` | string (decimal) | Amount of the held item |
| `type` | string | `"Income"` or `"Expense"` |

Holds do not have `date`, `frequency`, `start_date`, or `first_date` fields.

---

### GET /api/v1/skips

List all skipped transaction instances.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": [
    {
      "id": 1,
      "name": "Rent",
      "date": "2026-04-15",
      "amount": "1200.00",
      "type": "Expense"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Skip record identifier |
| `name` | string | Name of the skipped schedule item |
| `date` | string (date) | Specific date being skipped |
| `amount` | string (decimal) | Amount of the skipped instance |
| `type` | string | `"Income"` or `"Expense"` |

---

### GET /api/v1/transactions

List all upcoming transactions for the next 90 days. Each transaction is an
individual occurrence expanded from the user's recurring schedules, with holds
and skips applied. This is the dedicated equivalent of the
`upcoming_transactions` array inside `/dashboard`, but as a standalone
collection endpoint.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": [
    {
      "name": "Rent",
      "type": "Expense",
      "amount": "1200.00",
      "date": "2026-04-15"
    },
    {
      "name": "Salary",
      "type": "Income",
      "amount": "5000.00",
      "date": "2026-04-30"
    }
  ],
  "meta": {
    "total": 2
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Transaction name (from schedule) |
| `type` | string | `"Income"` or `"Expense"` |
| `amount` | string (decimal) | Serialized with 2 decimal places |
| `date` | string (date) | ISO 8601 date of this occurrence |

**Note:** Transactions do not have `id`, `frequency`, or `start_date` fields —
they are expanded instances of schedules, not the schedule definitions
themselves. Use `/schedules` to get the schedule records.

**Empty state:** `data` will be `[]` with `meta.total` of `0` when no
upcoming transactions exist.

---

### GET /api/v1/risk-score

Detailed cash-flow risk assessment. Returns the full risk-score breakdown
with monetary values serialized as decimal strings (unlike the `risk` object
inside `/dashboard`, which passes through raw Python floats).

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": {
    "score": 85,
    "status": "Safe",
    "color": "green",
    "runway_days": 120.0,
    "lowest_balance": "2500.00",
    "days_to_lowest": 15,
    "avg_daily_expense": "45.50",
    "days_below_threshold": 0,
    "pct_below_threshold": 0.0,
    "recovery_days": 0,
    "near_term_buffer": "3200.00"
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `score` | integer | 0–100 (higher is safer) |
| `status` | string | `"Safe"` / `"Stable"` / `"Watch"` / `"Risk"` / `"Critical"` |
| `color` | string | CSS color name for UI theming |
| `runway_days` | number or `null` | Days until funds run out at current burn rate; `null` when no expense drain is observed (stable/improving balance) |
| `lowest_balance` | string (decimal) | Lowest projected balance (decimal string) |
| `days_to_lowest` | integer | Days until projected lowest point |
| `avg_daily_expense` | string (decimal) | Average daily expense (decimal string) |
| `days_below_threshold` | integer | Days projected below 1-month expense reserve |
| `pct_below_threshold` | number | Fraction of horizon below threshold (0.0–1.0) |
| `recovery_days` | integer or `null` | Days from lowest back to threshold; `null` if never recovers; `0` if threshold never breached |
| `near_term_buffer` | string (decimal) | Minimum balance over next 14 days (decimal string) |

**Difference from `/dashboard`:** The `/risk-score` endpoint serializes
`lowest_balance`, `avg_daily_expense`, and `near_term_buffer` as decimal
strings, consistent with the API's amount conventions. The `risk` object in
`/dashboard` returns these as raw JSON numbers for backward compatibility.

**Status thresholds:**

| Score | Status | Color |
|-------|--------|-------|
| 80–100 | Safe | green |
| 60–79 | Stable | blue |
| 40–59 | Watch | yellow |
| 20–39 | Risk | orange |
| 0–19 | Critical | red |

---

### GET /api/v1/balance

Current balance snapshot. A lightweight endpoint that returns only the
latest balance record without running the projection engine. Ideal for
widgets, notifications, and quick balance checks.

**Auth required:** Yes (Bearer or session)

**Response `200 OK`:**

```json
{
  "data": {
    "id": 1,
    "amount": "5000.00",
    "date": "2026-04-09"
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer or `null` | Balance record ID; `null` if no balance exists |
| `amount` | string (decimal) | Current balance, 2 decimal places |
| `date` | string (date) | Date of the balance record |

**No balance record:** When no balance has been set, the response returns
`id: null`, `amount: "0.00"`, and `date` set to today's date.

**Note:** This is a single-resource response (`"data": { ... }`) — there is
no `meta` key. Use `/dashboard` if you also need risk score and projections.

---

## Client Implementation Notes

### Token Storage

Store the Bearer token in the iOS Keychain (`kSecClassGenericPassword`).
Never store it in UserDefaults or plain text.

### 401 Handling

On any `401` response, discard the stored token and redirect to the login
screen. Do not retry the request — the token is invalid or expired.

### Decimal Handling

Use `NSDecimalNumber` (or Swift's `Decimal`) for all amount fields. Do not
use `Double` or `Float` — currency arithmetic requires exact decimal
representation.

### Risk Object

The `risk` object inside `/dashboard` uses native JSON numbers (Python
floats), unlike all other monetary fields. Parse these as `Double` — they are
informational scores and ratios, not currency values.

### Empty States

- `/schedules`, `/scenarios`, `/holds`, `/skips`, `/transactions` — `data`
  will be `[]` with `meta.total` of `0` when the user has no items.
- `/projections` — `schedule` will be `[]`; `scenario` will be `null`.
- `/dashboard` — `upcoming_transactions` will be `[]`; `balance` defaults to
  `"0.00"` if no balance record exists.
- `/balance` — returns `id: null`, `amount: "0.00"`, `date: "<today>"` when
  no balance record exists.
- `/risk-score` — always returns a valid score object; when no schedules
  exist the score reflects a neutral assessment.

---

## 2026-04-10 Expansion Update

The following endpoints are now implemented and available for mobile clients:

- Auth:
  - `POST /api/v1/auth/login/2fa`
  - `POST /api/v1/auth/refresh`
  - `PUT /api/v1/auth/password`
- Settings + AI:
  - `GET /api/v1/settings`
  - `GET /api/v1/insights`
  - `POST /api/v1/insights/refresh`
- Balances:
  - `POST /api/v1/balance`
  - `GET /api/v1/balance/history`
- Schedules CRUD:
  - `POST /api/v1/schedules`
  - `PUT /api/v1/schedules/<id>`
  - `DELETE /api/v1/schedules/<id>`
- Scenarios CRUD:
  - `POST /api/v1/scenarios`
  - `PUT /api/v1/scenarios/<id>`
  - `DELETE /api/v1/scenarios/<id>`
- Holds/Skips mutations:
  - `POST /api/v1/holds`
  - `DELETE /api/v1/holds/<id>`
  - `DELETE /api/v1/holds`
  - `POST /api/v1/skips`
  - `DELETE /api/v1/skips/<id>`
  - `DELETE /api/v1/skips`

Additional behavior updates:
- Pagination query params `limit` / `offset` are now supported on list endpoints.
- `/dashboard` now includes both legacy `risk` and serialized `risk_v2`; `risk` is deprecated.
- Guests remain read-only and receive `403 forbidden` on mutation endpoints.
