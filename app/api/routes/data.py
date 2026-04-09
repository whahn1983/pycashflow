"""API v1 read-only data endpoints for mobile clients.

Endpoints
---------
GET   /api/v1/dashboard     Dashboard summary (balance, risk score, projections overview)
GET   /api/v1/schedules     List recurring scheduled transactions
GET   /api/v1/projections   Running-balance projection data points
GET   /api/v1/scenarios     List what-if scenario items
GET   /api/v1/holds         List held (paused) schedule items
GET   /api/v1/skips         List skipped transaction instances

All endpoints require authentication via Bearer token or active session.
"""

from datetime import datetime

from sqlalchemy import desc

from app import db
from app.models import Schedule, Scenario, Balance, Hold, Skip
from app.cashflow import update_cash, calculate_cash_risk_score

from app.api import api
from app.api.auth_utils import api_login_required, get_api_user
from app.api.responses import api_ok, api_list
from app.api.serializers import (
    serialize_schedule,
    serialize_scenario,
    serialize_balance,
    serialize_hold,
    serialize_skip,
    _amount,
    _date,
)


def _effective_user_id():
    """Return the data-owning user ID for the current API request.

    Guest users see their account owner's data; everyone else sees their own.
    Mirrors ``main.get_effective_user_id()`` but uses the API auth context.
    """
    user = get_api_user()
    if user.account_owner_id:
        return user.account_owner_id
    return user.id


# ── GET /api/v1/dashboard ────────────────────────────────────────────────────

@api.route("/dashboard", methods=["GET"])
@api_login_required
def api_dashboard():
    """Return a dashboard summary suitable for a mobile home screen.

    Response 200::

        {
          "data": {
            "balance": "5000.00",
            "balance_date": "2026-04-09",
            "risk": { "score": 85, "status": "Safe", "color": "green", ... },
            "upcoming_transactions": [ ... ],
            "min_balance": "3200.00"
          }
        }
    """
    user_id = _effective_user_id()

    # Latest balance — mirrors the index route logic in main.py
    balance = Balance.query.filter_by(user_id=user_id).order_by(
        desc(Balance.date), desc(Balance.id)
    ).first()

    try:
        balance_amount = float(balance.amount)
    except (ValueError, TypeError, AttributeError):
        balance_amount = 0.0

    # Fetch user data for projection engine
    schedules = Schedule.query.filter_by(user_id=user_id).all()
    holds = Hold.query.filter_by(user_id=user_id).all()
    skips = Skip.query.filter_by(user_id=user_id).all()
    scenarios = Scenario.query.filter_by(user_id=user_id).all()

    trans, run, run_scenario = update_cash(balance_amount, schedules, holds, skips, scenarios)

    # Risk score
    cash_risk = calculate_cash_risk_score(balance_amount, run)

    # Min balance within 90-day window (same as plot_cash)
    from datetime import timedelta
    todaydate = datetime.today().date()
    horizon_90 = todaydate + timedelta(days=90)
    if not run.empty:
        run_copy = run.copy()
        run_copy['amount'] = run_copy['amount'].astype(float)
        run_90 = run_copy[run_copy['date'] <= horizon_90]
        min_balance = float(run_90['amount'].min()) if not run_90.empty else float(run_copy['amount'].min())
    else:
        min_balance = balance_amount

    # Upcoming transactions (next 90 days) — trans DataFrame from update_cash
    upcoming = []
    if not trans.empty:
        for row in trans.itertuples(index=False):
            upcoming.append({
                "name": row.name,
                "type": row.type,
                "amount": _amount(row.amount),
                "date": _date(row.date),
            })

    balance_date = balance.date if balance else todaydate

    return api_ok({
        "balance": _amount(balance_amount),
        "balance_date": _date(balance_date),
        "risk": cash_risk,
        "upcoming_transactions": upcoming,
        "min_balance": _amount(min_balance),
    })


# ── GET /api/v1/schedules ────────────────────────────────────────────────────

@api.route("/schedules", methods=["GET"])
@api_login_required
def api_schedules():
    """Return all recurring scheduled items for the authenticated user.

    Response 200::

        { "data": [ { "id": 1, "name": "Rent", ... }, ... ], "meta": { "total": N } }
    """
    user_id = _effective_user_id()
    items = Schedule.query.filter_by(user_id=user_id).all()
    return api_list(
        [serialize_schedule(s) for s in items],
        total=len(items),
    )


# ── GET /api/v1/projections ──────────────────────────────────────────────────

@api.route("/projections", methods=["GET"])
@api_login_required
def api_projections():
    """Return running-balance projection data points.

    Returns the schedule-only projection and, if scenarios exist, the
    schedule+scenario projection as well.  Each series is a list of
    ``{ "date": "YYYY-MM-DD", "amount": "1234.56" }`` objects.

    Response 200::

        {
          "data": {
            "schedule": [ {"date": "...", "amount": "..."}, ... ],
            "scenario": [ ... ] | null
          }
        }
    """
    user_id = _effective_user_id()

    balance = Balance.query.filter_by(user_id=user_id).order_by(
        desc(Balance.date), desc(Balance.id)
    ).first()

    try:
        balance_amount = float(balance.amount)
    except (ValueError, TypeError, AttributeError):
        balance_amount = 0.0

    schedules = Schedule.query.filter_by(user_id=user_id).all()
    holds = Hold.query.filter_by(user_id=user_id).all()
    skips = Skip.query.filter_by(user_id=user_id).all()
    scenarios = Scenario.query.filter_by(user_id=user_id).all()

    _trans, run, run_scenario = update_cash(balance_amount, schedules, holds, skips, scenarios)

    def _series(df):
        if df is None or df.empty:
            return None
        points = []
        for row in df.itertuples(index=False):
            points.append({
                "date": _date(row.date),
                "amount": _amount(row.amount),
            })
        return points

    return api_ok({
        "schedule": _series(run) or [],
        "scenario": _series(run_scenario),
    })


# ── GET /api/v1/scenarios ────────────────────────────────────────────────────

@api.route("/scenarios", methods=["GET"])
@api_login_required
def api_scenarios():
    """Return all what-if scenario items for the authenticated user."""
    user_id = _effective_user_id()
    items = Scenario.query.filter_by(user_id=user_id).all()
    return api_list(
        [serialize_scenario(s) for s in items],
        total=len(items),
    )


# ── GET /api/v1/holds ────────────────────────────────────────────────────────

@api.route("/holds", methods=["GET"])
@api_login_required
def api_holds():
    """Return all held (paused) schedule items."""
    user_id = _effective_user_id()
    items = Hold.query.filter_by(user_id=user_id).all()
    return api_list(
        [serialize_hold(h) for h in items],
        total=len(items),
    )


# ── GET /api/v1/skips ────────────────────────────────────────────────────────

@api.route("/skips", methods=["GET"])
@api_login_required
def api_skips():
    """Return all skipped transaction instances."""
    user_id = _effective_user_id()
    items = Skip.query.filter_by(user_id=user_id).all()
    return api_list(
        [serialize_skip(s) for s in items],
        total=len(items),
    )
