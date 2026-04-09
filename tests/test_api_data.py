"""
Tests for API v1 data endpoints (mobile-facing read routes).

Covers:
  - Authentication required (401 without token)
  - Dashboard returns balance, risk, upcoming_transactions, min_balance
  - Schedules list endpoint
  - Projections endpoint returns schedule (and scenario) series
  - Scenarios, holds, skips list endpoints
  - Response shapes follow API conventions (data key, meta key for lists)
"""

import pytest
from datetime import date, timedelta, datetime

from werkzeug.security import generate_password_hash

# Module-level imports: captured before test stubs can replace sys.modules.
from app import db as _db
from app.models import User, Schedule, Scenario, Balance, Hold, Skip


# ── Helpers ──────────────────────────────────────────────────────────────────

def _json(resp):
    """Return parsed JSON body; raises on non-JSON response."""
    data = resp.get_json()
    assert data is not None, f"Response is not JSON (status={resp.status_code})"
    return data


def _login(client, email="admin@test.local", password="testpass123"):
    """POST to /api/v1/auth/login and return the raw token string."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        content_type="application/json",
    )
    return _json(resp)["data"]["token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Auth required on all data endpoints ──────────────────────────────────────


class TestDataEndpointsRequireAuth:
    """All data endpoints must return 401 without a valid token."""

    @pytest.mark.parametrize("path", [
        "/api/v1/dashboard",
        "/api/v1/schedules",
        "/api/v1/projections",
        "/api/v1/scenarios",
        "/api/v1/holds",
        "/api/v1/skips",
    ])
    def test_unauthenticated_returns_401(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 401
        body = _json(resp)
        assert body["code"] == "unauthorized"


# ── Dashboard endpoint ───────────────────────────────────────────────────────


class TestDashboard:
    """GET /api/v1/dashboard returns a mobile-friendly summary."""

    def test_dashboard_returns_200(self, client):
        token = _login(client)
        resp = client.get("/api/v1/dashboard", headers=_bearer(token))
        assert resp.status_code == 200

    def test_dashboard_has_data_key(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/dashboard", headers=_bearer(token)))
        assert "data" in body

    def test_dashboard_contains_balance(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/dashboard", headers=_bearer(token)))
        data = body["data"]
        assert "balance" in data
        assert "balance_date" in data
        # Balance should be a string (decimal format)
        assert isinstance(data["balance"], str)
        assert "." in data["balance"]

    def test_dashboard_contains_risk(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/dashboard", headers=_bearer(token)))
        risk = body["data"]["risk"]
        assert "score" in risk
        assert "status" in risk
        assert "color" in risk
        assert isinstance(risk["score"], int)

    def test_dashboard_contains_upcoming_transactions(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/dashboard", headers=_bearer(token)))
        data = body["data"]
        assert "upcoming_transactions" in data
        assert isinstance(data["upcoming_transactions"], list)

    def test_dashboard_contains_min_balance(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/dashboard", headers=_bearer(token)))
        data = body["data"]
        assert "min_balance" in data
        assert isinstance(data["min_balance"], str)

    def test_dashboard_via_session_auth(self, auth_client):
        """Session-authenticated requests should also work."""
        resp = auth_client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        body = _json(resp)
        assert "data" in body
        assert "balance" in body["data"]

    def test_dashboard_with_schedule(self, flask_app, client):
        """Dashboard reflects scheduled items in projections."""
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            future = date.today() + timedelta(days=7)
            sched = Schedule(
                user_id=user.id,
                name="_test_rent_dash",
                amount="1500.00",
                frequency="Monthly",
                startdate=future,
                firstdate=future,
                type="Expense",
            )
            _db.session.add(sched)
            _db.session.commit()

        token = _login(client)
        body = _json(client.get("/api/v1/dashboard", headers=_bearer(token)))
        data = body["data"]

        # With an expense scheduled, min_balance should be less than current balance
        assert float(data["min_balance"]) <= float(data["balance"])

        # Clean up
        with flask_app.app_context():
            Schedule.query.filter_by(name="_test_rent_dash").delete()
            _db.session.commit()


# ── Schedules endpoint ───────────────────────────────────────────────────────


class TestSchedules:
    """GET /api/v1/schedules returns the user's recurring items."""

    def test_schedules_returns_200(self, client):
        token = _login(client)
        resp = client.get("/api/v1/schedules", headers=_bearer(token))
        assert resp.status_code == 200

    def test_schedules_response_shape(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/schedules", headers=_bearer(token)))
        assert "data" in body
        assert isinstance(body["data"], list)
        assert "meta" in body
        assert "total" in body["meta"]

    def test_schedules_reflects_created_item(self, flask_app, client):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            future = date.today() + timedelta(days=14)
            sched = Schedule(
                user_id=user.id,
                name="_test_api_salary",
                amount="3000.00",
                frequency="Monthly",
                startdate=future,
                firstdate=future,
                type="Income",
            )
            _db.session.add(sched)
            _db.session.commit()

        token = _login(client)
        body = _json(client.get("/api/v1/schedules", headers=_bearer(token)))
        names = [s["name"] for s in body["data"]]
        assert "_test_api_salary" in names

        # Verify serialization fields
        item = next(s for s in body["data"] if s["name"] == "_test_api_salary")
        assert item["amount"] == "3000.00"
        assert item["type"] == "Income"
        assert item["frequency"] == "Monthly"
        assert "id" in item
        assert "start_date" in item
        assert "first_date" in item

        # Clean up
        with flask_app.app_context():
            Schedule.query.filter_by(name="_test_api_salary").delete()
            _db.session.commit()


# ── Projections endpoint ─────────────────────────────────────────────────────


class TestProjections:
    """GET /api/v1/projections returns running-balance data points."""

    def test_projections_returns_200(self, client):
        token = _login(client)
        resp = client.get("/api/v1/projections", headers=_bearer(token))
        assert resp.status_code == 200

    def test_projections_response_shape(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/projections", headers=_bearer(token)))
        data = body["data"]
        assert "schedule" in data
        assert isinstance(data["schedule"], list)
        # scenario is null when no scenarios exist
        assert "scenario" in data

    def test_projections_schedule_has_data_points(self, client):
        """Even with no schedules, there should be at least the starting balance point."""
        token = _login(client)
        body = _json(client.get("/api/v1/projections", headers=_bearer(token)))
        schedule = body["data"]["schedule"]
        assert len(schedule) >= 1
        # Each point has date and amount
        point = schedule[0]
        assert "date" in point
        assert "amount" in point

    def test_projections_with_scenario(self, flask_app, client):
        """When scenarios exist, the scenario series should be returned."""
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            future = date.today() + timedelta(days=10)
            scenario = Scenario(
                user_id=user.id,
                name="_test_api_scenario",
                amount="500.00",
                frequency="Monthly",
                startdate=future,
                firstdate=future,
                type="Expense",
            )
            _db.session.add(scenario)
            _db.session.commit()

        token = _login(client)
        body = _json(client.get("/api/v1/projections", headers=_bearer(token)))
        assert body["data"]["scenario"] is not None
        assert isinstance(body["data"]["scenario"], list)

        # Clean up
        with flask_app.app_context():
            Scenario.query.filter_by(name="_test_api_scenario").delete()
            _db.session.commit()


# ── Scenarios endpoint ───────────────────────────────────────────────────────


class TestScenarios:
    """GET /api/v1/scenarios returns what-if items."""

    def test_scenarios_returns_200(self, client):
        token = _login(client)
        resp = client.get("/api/v1/scenarios", headers=_bearer(token))
        assert resp.status_code == 200

    def test_scenarios_response_shape(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/scenarios", headers=_bearer(token)))
        assert "data" in body
        assert isinstance(body["data"], list)
        assert "meta" in body
        assert "total" in body["meta"]

    def test_scenarios_reflects_created_item(self, flask_app, client):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            future = date.today() + timedelta(days=30)
            scenario = Scenario(
                user_id=user.id,
                name="_test_api_whatif",
                amount="200.00",
                frequency="Onetime",
                startdate=future,
                firstdate=future,
                type="Expense",
            )
            _db.session.add(scenario)
            _db.session.commit()

        token = _login(client)
        body = _json(client.get("/api/v1/scenarios", headers=_bearer(token)))
        names = [s["name"] for s in body["data"]]
        assert "_test_api_whatif" in names

        # Clean up
        with flask_app.app_context():
            Scenario.query.filter_by(name="_test_api_whatif").delete()
            _db.session.commit()


# ── Holds endpoint ───────────────────────────────────────────────────────────


class TestHolds:
    """GET /api/v1/holds returns paused schedule items."""

    def test_holds_returns_200(self, client):
        token = _login(client)
        resp = client.get("/api/v1/holds", headers=_bearer(token))
        assert resp.status_code == 200

    def test_holds_response_shape(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/holds", headers=_bearer(token)))
        assert "data" in body
        assert isinstance(body["data"], list)
        assert "meta" in body

    def test_holds_reflects_created_item(self, flask_app, client):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            hold = Hold(
                user_id=user.id,
                name="_test_api_hold",
                amount="100.00",
                type="Expense",
            )
            _db.session.add(hold)
            _db.session.commit()

        token = _login(client)
        body = _json(client.get("/api/v1/holds", headers=_bearer(token)))
        names = [h["name"] for h in body["data"]]
        assert "_test_api_hold" in names

        item = next(h for h in body["data"] if h["name"] == "_test_api_hold")
        assert item["amount"] == "100.00"
        assert item["type"] == "Expense"

        # Clean up
        with flask_app.app_context():
            Hold.query.filter_by(name="_test_api_hold").delete()
            _db.session.commit()


# ── Skips endpoint ───────────────────────────────────────────────────────────


class TestSkips:
    """GET /api/v1/skips returns skipped transaction instances."""

    def test_skips_returns_200(self, client):
        token = _login(client)
        resp = client.get("/api/v1/skips", headers=_bearer(token))
        assert resp.status_code == 200

    def test_skips_response_shape(self, client):
        token = _login(client)
        body = _json(client.get("/api/v1/skips", headers=_bearer(token)))
        assert "data" in body
        assert isinstance(body["data"], list)
        assert "meta" in body

    def test_skips_reflects_created_item(self, flask_app, client):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            future = date.today() + timedelta(days=20)
            skip = Skip(
                user_id=user.id,
                name="_test_api_skip",
                date=future,
                amount="75.00",
                type="Expense",
            )
            _db.session.add(skip)
            _db.session.commit()

        token = _login(client)
        body = _json(client.get("/api/v1/skips", headers=_bearer(token)))
        names = [s["name"] for s in body["data"]]
        assert "_test_api_skip" in names

        item = next(s for s in body["data"] if s["name"] == "_test_api_skip")
        assert item["amount"] == "75.00"
        assert "date" in item

        # Clean up
        with flask_app.app_context():
            Skip.query.filter_by(name="_test_api_skip").delete()
            _db.session.commit()


# ── Guest user data isolation ────────────────────────────────────────────────


class TestGuestUserDataAccess:
    """Guest users should see their account owner's data, not their own."""

    def test_guest_sees_owner_schedules(self, flask_app, client):
        with flask_app.app_context():
            owner = User.query.filter_by(email="admin@test.local").first()

            # Create a guest user linked to the admin
            guest = User(
                email="_guest_api@test.local",
                password=generate_password_hash("guestpass", method="scrypt"),
                name="API Guest",
                admin=False,
                is_active=True,
                account_owner_id=owner.id,
            )
            _db.session.add(guest)
            _db.session.commit()

            # Create a schedule owned by the admin
            future = date.today() + timedelta(days=5)
            sched = Schedule(
                user_id=owner.id,
                name="_test_owner_sched",
                amount="2000.00",
                frequency="Monthly",
                startdate=future,
                firstdate=future,
                type="Income",
            )
            _db.session.add(sched)
            _db.session.commit()

        # Login as guest
        token = _login(client, email="_guest_api@test.local", password="guestpass")
        body = _json(client.get("/api/v1/schedules", headers=_bearer(token)))
        names = [s["name"] for s in body["data"]]
        assert "_test_owner_sched" in names

        # Clean up
        with flask_app.app_context():
            Schedule.query.filter_by(name="_test_owner_sched").delete()
            User.query.filter_by(email="_guest_api@test.local").delete()
            _db.session.commit()
