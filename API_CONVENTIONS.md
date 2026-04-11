# PyCashFlow API v1 — Conventions

> This document describes the URL structure, response shapes, error shapes, and
> serialization rules that all `/api/v1/` endpoints must follow.

---

## 1. URL Versioning

All API endpoints are prefixed with `/api/v1/`.

```
https://your-host/api/v1/<resource>[/<id>][/<sub-resource>]
```

The existing server-rendered routes (no `/api/` prefix) are unaffected.
When a breaking change is necessary, a new prefix (`/api/v2/`) is introduced
rather than modifying existing endpoints.

---

## 2. Authentication

All endpoints except `POST /api/v1/auth/login` require authentication.

### Bearer Token (primary — mobile / API clients)

```
Authorization: Bearer <raw_token>
```

Tokens are issued by `POST /api/v1/auth/login` and stored as a SHA-256 hash
in the `user_tokens` table.  The raw token is returned once at login and
never stored server-side.  Default TTL: **30 days**.

### Session Cookie (secondary — browser / same-origin)

Flask-Login session cookies issued by the existing `/login` route are also
accepted for **read** operations.  This allows the web app's JavaScript to
call `/api/v1/` endpoints without a separate login step.

### CSRF

The entire `/api/v1/` blueprint is **exempt from CSRF validation**.
Bearer-token clients do not need CSRF tokens.  Session-authenticated browsers
that call mutating API endpoints (`POST`/`PUT`/`DELETE`) must use Bearer
tokens for those requests.

---

## 3. Success Response Shape

### Single resource — `200 OK` or `201 Created`

```jsonc
{
  "data": {
    "id": 42,
    "name": "Rent",
    "amount": "1500.00",
    ...
  }
}
```

### Collection — `200 OK`

```jsonc
{
  "data": [
    { "id": 1, ... },
    { "id": 2, ... }
  ],
  "meta": {
    "total": 47,
    "limit": 50,
    "offset": 0
  }
}
```

`meta` is present only when pagination parameters are applicable.

### No content — `204 No Content`

Empty body.  Used for successful `DELETE` operations.

---

## 4. Error Response Shape

All API errors use a consistent JSON envelope regardless of HTTP status code.

### Standard error

```jsonc
{
  "error":  "Resource not found",   // Human-readable message
  "code":   "not_found",            // Machine-readable slug
  "status": 404                     // Mirror of the HTTP status code
}
```

### Validation error — `422 Unprocessable Entity`

Validation errors additionally include a `fields` map that names the
offending inputs.

```jsonc
{
  "error":  "Validation failed",
  "code":   "validation_error",
  "status": 422,
  "fields": {
    "amount":    "Must be a positive number",
    "frequency": "Must be one of: Monthly, Weekly, BiWeekly, Quarterly, Yearly, Onetime"
  }
}
```

### Error code catalogue

| `code`              | HTTP status | When used                                  |
|---------------------|-------------|--------------------------------------------|
| `unauthorized`      | 401         | Missing or invalid token / session         |
| `forbidden`         | 403         | Authenticated but lacks permission         |
| `not_found`         | 404         | Resource does not exist or is not visible  |
| `method_not_allowed`| 405         | HTTP verb not supported on this path       |
| `validation_error`  | 422         | Request body fails input validation        |
| `internal_error`    | 500         | Unhandled server-side exception            |

---

## 5. Date and Time Serialization

| Type              | Format                    | Example                    |
|-------------------|---------------------------|----------------------------|
| `datetime.date`   | ISO 8601 date string      | `"2026-04-09"`             |
| `datetime.datetime` | ISO 8601 UTC datetime   | `"2026-04-09T14:30:00Z"`   |
| Naive datetimes   | Treated as UTC, same format | `"2026-04-09T14:30:00Z"` |

Rules:
- All datetimes are in **UTC**.  Clients are responsible for local-time conversion.
- Date strings use the `YYYY-MM-DD` format (zero-padded).
- Datetime strings use the `YYYY-MM-DDTHH:MM:SSZ` format (seconds precision, `Z` suffix).
- `null` / `None` values serialise as JSON `null`.

---

## 6. Currency / Amount Serialization

Monetary amounts are serialised as **decimal strings** (not JSON numbers).

```jsonc
{ "amount": "1500.00" }   // correct
{ "amount": 1500.00 }     // incorrect — may lose precision in JS
```

Rules:
- Always two decimal places: `"9.90"`, `"1000.00"`.
- Negative amounts (expenses) are still represented as positive numbers; the
  `type` field (`"Income"` / `"Expense"`) signals the direction.
- Clients should parse with a decimal library, not native `float`.

---

## 7. Pagination (list endpoints)

List endpoints accept optional query parameters:

| Parameter | Default | Max  | Description              |
|-----------|---------|------|--------------------------|
| `limit`   | 50      | 200  | Number of records to return |
| `offset`  | 0       | —    | Number of records to skip   |

The response `meta.total` reflects the total count of matching records
(before pagination) so clients can calculate page counts.

> **Note:** Pagination is not yet implemented on all endpoints.
> It will be added in a subsequent iteration.

---

## 8. HTTP Methods

| Method   | Semantics                                |
|----------|------------------------------------------|
| `GET`    | Read — never modifies state              |
| `POST`   | Create a new resource                    |
| `PUT`    | Replace an existing resource (full update) |
| `PATCH`  | Partial update (reserved for future use) |
| `DELETE` | Remove a resource → `204 No Content`     |

---

## 9. Content Type

All API requests with a body must use `Content-Type: application/json`.
All API responses use `Content-Type: application/json`.

---

## 10. Rate Limiting

The API inherits the application-wide rate limiter (Flask-Limiter).
Per-endpoint limits will be documented alongside each endpoint.
The auth endpoints (`/auth/login`) apply a strict limit to mitigate
brute-force attacks.

---

## Appendix — Current Endpoint Inventory (v1 foundation)

| Method | Path                   | Auth required | Description                  |
|--------|------------------------|---------------|------------------------------|
| POST   | `/api/v1/auth/login`   | No            | Issue bearer token           |
| POST   | `/api/v1/auth/logout`  | Yes           | Revoke current bearer token  |
| GET    | `/api/v1/auth/me`      | Yes           | Current user profile         |

Business endpoints (schedules, balances, projections, etc.) will be added
in subsequent phases per the API_GAP_REPORT.md implementation sequence.

## Billing Endpoints (v1)

- `POST /api/v1/billing/create-checkout-session` (Bearer auth required)
- `POST /api/v1/billing/webhook/stripe` (public, Stripe signature required)
- `POST /api/v1/billing/verify-appstore` (public, server-side verification path)

Subscription enforcement is controlled via `PAYMENTS_ENABLED`.
When enabled, non-global-admin authenticated users must have an active/trial owner subscription.
