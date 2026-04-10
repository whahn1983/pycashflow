# PyCashFlow API Expansion Plan for SwiftUI Monorepo

Date: 2026-04-10  
Scope: Backend API expansion + `/ios-app` SwiftUI client bootstrapping  
Prerequisite: This plan is based on the current API implementation and current docs (`AGENTS.md`, `CODEX_HANDOFF.md`, `MOBILE_API_REFERENCE.md`, `INTEGRATION_GAPS.md`).

---

## 1) Current-State Audit (What Exists Today)

### Implemented API surface (v1)

- Auth:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
- Read endpoints:
  - `GET /api/v1/dashboard`
  - `GET /api/v1/schedules`
  - `GET /api/v1/projections`
  - `GET /api/v1/scenarios`
  - `GET /api/v1/holds`
  - `GET /api/v1/skips`
  - `GET /api/v1/transactions`
  - `GET /api/v1/risk-score`
  - `GET /api/v1/balance`

### Key observed constraints / inconsistencies

1. API is read-only except auth token lifecycle (no resource mutation endpoints).
2. TOTP-enabled users cannot authenticate via API (login currently rejects 2FA-enabled users).
3. Pagination contract exists in helpers/docs but query params are not wired in data routes.
4. `dashboard.risk` is passed through as raw engine dict (mixed numeric types), while `/risk-score` is serialized more consistently.
5. Dashboard and web route behavior diverges on balance-date normalization side effects.
6. Validation logic is primarily embedded in form handlers in `main.py`, not reusable for JSON APIs.
7. Guest access is supported in data queries via effective-user mapping, but write permissions need explicit mobile-safe handling.

---

## 2) Mobile Product Surface and API Coverage Matrix

The matrix below compares required SwiftUI screens against existing endpoints.

| Mobile Screen | Required Capabilities | Existing API Coverage | Gap |
|---|---|---|---|
| Login | Email/password sign-in, token storage, current user | Partial (`/auth/login`, `/auth/me`) | Missing 2FA continuation endpoint and token refresh |
| Dashboard | Balance summary, risk, min balance, upcoming txns | Mostly covered (`/dashboard`, `/risk-score`, `/balance`) | Data typing inconsistency in risk payload; no cached AI insights API |
| Accounts / Balances | View current balance, update current balance, optional history | Partial (`GET /balance`) | Missing `POST /balance`, missing history |
| Projections | Fetch schedule/scenario projections | Covered (`/projections`) | Optional filter/horizon params absent |
| Recurring Schedules | List, create, edit, delete | List only (`/schedules`) | Missing POST/PUT/DELETE |
| Scenarios | List, create, edit, delete | List only (`/scenarios`) | Missing POST/PUT/DELETE |
| Holds & Skips | List, add/remove hold, add/remove skip, clear all | List only (`/holds`, `/skips`) | Missing mutation endpoints |
| Transactions Feed | View expanded upcoming instances | Covered (`/transactions`) | No pagination or date-range filtering |
| Settings (user) | Change password, view basic profile/settings | Partial (`/auth/me`) | Missing password change endpoint and user settings payload endpoint |
| AI Insights (optional in MVP) | Read cached insights, refresh insights | None in API | Missing insights endpoints |

---

## 3) Required New Endpoints

### Batch 1 — Critical read/completion endpoints (MVP unblock)

1. `POST /api/v1/auth/login/2fa`
   - Purpose: complete login for accounts with TOTP enabled.
   - Request: temporary login challenge + TOTP code (or backup code).
   - Response: same token+user envelope as `/auth/login`.
2. `POST /api/v1/auth/refresh`
   - Purpose: issue new token before/at expiry.
3. `GET /api/v1/settings`
   - Purpose: mobile settings bootstrap (profile flags + app config relevant to client).
4. Pagination wiring for list endpoints:
   - `GET /schedules`, `/scenarios`, `/holds`, `/skips`, `/transactions`
   - Optional params: `limit`, `offset`.
5. AI insights read endpoints (included in MVP):
   - `GET /api/v1/insights`
   - `POST /api/v1/insights/refresh` (server-triggered refresh; mobile remains read-focused)

### Batch 2 — Core write/update flows (full daily-use mobile app)

1. `POST /api/v1/schedules`
2. `PUT /api/v1/schedules/<id>`
3. `DELETE /api/v1/schedules/<id>`
4. `POST /api/v1/scenarios`
5. `PUT /api/v1/scenarios/<id>`
6. `DELETE /api/v1/scenarios/<id>`
7. `POST /api/v1/balance`
8. `POST /api/v1/holds`
9. `DELETE /api/v1/holds/<id>`
10. `POST /api/v1/skips`
11. `DELETE /api/v1/skips/<id>`

### Batch 3 — Secondary features

1. `DELETE /api/v1/holds` (clear all)
2. `DELETE /api/v1/skips` (clear all)
3. `GET /api/v1/balance/history`
4. `PUT /api/v1/auth/password`
5. (Reserved for additional post-MVP endpoints if needed)

---

## 4) Changes to Existing Endpoints

1. **`GET /dashboard`**
   - Keep existing fields (backward compatibility).
   - Add optional `risk_v2` field (fully serialized decimal-string-safe object).
   - Mark existing `risk` as deprecated immediately for clients; keep both during migration.
   - Plan removal of raw `risk` only after migration window and documented client cutover.
2. **List endpoints**
   - Preserve existing default behavior when `limit/offset` absent.
   - Add `meta.limit` and `meta.offset` when params are supplied.
3. **`GET /projections`**
   - Keep current schema; optionally add query params (`horizon_days`) as optional only.
4. **Auth endpoints**
   - `POST /auth/login` should return structured signal when 2FA required (without leaking credential validity); proposed pattern:
     - still generic on invalid creds,
     - but if primary auth succeeds and 2FA enabled, return `403` with code `twofa_required` and short-lived challenge token.
   - Persist 2FA challenge server-side for MVP with short TTL, one-time use, attempt limits, and invalidation on success/failure/timeout.

---

## 5) Endpoint-to-Screen Mapping (Target SwiftUI App)

| Screen | Endpoints |
|---|---|
| Launch / Session bootstrap | `GET /auth/me`, `POST /auth/refresh` |
| Login | `POST /auth/login`, `POST /auth/login/2fa` |
| Dashboard Home | `GET /dashboard`, `GET /risk-score` |
| Balance Detail | `GET /balance`, `POST /balance`, `GET /balance/history` |
| Schedules List | `GET /schedules` |
| Schedule Editor | `POST /schedules`, `PUT /schedules/<id>`, `DELETE /schedules/<id>` |
| Scenarios List | `GET /scenarios` |
| Scenario Editor | `POST /scenarios`, `PUT /scenarios/<id>`, `DELETE /scenarios/<id>` |
| Holds/Skips Management | `GET /holds`, `GET /skips`, `POST/DELETE` holds/skips endpoints |
| Transactions Feed | `GET /transactions` |
| Settings | `GET /settings`, `PUT /auth/password`, `POST /auth/logout` |
| AI Card (optional) | `GET /insights`, `POST /insights/refresh` |

---

## 6) Auth and Authorization Considerations

1. Preserve dual-mode auth (`Bearer` + session), but SwiftUI app uses Bearer only.
2. Maintain guest-owner data mapping for reads via effective user ID.
3. Enforce write restrictions:
   - guest users are read-only and must receive `403 forbidden` on all mutation endpoints.
4. 2FA API flow should avoid credential oracle leaks:
   - constant-time checks remain,
   - minimal error differentiation,
   - short-lived signed challenge for second step.
5. Token refresh must be additive and non-breaking for current clients:
   - preserve existing login/logout request/response contract,
   - if refresh tokens are introduced, prefer short-lived access tokens + rotated refresh tokens for mobile.

---

## 7) Data Model / Validation Implications

1. No destructive schema rewrite required; existing tables support core CRUD.
2. Additive migration likely needed for API 2FA challenge table or token-challenge fields (if persistent challenges are chosen).
3. Extract shared validators from `main.py` into a reusable module (`app/validators.py`), then call from both web forms and JSON APIs.
4. Add reusable helper for effective user ownership resolution to avoid duplicated logic.
5. Keep serialization rules unchanged (amount decimal strings, ISO dates, response envelopes).

---

## 8) Monorepo iOS Structure Plan (`/ios-app`)

Proposed repository layout:

```text
/ios-app
  /PyCashFlowApp.xcodeproj
  /PyCashFlowApp
    /App
    /Core
      /Networking      (APIClient, Endpoint, AuthInterceptor)
      /Auth            (SessionManager, KeychainTokenStore)
      /Models          (DTOs aligned with API envelopes)
      /Utilities       (Date/Decimal decoding helpers)
    /Features
      /Login
      /Dashboard
      /Accounts
      /Schedules
      /Scenarios
      /Settings
    /Resources
  /README.md
```

Principles:
- iOS app consumes only HTTP API contracts.
- No backend code imports/shared runtime internals.
- Shared documentation remains in root (`MOBILE_API_REFERENCE.md`, `API_CONVENTIONS.md`).

---

## 9) Delivery Phasing (Implementation Sequence)

### Phase A — API MVP unblock
- Implement Batch 1 endpoints + pagination wiring.
- Add tests for auth 2FA flow (including persisted challenge lifecycle) and paginated reads.
- Update `MOBILE_API_REFERENCE.md`.

### Phase B — Core CRUD
- Implement Batch 2 endpoints using shared validators.
- Add tests for success/validation/authz for each mutation.
- Ensure no regressions for web routes.

### Phase C — iOS bootstrap
- Create `/ios-app` SwiftUI project.
- Implement:
  - API client with envelope decoding,
  - session/token manager,
  - login flow (including 2FA step if required),
  - initial screens: login, dashboard, accounts.

### Phase D — Secondary APIs + polish
- Implement Batch 3 endpoints.
- Expand iOS screens for schedules/scenarios/settings.
- Add docs updates and integration notes.

---

## 10) Test Strategy

### Backend
- Extend `tests/test_api_foundation.py` for auth/2FA/refresh envelope rules.
- Extend `tests/test_api_data.py` for:
  - pagination (`limit`, `offset`),
  - CRUD endpoints,
  - permission checks (guest vs owner),
  - validation `fields` payloads.

### iOS
- Unit tests:
  - API envelope decoding,
  - Decimal/date parsing,
  - SessionManager token transitions.
- Integration sanity:
  - login → me → dashboard flow,
  - login (2FA-required user) → challenge verify → token issuance,
  - AI insights load and refresh display flow,
  - unauthorized refresh handling,
  - user-visible loading/error states.

---

## 11) Prioritization: MVP → Full App

### MVP (must ship first)
- Auth that works for both non-2FA and 2FA accounts.
- Dashboard + projections + current balance read.
- Schedule CRUD.
- Balance update.
- AI insights read/refresh display support.
- Basic SwiftUI app with Login, Dashboard, Accounts.

### Full app
- Scenario CRUD.
- Holds/skips mutation flows.
- Settings/password change.
- Balance history and additional quality-of-life APIs.

---

## 12) Decisions Captured (from review)

1. Guests remain read-only for all API mutation endpoints.
2. Token refresh must be additive and backward-compatible with current login/logout contracts.
3. 2FA challenge state is persisted server-side for MVP with TTL, one-time use, attempt limits, and strict invalidation.
4. AI insights are included in MVP as read-focused mobile functionality.
5. `/dashboard` keeps both `risk` and `risk_v2` during migration; `risk` is deprecated now and removed after migration.

---

## 13) Implementation Guardrails

- No breaking changes to existing response envelope or field names.
- New query params remain optional.
- New migrations are additive only.
- Reuse business logic from existing modules; avoid duplicating rules in SwiftUI.
- If mobile needs new behavior, add/refine API endpoint rather than embedding business logic client-side.
