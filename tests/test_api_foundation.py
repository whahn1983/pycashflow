"""
Tests for the API v1 foundation.

Covers the four required scenarios from the deliverables:
  1. Success response shape  — ``{"data": ...}``
  2. Error response shape    — ``{"error": ..., "code": ..., "status": ...}``
  3. 404 handling            — unknown /api/ path returns JSON 404
  4. Validation failure      — missing fields returns 422 with ``fields``

Additionally verifies the auth lifecycle:
  - Valid credentials → token + user in response
  - Invalid credentials → 401
  - Token can authenticate /auth/me
  - Session cookie can authenticate /auth/me (existing web-app sessions)
  - Logout invalidates the token
"""

import pytest
from datetime import date
from types import SimpleNamespace

from werkzeug.security import generate_password_hash

# Module-level imports: captured before test_cash_risk_score / test_projection_engine
# install sys.modules stubs that replace app.models with lightweight Mocks.
# conftest.py creates the real Flask app (and real models) before any stubs are
# installed, so these names are bound to the real classes here at collection time.
from app import db as _db
from app.models import UserToken, User
from app.api.serializers import serialize_balance, serialize_user, _amount, _date, _datetime
from app.api.auth_utils import hash_token
import app.api.routes.auth as api_auth_routes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json(resp):
    """Return parsed JSON body; raises on non-JSON response."""
    data = resp.get_json()
    assert data is not None, f"Response is not JSON (status={resp.status_code})"
    return data


def _login(client, email="admin@test.local", password="testpass123"):
    """POST to /api/v1/auth/login and return the raw response."""
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        content_type="application/json",
    )


def _bearer(token: str) -> dict:
    """Build an Authorization header dict for Bearer token requests."""
    return {"Authorization": f"Bearer {token}"}


# ── 1. Success response shape ─────────────────────────────────────────────────


class TestSuccessResponseShape:
    """Every 2xx response from the API must wrap its payload in a ``data`` key."""

    def test_me_via_session_has_data_key(self, auth_client):
        resp = auth_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = _json(resp)
        assert "data" in body, "Successful response must contain a 'data' key"

    def test_me_data_contains_user_fields(self, auth_client):
        body = _json(auth_client.get("/api/v1/auth/me"))
        user = body["data"]
        for field in ("id", "email", "name", "is_admin", "twofa_enabled", "is_guest"):
            assert field in user, f"User object missing expected field '{field}'"

    def test_login_response_wraps_in_data(self, client):
        resp = _login(client)
        assert resp.status_code == 200
        body = _json(resp)
        assert "data" in body
        assert "token" in body["data"]
        assert "user" in body["data"]

    def test_logout_has_data_key(self, client):
        token = _json(_login(client))["data"]["token"]
        resp = client.post("/api/v1/auth/logout", headers=_bearer(token))
        assert resp.status_code == 200
        body = _json(resp)
        assert "data" in body


# ── 2. Error response shape ───────────────────────────────────────────────────


class TestErrorResponseShape:
    """Every error response must contain ``error``, ``code``, and ``status``."""

    def _assert_error_shape(self, resp, expected_status: int, expected_code: str):
        assert resp.status_code == expected_status
        body = _json(resp)
        assert "error" in body, "Error response must have an 'error' key"
        assert "code" in body, "Error response must have a 'code' key"
        assert "status" in body, "Error response must have a 'status' key"
        assert body["code"] == expected_code, (
            f"Expected code={expected_code!r}, got {body['code']!r}"
        )
        assert body["status"] == expected_status, (
            f"Expected status={expected_status}, got {body['status']}"
        )

    def test_unauthenticated_me_returns_401(self, client):
        resp = client.get("/api/v1/auth/me")
        self._assert_error_shape(resp, 401, "unauthorized")

    def test_invalid_credentials_returns_401(self, client):
        resp = _login(client, password="totally-wrong")
        self._assert_error_shape(resp, 401, "unauthorized")

    def test_inactive_account_returns_401(self, flask_app, client):
        """An existing but inactive user should be rejected."""
        with flask_app.app_context():
            inactive = User(
                email="inactive@test.local",
                password=generate_password_hash("pass123", method="scrypt"),
                name="Inactive",
                admin=False,
                is_active=False,
            )
            _db.session.add(inactive)
            _db.session.commit()

        resp = _login(client, email="inactive@test.local", password="pass123")
        self._assert_error_shape(resp, 401, "unauthorized")

        # Clean up
        with flask_app.app_context():
            User.query.filter_by(email="inactive@test.local").delete()
            _db.session.commit()

    def test_expired_token_returns_401(self, flask_app, client):
        """A token past its expiry date must be rejected."""
        from datetime import datetime, timedelta, timezone

        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            expired = UserToken(
                user_id=user.id,
                token_hash=hash_token("expired-raw-token-value"),
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            _db.session.add(expired)
            _db.session.commit()

        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer expired-raw-token-value"},
        )
        self._assert_error_shape(resp, 401, "unauthorized")

        with flask_app.app_context():
            UserToken.query.filter_by(
                token_hash=hash_token("expired-raw-token-value")
            ).delete()
            _db.session.commit()


# ── 3. 404 handling ───────────────────────────────────────────────────────────


class TestNotFoundHandling:
    """Unknown /api/ paths must return JSON 404, not an HTML page."""

    def test_unknown_api_path_returns_404_json(self, client):
        resp = client.get("/api/v1/does-not-exist")
        assert resp.status_code == 404
        assert resp.content_type.startswith("application/json")
        body = _json(resp)
        assert body["code"] == "not_found"
        assert body["status"] == 404

    def test_404_response_has_all_error_keys(self, client):
        resp = client.get("/api/v1/nonexistent/resource/123")
        body = _json(resp)
        for key in ("error", "code", "status"):
            assert key in body, f"404 response must include '{key}'"

    def test_existing_web_route_not_intercepted(self, auth_client):
        """The /api 404 handler must not break the server-rendered web app."""
        resp = auth_client.get("/schedule", follow_redirects=True)
        assert resp.status_code == 200
        # Content should be HTML, not JSON
        assert "text/html" in resp.content_type


# ── 4. Validation failure handling ────────────────────────────────────────────


class TestValidationFailureHandling:
    """Endpoints that receive incomplete input must return 422 with a ``fields`` map."""

    def test_missing_both_fields_returns_422(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = _json(resp)
        assert body["code"] == "validation_error"
        assert "fields" in body
        assert "email" in body["fields"]
        assert "password" in body["fields"]

    def test_missing_email_only(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"password": "somepass"},
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = _json(resp)
        assert "email" in body["fields"]
        assert "password" not in body["fields"]

    def test_missing_password_only(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com"},
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = _json(resp)
        assert "password" in body["fields"]
        assert "email" not in body["fields"]

    def test_blank_email_treated_as_missing(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "   ", "password": "pass"},
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = _json(resp)
        assert "email" in body["fields"]

    def test_non_json_body_returns_422(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            data="not json at all",
            content_type="text/plain",
        )
        assert resp.status_code == 422


# ── Auth lifecycle ────────────────────────────────────────────────────────────


class TestAuthLifecycle:
    """End-to-end token issuance, use, and revocation."""

    def test_valid_login_creates_token_in_db(self, flask_app, client):
        resp = _login(client)
        assert resp.status_code == 200
        raw_token = _json(resp)["data"]["token"]

        with flask_app.app_context():
            record = UserToken.query.filter_by(token_hash=hash_token(raw_token)).first()
            assert record is not None, "Token record must be persisted in the database"

    def test_bearer_token_authenticates_me(self, client):
        raw_token = _json(_login(client))["data"]["token"]
        resp = client.get("/api/v1/auth/me", headers=_bearer(raw_token))
        assert resp.status_code == 200
        assert _json(resp)["data"]["email"] == "admin@test.local"

    def test_me_user_fields_match_logged_in_user(self, client):
        raw_token = _json(_login(client))["data"]["token"]
        body = _json(client.get("/api/v1/auth/me", headers=_bearer(raw_token)))
        user = body["data"]
        assert user["email"] == "admin@test.local"
        assert user["name"] == "Test Admin"
        assert user["is_admin"] is True
        assert user["is_guest"] is False

    def test_session_auth_works_on_me(self, auth_client):
        """Existing Flask-Login sessions (web app) can reach /auth/me."""
        resp = auth_client.get("/api/v1/auth/me")
        assert resp.status_code == 200

    def test_logout_removes_token_from_db(self, flask_app, client):
        raw_token = _json(_login(client))["data"]["token"]

        # Token should be in the DB
        with flask_app.app_context():
            assert UserToken.query.filter_by(token_hash=hash_token(raw_token)).first()

        # Logout
        resp = client.post("/api/v1/auth/logout", headers=_bearer(raw_token))
        assert resp.status_code == 200

        # Token should be gone
        with flask_app.app_context():
            assert UserToken.query.filter_by(token_hash=hash_token(raw_token)).first() is None

    def test_revoked_token_is_rejected(self, client):
        raw_token = _json(_login(client))["data"]["token"]
        client.post("/api/v1/auth/logout", headers=_bearer(raw_token))

        # Attempt to use the revoked token
        resp = client.get("/api/v1/auth/me", headers=_bearer(raw_token))
        assert resp.status_code == 401

    def test_unknown_token_returns_401(self, client):
        resp = client.get("/api/v1/auth/me", headers=_bearer("totally-fake-token"))
        assert resp.status_code == 401


# ── Serializer unit tests ─────────────────────────────────────────────────────


class TestSerializers:
    """Verify serialization helpers produce correct types and formats."""

    def test_serialize_user_excludes_password(self, flask_app):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            data = serialize_user(user)

        assert "password" not in data
        assert "twofa_secret" not in data
        assert "twofa_backup_codes" not in data

    def test_serialize_balance_amount_is_string(self):
        # Use SimpleNamespace — serialize_balance only accesses .id/.amount/.date,
        # so we don't need a real SQLAlchemy model instance.
        bal = SimpleNamespace(id=1, amount="5000.00", date=date.today())
        data = serialize_balance(bal)

        # Amount must be a string to avoid floating-point issues
        assert isinstance(data["amount"], str)
        # Must have exactly 2 decimal places
        parts = data["amount"].split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 2

    def test_serialize_balance_date_is_iso_string(self):
        bal = SimpleNamespace(id=2, amount="100.00", date=date(2026, 1, 15))
        data = serialize_balance(bal)
        assert data["date"] == "2026-01-15"

    def test_amount_helper_two_decimal_places(self):
        from decimal import Decimal

        assert _amount(Decimal("1000")) == "1000.00"
        assert _amount(Decimal("9.9")) == "9.90"
        assert _amount(None) is None

    def test_date_helper_formats_correctly(self):
        from datetime import datetime

        assert _date(date(2026, 3, 5)) == "2026-03-05"
        assert _date(datetime(2026, 3, 5, 12, 0, 0)) == "2026-03-05"
        assert _date(None) is None

    def test_datetime_helper_formats_utc(self):
        from datetime import datetime, timezone

        dt = datetime(2026, 4, 9, 14, 30, 0, tzinfo=timezone.utc)
        assert _datetime(dt) == "2026-04-09T14:30:00Z"
        assert _datetime(None) is None


class TestAuthEnhancements:
    def test_twofa_challenge_mark_consumed_is_single_use(self):
        challenge = "challenge-token"
        with api_auth_routes._CONSUMED_TWOFA_CHALLENGES_LOCK:
            api_auth_routes._CONSUMED_TWOFA_CHALLENGES.clear()

        assert api_auth_routes._try_mark_twofa_challenge_consumed(challenge) is True
        assert api_auth_routes._try_mark_twofa_challenge_consumed(challenge) is False

    def test_login_twofa_required_returns_challenge(self, flask_app, client):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            user.twofa_enabled = True
            _db.session.commit()

        resp = _login(client)
        assert resp.status_code == 200
        body = _json(resp)["data"]
        assert body["twofa_required"] is True
        assert "challenge" in body
        assert "token" not in body

        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            user.twofa_enabled = False
            _db.session.commit()

    def test_refresh_rotates_token(self, client):
        old_token = _json(_login(client))["data"]["token"]
        resp = client.post("/api/v1/auth/refresh", headers=_bearer(old_token))
        assert resp.status_code == 200
        new_token = _json(resp)["data"]["token"]
        assert new_token != old_token

        denied = client.get("/api/v1/auth/me", headers=_bearer(old_token))
        assert denied.status_code == 401

        ok = client.get("/api/v1/auth/me", headers=_bearer(new_token))
        assert ok.status_code == 200

    def test_refresh_requires_bearer_even_with_session(self, auth_client):
        resp = auth_client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
        assert _json(resp)["code"] == "unauthorized"

    def test_logout_requires_bearer_even_with_session(self, auth_client):
        resp = auth_client.post("/api/v1/auth/logout")
        assert resp.status_code == 401
        assert _json(resp)["code"] == "unauthorized"

    def test_twofa_challenge_cannot_be_reused(self, flask_app, client, monkeypatch):
        with flask_app.app_context():
            user = User.query.filter_by(email="admin@test.local").first()
            user.twofa_enabled = True
            user.twofa_secret = "encrypted"
            _db.session.commit()

        try:
            monkeypatch.setattr(api_auth_routes, "verify_totp", lambda _secret, _code: True)
            monkeypatch.setattr(api_auth_routes, "decrypt_totp_secret", lambda _encrypted: "secret")

            login_resp = _login(client)
            assert login_resp.status_code == 200
            challenge = _json(login_resp)["data"]["challenge"]

            first = client.post("/api/v1/auth/login/2fa", json={"challenge": challenge, "code": "123456"})
            assert first.status_code == 200

            second = client.post("/api/v1/auth/login/2fa", json={"challenge": challenge, "code": "123456"})
            assert second.status_code == 401
        finally:
            with flask_app.app_context():
                user = User.query.filter_by(email="admin@test.local").first()
                user.twofa_enabled = False
                user.twofa_secret = None
                _db.session.commit()

    def test_login_2fa_validation_rejects_non_string_fields(self, client):
        resp = client.post("/api/v1/auth/login/2fa", json={"challenge": 123, "code": 456})
        assert resp.status_code == 422
        body = _json(resp)
        assert body["code"] == "validation_error"
        assert "challenge" in body["fields"]
        assert "code" in body["fields"]

    def test_change_password(self, client):
        token = _json(_login(client))["data"]["token"]
        resp = client.put(
            "/api/v1/auth/password",
            headers=_bearer(token),
            json={"current_password": "testpass123", "new_password": "newpass1234"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        old_login = _login(client, password="testpass123")
        assert old_login.status_code == 401
        new_login = _login(client, password="newpass1234")
        assert new_login.status_code == 200
        new_token = _json(new_login)["data"]["token"]
        revert = client.put(
            "/api/v1/auth/password",
            headers=_bearer(new_token),
            json={"current_password": "newpass1234", "new_password": "testpass123"},
            content_type="application/json",
        )
        assert revert.status_code == 200

    def test_change_password_revokes_all_existing_tokens(self, client):
        token_a = _json(_login(client))["data"]["token"]
        token_b = _json(_login(client))["data"]["token"]

        change = client.put(
            "/api/v1/auth/password",
            headers=_bearer(token_a),
            json={"current_password": "testpass123", "new_password": "newpass1234"},
            content_type="application/json",
        )
        assert change.status_code == 200

        revoked = client.get("/api/v1/auth/me", headers=_bearer(token_b))
        assert revoked.status_code == 401

        new_login = _login(client, password="newpass1234")
        assert new_login.status_code == 200
        rotate_token = _json(new_login)["data"]["token"]
        revert = client.put(
            "/api/v1/auth/password",
            headers=_bearer(rotate_token),
            json={"current_password": "newpass1234", "new_password": "testpass123"},
            content_type="application/json",
        )
        assert revert.status_code == 200
