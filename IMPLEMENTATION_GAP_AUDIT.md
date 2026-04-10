# API Expansion / Gap Implementation Audit

Date: 2026-04-10
Reference docs:
- `API_EXPANSION_PLAN.md`
- `API_GAP_REPORT.md`
- `INTEGRATION_GAPS.md`

## Overall verdict

Most of the API expansion plan and endpoint gaps are implemented. The backend now includes the planned auth, read, and write API endpoints plus pagination and supporting tests. A few refactor-oriented recommendations from `INTEGRATION_GAPS.md` are still partially or fully outstanding.

## Implemented items (confirmed)

- API v1 blueprint exists and is registered at `/api/v1`.
- Auth API includes login, 2FA continuation, refresh, logout, me, and password change.
- Data API includes:
  - dashboard (with `risk` + `risk_v2`), projections, risk-score,
  - schedules/scenarios/holds/skips list + CRUD/clear endpoints,
  - transactions list,
  - balance read/write + balance history,
  - settings and insights read/refresh endpoints.
- Pagination (`limit`, `offset`) is wired into list endpoints.
- Guest write restrictions are enforced for mutation endpoints.
- iOS app scaffold exists under `/ios-app` with app/core/features structure.
- API foundation and data tests validate these capabilities.

## Outstanding or partial items

1. **Dashboard balance-reset side effect remains in web route**
   - `GET /` in `app/main.py` still deletes/reinserts balance rows on load.
2. **`get_effective_user_id` duplication remains**
   - Still defined independently in web (`main.py`) and API (`data.py`).
3. **Validation extraction is partial**
   - API has local payload validators in `app/api/routes/data.py`, but there is no shared `app/validators.py` used by both web + API.
4. **`Query.get()` deprecation remains**
   - `User.query.get(...)` still used in the login manager loader.
5. **Min-balance logic not extracted as shared utility**
   - API computes min-balance inline in dashboard while web still gets it via `plot_cash()`.

## Confidence basis

- Source review in `app/api/routes/*`, `app/main.py`, `app/__init__.py`, `ios-app/*`, and API docs.
- Test run: `python -m pytest -q tests/test_api_foundation.py tests/test_api_data.py` (100 passed).
