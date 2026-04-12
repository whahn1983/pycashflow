"""
Flask route integration tests.

Uses the real Flask test app created eagerly in conftest.py (with an
in-memory SQLite database) to exercise the most important HTTP routes.

Goals:
  - Verify that authenticated users reach each page successfully.
  - Verify that unauthenticated requests are redirected to login.
  - Verify that form validation rejects bad input without crashing.
  - Confirm key POST routes (create, balance, create_scenario) behave correctly.

We deliberately avoid inspecting HTML structure or CSS; tests only check HTTP
status codes, redirects, and flash messages where they are easy to assert.
"""

import pytest
import importlib
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash



# ── Helpers ───────────────────────────────────────────────────────────────────

def _flashed(response_data: bytes, keyword: str) -> bool:
    """Return True if `keyword` appears in the response bytes (case-insensitive)."""
    return keyword.lower().encode() in response_data.lower()


# ── Tests: unauthenticated access ─────────────────────────────────────────────


class TestUnauthenticatedAccess:
    """All protected routes must redirect unauthenticated visitors to login."""

    @pytest.mark.parametrize(
        "path",
        ["/", "/schedule", "/scenarios", "/settings", "/holds"],
    )
    def test_protected_get_redirects_to_login(self, client, path):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302), (
            f"GET {path} should redirect unauthenticated user, got {resp.status_code}"
        )
        location = resp.headers.get("Location", "")
        assert "login" in location.lower(), (
            f"GET {path} should redirect to login page, got location: {location}"
        )


# ── Tests: authenticated GET routes ──────────────────────────────────────────


class TestAuthenticatedGetRoutes:
    """Authenticated admin users should receive a 200 for all primary pages."""

    def test_index_returns_200(self, auth_client):
        resp = auth_client.get("/", follow_redirects=True)
        assert resp.status_code == 200

    def test_schedule_page_returns_200(self, auth_client):
        resp = auth_client.get("/schedule", follow_redirects=True)
        assert resp.status_code == 200

    def test_scenarios_page_returns_200(self, auth_client):
        resp = auth_client.get("/scenarios", follow_redirects=True)
        assert resp.status_code == 200

    def test_settings_page_returns_200(self, auth_client):
        resp = auth_client.get("/settings", follow_redirects=True)
        assert resp.status_code == 200

    def test_holds_page_returns_200(self, auth_client):
        resp = auth_client.get("/holds", follow_redirects=True)
        assert resp.status_code == 200

    def test_refresh_redirects_to_index(self, auth_client):
        resp = auth_client.get("/refresh", follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert "/" in resp.headers.get("Location", "")


class TestSignupLinkBehavior:
    def test_login_create_account_defaults_to_builtin_signup(self, client):
        resp = client.get("/login", follow_redirects=True)
        assert resp.status_code == 200
        assert b'href="/signup"' in resp.data

    def test_login_create_account_uses_external_signup_url(self, client, app_ctx, text_settings_model):
        db = app_ctx
        text_settings_model.query.filter_by(name="external_signup_url").delete()
        db.session.add(
            text_settings_model(name="external_signup_url", value="https://example.com/app-signup")
        )
        db.session.commit()

        resp = client.get("/login", follow_redirects=True)
        assert resp.status_code == 200
        assert b'href="https://example.com/app-signup"' in resp.data

        text_settings_model.query.filter_by(name="external_signup_url").delete()
        db.session.commit()

    def test_signup_route_redirects_to_external_url_when_configured(self, client, app_ctx, text_settings_model):
        db = app_ctx
        text_settings_model.query.filter_by(name="external_signup_url").delete()
        db.session.add(
            text_settings_model(name="external_signup_url", value="https://example.com/app-signup")
        )
        db.session.commit()

        resp = client.get("/signup", follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert resp.headers.get("Location") == "https://example.com/app-signup"

        text_settings_model.query.filter_by(name="external_signup_url").delete()
        db.session.commit()

    def test_signups_post_rejects_invalid_external_signup_url(
        self, auth_client, app_ctx, user_model, settings_model, text_settings_model
    ):
        db = app_ctx
        admin = user_model.query.filter_by(email="admin@test.local").first()
        admin.is_global_admin = True
        db.session.commit()

        settings_model.query.filter_by(name="signup").delete()
        text_settings_model.query.filter_by(name="external_signup_url").delete()
        db.session.commit()

        resp = auth_client.post(
            "/signups",
            data={"signupvalue": "False", "external_signup_url": "javascript:alert(1)"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert _flashed(resp.data, "valid http")
        assert text_settings_model.query.filter_by(name="external_signup_url").first() is None


# ── Tests: schedule creation (POST /create) ───────────────────────────────────


class TestCreateSchedule:
    """POST /create validates input and creates schedule entries."""

    def _post_create(self, auth_client, **overrides):
        """Submit a valid create form, optionally overriding specific fields."""
        data = {
            "name": "TestSalary",
            "amount": "3000",
            "type": "Income",
            "frequency": "Monthly",
            "startdate": "2099-01-01",
        }
        data.update(overrides)
        return auth_client.post("/create", data=data, follow_redirects=True)

    def test_valid_schedule_creation_returns_200(self, auth_client):
        resp = self._post_create(auth_client, name="SalaryRouteTest1")
        assert resp.status_code == 200

    def test_valid_creation_shows_success_flash(self, auth_client):
        resp = self._post_create(auth_client, name="SalaryRouteTest2")
        assert _flashed(resp.data, "added") or _flashed(resp.data, "success")

    def test_empty_name_shows_error_flash(self, auth_client):
        resp = self._post_create(auth_client, name="")
        assert resp.status_code == 200
        assert _flashed(resp.data, "name") or _flashed(resp.data, "character")

    def test_non_numeric_amount_shows_error_flash(self, auth_client):
        resp = self._post_create(auth_client, amount="notanumber")
        assert resp.status_code == 200
        assert _flashed(resp.data, "amount") or _flashed(resp.data, "number")

    def test_invalid_type_shows_error_flash(self, auth_client):
        resp = self._post_create(auth_client, type="Payment")
        assert resp.status_code == 200
        assert _flashed(resp.data, "invalid") or _flashed(resp.data, "type")

    def test_invalid_frequency_shows_error_flash(self, auth_client):
        resp = self._post_create(auth_client, frequency="Fortnightly")
        assert resp.status_code == 200
        assert _flashed(resp.data, "invalid") or _flashed(resp.data, "frequency")

    def test_duplicate_schedule_shows_already_exists_flash(self, auth_client):
        name = "DuplicateScheduleTest"
        # Create it once
        self._post_create(auth_client, name=name)
        # Try to create it again
        resp = self._post_create(auth_client, name=name)
        assert resp.status_code == 200
        assert _flashed(resp.data, "exists") or _flashed(resp.data, "already")


# ── Tests: balance update (POST /balance) ─────────────────────────────────────


class TestBalanceUpdate:
    def test_valid_balance_update_redirects(self, auth_client):
        resp = auth_client.post(
            "/balance",
            data={"amount": "7500.00", "date": "2099-01-01"},
            follow_redirects=False,
        )
        # Should redirect back to the dashboard
        assert resp.status_code in (301, 302)


# ── Tests: scenario creation (POST /create_scenario) ─────────────────────────


class TestCreateScenario:
    def _post_create_scenario(self, auth_client, **overrides):
        data = {
            "name": "TestScenario",
            "amount": "2000",
            "type": "Income",
            "frequency": "Monthly",
            "startdate": "2099-06-01",
        }
        data.update(overrides)
        return auth_client.post("/create_scenario", data=data, follow_redirects=True)

    def test_valid_scenario_creation_returns_200(self, auth_client):
        resp = self._post_create_scenario(auth_client, name="ScenarioRouteTest1")
        assert resp.status_code == 200

    def test_valid_scenario_shows_success_flash(self, auth_client):
        resp = self._post_create_scenario(auth_client, name="ScenarioRouteTest2")
        assert _flashed(resp.data, "added") or _flashed(resp.data, "success")

    def test_empty_scenario_name_shows_error(self, auth_client):
        resp = self._post_create_scenario(auth_client, name="")
        assert resp.status_code == 200
        assert _flashed(resp.data, "name") or _flashed(resp.data, "character")

    def test_invalid_scenario_type_shows_error(self, auth_client):
        resp = self._post_create_scenario(auth_client, type="Transfer")
        assert resp.status_code == 200
        assert _flashed(resp.data, "invalid") or _flashed(resp.data, "type")


def test_delete_user_removes_passkey_credentials(
    auth_client, app_ctx, user_model, passkey_credential_model
):
    db = app_ctx
    owner = user_model.query.filter_by(email="admin@test.local").first()
    if owner is None:
        owner = user_model(
            email="admin@test.local",
            password=generate_password_hash("testpass123", method="scrypt"),
            name="Test Admin",
            admin=True,
            is_active=True,
            account_owner_id=None,
            is_global_admin=False,
        )
        db.session.add(owner)
        db.session.flush()

    guest = user_model(
        email="guest-passkey-delete@test.local",
        password=generate_password_hash("testpass123", method="scrypt"),
        name="Guest To Delete",
        admin=False,
        is_active=True,
        account_owner_id=owner.id,
        is_global_admin=False,
    )
    db.session.add(guest)
    db.session.flush()

    credential = passkey_credential_model(
        user_id=guest.id,
        credential_id="guest-credential-to-delete",
        public_key="pk",
        sign_count=0,
        label="Guest Key",
    )
    db.session.add(credential)
    db.session.commit()

    resp = auth_client.post(f"/delete_user/{guest.id}", follow_redirects=False)

    assert resp.status_code in (301, 302)
    assert user_model.query.filter_by(id=guest.id).first() is None
    assert passkey_credential_model.query.filter_by(
        credential_id="guest-credential-to-delete"
    ).first() is None


def test_delete_owner_removes_guest_password_setup_tokens(
    auth_client, app_ctx, user_model, password_setup_token_model
):
    db = app_ctx
    acting_admin = user_model.query.filter_by(email="admin@test.local").first()
    acting_admin.is_global_admin = True
    db.session.flush()

    owner = user_model(
        email="owner-delete@test.local",
        password=generate_password_hash("testpass123", method="scrypt"),
        name="Owner To Delete",
        admin=True,
        is_active=True,
        account_owner_id=None,
        is_global_admin=False,
    )
    db.session.add(owner)
    db.session.flush()

    guest = user_model(
        email="guest-owner-delete@test.local",
        password=generate_password_hash("testpass123", method="scrypt"),
        name="Guest Of Owner To Delete",
        admin=False,
        is_active=True,
        account_owner_id=owner.id,
        is_global_admin=False,
    )
    db.session.add(guest)
    db.session.flush()

    guest_id = guest.id
    token = password_setup_token_model(
        user_id=guest.id,
        token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc),
    )
    db.session.add(token)
    db.session.commit()
    token_id = token.id

    resp = auth_client.post(f"/delete_user/{owner.id}", follow_redirects=False)

    assert resp.status_code in (301, 302)
    assert user_model.query.filter_by(id=owner.id).first() is None
    assert user_model.query.filter_by(id=guest_id).first() is None
    assert password_setup_token_model.query.filter_by(id=token_id).first() is None


class TestGuestOnboarding:
    def test_add_guest_sends_password_setup_email(
        self, auth_client, flask_app, app_ctx, user_model, password_setup_token_model, monkeypatch
    ):
        monkeypatch.setitem(flask_app.config, "FRONTEND_BASE_URL", "https://app.example.com/")
        sent = {}

        def _fake_send_password_setup_email(user_name, user_email, setup_url, expires_minutes):
            sent["user_name"] = user_name
            sent["user_email"] = user_email
            sent["setup_url"] = setup_url
            sent["expires_minutes"] = expires_minutes
            return True

        main_module = importlib.import_module("app.main")
        monkeypatch.setattr(main_module, "send_password_setup_email", _fake_send_password_setup_email)
        resp = auth_client.post(
            "/add_guest",
            data={"name": "Guest Invite", "email": "guest-invite@test.local"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert _flashed(resp.data, "password setup email was sent")
        assert sent["user_name"] == "Guest Invite"
        assert sent["user_email"] == "guest-invite@test.local"
        assert sent["setup_url"].startswith("https://app.example.com/auth/set-password/")
        assert isinstance(sent["expires_minutes"], int)

        guest = user_model.query.filter_by(email="guest-invite@test.local").first()
        assert guest is not None
        assert guest.account_owner_id is not None

        app_ctx.session.query(password_setup_token_model).filter_by(user_id=guest.id).delete()
        app_ctx.session.delete(guest)
        app_ctx.session.commit()

    def test_add_guest_requires_frontend_base_url(
        self, auth_client, flask_app, app_ctx, user_model, monkeypatch
    ):
        monkeypatch.setitem(flask_app.config, "FRONTEND_BASE_URL", "")
        resp = auth_client.post(
            "/add_guest",
            data={"name": "No Frontend", "email": "guest-no-front@test.local"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert _flashed(resp.data, "frontend_base_url must be configured")
        assert user_model.query.filter_by(email="guest-no-front@test.local").first() is None
