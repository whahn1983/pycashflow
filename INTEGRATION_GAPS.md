# PyCashFlow — Integration Gaps

> Where template-oriented logic blocks clean mobile API use, what endpoints
> are still missing, and what refactors would help before building more APIs.

---

## 1. Template-Oriented Logic That Blocks Clean API Use

### 1.1 Balance side-effect on dashboard load

**File:** `app/main.py` lines 53–114 (the `index()` route)

The web dashboard's `GET /` route **deletes all Balance rows for the user and
re-inserts a single row** with today's date on every page load (lines 67–76).
This is a data-mutating side effect inside a GET request.

The API `GET /api/v1/dashboard` does **not** replicate this behavior — it reads
the latest balance without mutation. This creates a subtle divergence: after a
web dashboard visit, the balance date is always "today"; the API returns
whatever date was last written.

**Risk:** If the web app is used alongside the mobile app, balance dates will
be inconsistent depending on which interface was used last.

**Recommendation:** Extract balance retrieval into a shared function. Move the
"reset balance date" logic into an explicit `POST /balance` action, or
remove it entirely if it's not essential.

### 1.2 Form-based validation is not reusable

**File:** `app/main.py` lines 177–225 (`create()` route)

Schedule creation validation is implemented inline within the Flask form
handler: checking name length, parsing amount, validating type/frequency
enums, checking for duplicates. This logic is tightly coupled to
`request.form` and `flash()` messages.

When write API endpoints are added, this validation will need to be
reimplemented for JSON input. The two copies will inevitably diverge.

**Recommendation:** Extract validation into a shared module
(e.g., `app/validators.py`) that accepts plain dicts and returns structured
error dicts. Both the web form handler and API route can call the same
validator.

### 1.3 Plotly chart generation in business logic

**File:** `app/cashflow.py` — `plot_cash()` function

The `plot_cash()` function generates a Plotly interactive HTML chart. This is
called by the web dashboard but is irrelevant for mobile clients (who will
render their own charts from the `/projections` data points).

The API correctly bypasses `plot_cash()` and uses `update_cash()` directly.
However, `plot_cash()` also computes `minbalance` and `min_scenario` as
side outputs. The API dashboard reimplements this min-balance calculation
(lines 92–101 of `data.py`), creating a second copy of the logic.

**Recommendation:** Extract min-balance computation from `plot_cash()` into a
standalone function that both web and API routes can call.

### 1.4 Flash messages as validation feedback

Throughout `main.py`, validation failures are communicated via `flash()`
messages followed by redirects. This pattern is web-only — API routes must
return JSON error bodies. The two feedback mechanisms share no code.

**Affected routes:** `/create`, `/update`, `/create_scenario`,
`/update_scenario`, `/balance`, `/changepw`, `/create_user`, `/update_user`,
`/add_guest`, `/ai_settings`, `/email`, `/global_email_settings`.

### 1.5 `get_effective_user_id()` is duplicated

The function exists in two places with identical logic:
- `app/main.py:39` — uses `current_user` (Flask-Login)
- `app/api/routes/data.py:37` — uses `get_api_user()` (Bearer/session)

Both resolve guest → owner mapping. Having two copies means a bug fix in one
may not reach the other.

**Recommendation:** Create a single helper that accepts a user object and
returns the effective user ID. Both call sites pass in their resolved user.

---

## 2. Endpoints Still Needed for a Practical iOS App

### Must-have (P0)

| Method | Path | Purpose | Web equivalent |
|--------|------|---------|----------------|
| POST | `/api/v1/schedules` | Create a new schedule | `POST /create` |
| PUT | `/api/v1/schedules/<id>` | Update a schedule | `POST /update` |
| DELETE | `/api/v1/schedules/<id>` | Delete a schedule | `POST /delete/<id>` |
| POST | `/api/v1/balance` | Update current balance | `POST /balance` |

Without these, the mobile app is read-only and users must switch to the web
app for any modifications.

### Should-have (P1)

| Method | Path | Purpose | Web equivalent |
|--------|------|---------|----------------|
| POST | `/api/v1/scenarios` | Create a scenario | `POST /create_scenario` |
| PUT | `/api/v1/scenarios/<id>` | Update a scenario | `POST /update_scenario` |
| DELETE | `/api/v1/scenarios/<id>` | Delete a scenario | `POST /delete_scenario/<id>` |
| POST | `/api/v1/holds` | Put a schedule on hold | `POST /addhold/<id>` |
| DELETE | `/api/v1/holds/<id>` | Remove a hold | `POST /deletehold/<id>` |
| POST | `/api/v1/skips` | Skip a transaction instance | `POST /addskip/<id>` |
| DELETE | `/api/v1/skips/<id>` | Remove a skip | `POST /deleteskip/<id>` |
| POST | `/api/v1/auth/login/2fa` | TOTP verification for API login | `POST /login/2fa` |

### Nice-to-have (P2)

| Method | Path | Purpose | Web equivalent |
|--------|------|---------|----------------|
| POST | `/api/v1/auth/refresh` | Extend token lifetime | None (new) |
| GET | `/api/v1/balance/history` | List historical balances | `GET /balance` |
| GET | `/api/v1/transactions` | 90-day transaction preview | `GET /transactions` |
| GET | `/api/v1/insights` | Cached AI insights | Inline on `GET /` |
| POST | `/api/v1/insights/refresh` | Trigger new AI analysis | `POST /ai_insights` |
| PUT | `/api/v1/auth/password` | Change password | `POST /changepw` |
| DELETE | `/api/v1/holds` | Clear all holds | `POST /clearholds` |
| DELETE | `/api/v1/skips` | Clear all skips | `POST /clearskips` |
| GET | `/api/v1/export` | Download schedules as CSV | `GET /export` |

### Not needed for mobile (admin-only, web-only)

These routes are admin or system configuration and do not need API equivalents
for the initial mobile release:

- User management (`/create_user`, `/update_user`, `/delete_user`, etc.)
- Global admin (`/global_admin`, `/global_email_settings`)
- Guest management (`/manage_guests`, `/add_guest`, `/remove_guest`)
- Signup control (`/signups`)
- Email ingestion config (`/email`)
- 2FA setup (`/setup_2fa`, `/disable_2fa`)
- Passkey management (registration/deletion)

---

## 3. Recommended Refactors Before Building More APIs

### 3.1 Extract input validation (high priority)

**Current state:** Validation for schedules, scenarios, balance, password
changes, and user creation is scattered across `main.py` in ~15 different
route handlers. Each handler reads from `request.form`, validates inline,
and uses `flash()` for errors.

**What to do:** Create `app/validators.py` with functions like:

```python
def validate_schedule(data: dict) -> dict[str, str]:
    """Return a dict of field→error. Empty dict means valid."""
```

Both web routes (reading from `request.form`) and API routes (reading from
`request.get_json()`) call the same validators. Errors map directly to the
API's `fields` dict in 422 responses.

### 3.2 Unify `get_effective_user_id()` (medium priority)

Create a single function in a shared location:

```python
# app/utils.py
def effective_user_id(user) -> int:
    return user.account_owner_id or user.id
```

Replace both copies in `main.py` and `data.py`.

### 3.3 Extract min-balance calculation (medium priority)

`plot_cash()` in `cashflow.py` computes `minbalance` as a side output of
chart generation. The API dashboard reimplements this calculation. Extract it:

```python
def min_balance_in_window(run_df, horizon_days=90) -> float:
    ...
```

### 3.4 Formalize the risk-score return type (medium priority)

`calculate_cash_risk_score()` returns a plain dict with Python floats. For API
consumers, this should pass through a serializer that formats numeric values
consistently. Either:

- Add `serialize_risk_score(risk_dict)` to `serializers.py`, or
- Have `calculate_cash_risk_score()` return a typed dataclass/NamedTuple

### 3.5 Fix `Query.get()` deprecation (low priority)

**File:** `app/__init__.py` line 80

```python
return User.query.get(int(user_id))
```

This triggers 38 `LegacyAPIWarning` during tests. Replace with:

```python
return db.session.get(User, int(user_id))
```

This is a one-line fix but affects every request (it's in the Flask-Login
user loader).

### 3.6 Remove balance-reset side effect (low priority)

The `index()` route in `main.py` deletes and recreates the Balance row on
every GET request. This is unusual and creates the API/web divergence
described in section 1.1. Consider whether this behavior is actually needed
— if so, make it an explicit user action rather than a side effect of viewing
the dashboard.

---

## 4. Summary of Risk Areas

| Area | Risk Level | Impact |
|------|-----------|--------|
| No write endpoints | **High** | Mobile app is useless for data entry |
| 2FA blocks API login | **High** | Security-conscious users locked out |
| Balance-reset side effect | **Medium** | Data inconsistency between web and API |
| Duplicated validation logic | **Medium** | Web and API will diverge when writes are added |
| Risk score as raw dict | **Low** | API contract is fragile — any engine change breaks clients |
| No pagination | **Low** | Works fine until users have hundreds of schedules |
| SQLAlchemy deprecation | **Low** | Will break on next major SQLAlchemy upgrade |
