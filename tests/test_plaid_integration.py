"""Tests for the Plaid Balance integration.

Covers the configuration gate, model invariants (one active connection per
user), exchange-token guards, balance-update precedence (available vs
current), dashboard integration safety, and that no transaction/raw-payload
storage paths exist.

All Plaid SDK interactions are mocked; tests never hit the network.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

# Other test modules (test_cash_risk_score, test_projection_engine) install
# sys.modules stubs for ``app`` / ``app.models`` / ``app.cashflow``. Pytest
# collects test files in alphabetical order, and conftest.py is imported
# BEFORE any test file, so it captures the real references first. Pull them
# from there to guarantee we test against the real Flask app + ORM models.
from conftest import (  # noqa: E402
    _db as db,
    _Balance as Balance,
    _User as User,
    _PlaidConnection as PlaidConnection,
    _plaid_service as plaid_service,
)
from app.crypto_utils import encrypt_password  # crypto_utils is never stubbed


# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def plaid_user(flask_app):
    """Create a fresh User with no Plaid connection for each test."""
    with flask_app.app_context():
        user = User(
            email=f"plaid-user-{datetime.utcnow().timestamp()}@test.local",
            password=generate_password_hash("testpw", method="scrypt"),
            name="Plaid User",
            admin=True,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    yield user_id

    with flask_app.app_context():
        # Clean up Plaid connection + balances + user.
        PlaidConnection.query.filter_by(user_id=user_id).delete()
        Balance.query.filter_by(user_id=user_id).delete()
        User.query.filter_by(id=user_id).delete()
        db.session.commit()


def _configure_plaid(flask_app, **overrides):
    cfg = {
        "PLAID_CLIENT_ID": "client-id",
        "PLAID_SECRET": "secret",
        "PLAID_ENV": "sandbox",
        "PLAID_PRODUCTS": "auth",
        "PLAID_COUNTRY_CODES": "US",
        "PLAID_REDIRECT_URI": "",
    }
    cfg.update(overrides)
    flask_app.config.update(cfg)


def _deconfigure_plaid(flask_app):
    for k in (
        "PLAID_CLIENT_ID",
        "PLAID_SECRET",
        "PLAID_ENV",
        "PLAID_PRODUCTS",
        "PLAID_REDIRECT_URI",
    ):
        flask_app.config[k] = ""


def _make_balances_response(account_id, *, available, current):
    balances = SimpleNamespace(available=available, current=current)
    account = SimpleNamespace(account_id=account_id, balances=balances)
    return SimpleNamespace(accounts=[account])


def _add_connection(user_id, **overrides):
    defaults = dict(
        user_id=user_id,
        encrypted_access_token=encrypt_password("access-sandbox-test"),
        plaid_item_id="item-1",
        plaid_account_id="acct-1",
        institution_name="Test Bank",
        account_name="Checking",
        account_mask="0001",
        account_type="depository",
        account_subtype="checking",
        is_active=True,
    )
    defaults.update(overrides)
    conn = PlaidConnection(**defaults)
    db.session.add(conn)
    db.session.commit()
    return conn


# ── Configuration ────────────────────────────────────────────────────────────


class TestPlaidConfigured:
    def test_not_configured_when_missing_values(self, flask_app):
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)
            assert plaid_service.plaid_is_configured() is False

    def test_configured_when_all_required_values_present(self, flask_app):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            assert plaid_service.plaid_is_configured() is True
            _deconfigure_plaid(flask_app)

    def test_balance_product_filtered_from_link_products(self, flask_app):
        with flask_app.app_context():
            _configure_plaid(flask_app, PLAID_PRODUCTS="auth,balance,transactions")
            products = plaid_service.get_configured_products()
            assert "balance" not in products
            assert "auth" in products
            _deconfigure_plaid(flask_app)


# ── Settings page status ─────────────────────────────────────────────────────


class TestSettingsPlaidStatus:
    def test_status_not_configured(self, auth_client, flask_app):
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)
        resp = auth_client.get("/api/v1/plaid/status")
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["configured"] is False
        assert body["connected"] is False

    def test_status_configured_not_connected(self, auth_client, flask_app):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        resp = auth_client.get("/api/v1/plaid/status")
        body = resp.get_json()["data"]
        assert body["configured"] is True
        assert body["connected"] is False
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_link_token_blocked_when_not_configured(self, auth_client, flask_app):
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)
        resp = auth_client.post("/api/v1/plaid/link-token")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "plaid_not_configured"


# ── Exchange token ──────────────────────────────────────────────────────────


class TestExchangePublicToken:
    def _mock_exchange(self, item_id="item-x", access_token="access-x"):
        return SimpleNamespace(item_id=item_id, access_token=access_token)

    def test_stores_minimal_metadata_and_encrypts_token(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            user = User.query.get(plaid_user)
            metadata = {
                "institution": {"institution_id": "ins_1", "name": "First Bank"},
                "accounts": [
                    {
                        "id": "acct-checking-1",
                        "name": "Primary Checking",
                        "mask": "1234",
                        "type": "depository",
                        "subtype": "checking",
                        "iso_currency_code": "USD",
                    }
                ],
            }
            with patch.object(
                plaid_service, "_plaid_client"
            ) as mock_client:
                mock_client.return_value.item_public_token_exchange.return_value = (
                    self._mock_exchange(item_id="item-abc", access_token="access-secret")
                )
                conn = plaid_service.exchange_public_token_for_user(
                    user, "public-token-123", metadata
                )

            assert conn.user_id == user.id
            assert conn.plaid_item_id == "item-abc"
            assert conn.plaid_account_id == "acct-checking-1"
            assert conn.institution_name == "First Bank"
            assert conn.account_mask == "1234"
            # Ensure token is encrypted, not plaintext.
            assert conn.encrypted_access_token != "access-secret"
            # No "balance"/queried balance field exists on this model.
            for forbidden in ("balance", "available_balance", "current_balance",
                              "raw_response", "transactions"):
                assert not hasattr(conn, forbidden), (
                    f"PlaidConnection must not store {forbidden!r}"
                )
            _deconfigure_plaid(flask_app)

    def test_rejects_when_already_connected(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            metadata = {
                "institution": {"institution_id": "ins_1", "name": "First"},
                "accounts": [
                    {"id": "acct-2", "type": "depository", "subtype": "checking"}
                ],
            }
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.item_public_token_exchange.return_value = (
                    self._mock_exchange()
                )
                with pytest.raises(plaid_service.PlaidServiceError) as ei:
                    plaid_service.exchange_public_token_for_user(
                        user, "ptok", metadata
                    )
                assert ei.value.code == "plaid_already_connected"
            _deconfigure_plaid(flask_app)

    def test_rejects_unsupported_account_type(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            user = User.query.get(plaid_user)
            metadata = {
                "institution": {"institution_id": "i", "name": "n"},
                "accounts": [
                    {"id": "acct-c", "type": "credit", "subtype": "credit card"}
                ],
            }
            with pytest.raises(plaid_service.PlaidServiceError) as ei:
                plaid_service.exchange_public_token_for_user(user, "ptok", metadata)
            assert ei.value.code in (
                "plaid_unsupported_account_type",
                "plaid_unsupported_account_subtype",
            )
            _deconfigure_plaid(flask_app)

    def test_rejects_multiple_accounts(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            user = User.query.get(plaid_user)
            metadata = {
                "institution": {"institution_id": "i", "name": "n"},
                "accounts": [
                    {"id": "a", "type": "depository", "subtype": "checking"},
                    {"id": "b", "type": "depository", "subtype": "checking"},
                ],
            }
            with pytest.raises(plaid_service.PlaidServiceError) as ei:
                plaid_service.exchange_public_token_for_user(user, "ptok", metadata)
            assert ei.value.code == "plaid_select_one_account"
            _deconfigure_plaid(flask_app)

    def test_rejects_when_account_id_missing(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            user = User.query.get(plaid_user)
            metadata = {
                "institution": {"institution_id": "i", "name": "n"},
                "accounts": [
                    {"type": "depository", "subtype": "checking", "name": "Checking"}
                ],
            }
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                with pytest.raises(plaid_service.PlaidServiceError) as ei:
                    plaid_service.exchange_public_token_for_user(user, "ptok", metadata)
                assert ei.value.code == "plaid_missing_account_id"
                assert not mock_client.return_value.item_public_token_exchange.called
            assert PlaidConnection.query.filter_by(user_id=user.id).count() == 0
            _deconfigure_plaid(flask_app)

    def test_rejects_when_account_id_blank(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            user = User.query.get(plaid_user)
            metadata = {
                "institution": {"institution_id": "i", "name": "n"},
                "accounts": [
                    {"id": "   ", "type": "depository", "subtype": "checking"}
                ],
            }
            with pytest.raises(plaid_service.PlaidServiceError) as ei:
                plaid_service.exchange_public_token_for_user(user, "ptok", metadata)
            assert ei.value.code == "plaid_missing_account_id"
            assert PlaidConnection.query.filter_by(user_id=user.id).count() == 0
            _deconfigure_plaid(flask_app)


# ── Remove connection ───────────────────────────────────────────────────────


class TestRemoveConnection:
    def test_calls_item_remove_and_deletes_local_record(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                plaid_service.remove_plaid_connection_for_user(user)
                assert mock_client.return_value.item_remove.called
            assert PlaidConnection.query.filter_by(user_id=user.id).count() == 0
            _deconfigure_plaid(flask_app)

    def test_removes_local_even_if_item_remove_fails(self, flask_app, plaid_user):
        from plaid.exceptions import ApiException

        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.item_remove.side_effect = ApiException()
                plaid_service.remove_plaid_connection_for_user(user)
            assert PlaidConnection.query.filter_by(user_id=user.id).count() == 0
            _deconfigure_plaid(flask_app)

    def test_balance_rows_remain_after_removal(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            db.session.add(Balance(user_id=plaid_user, amount=1234.0, date=date.today()))
            db.session.commit()
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client"):
                plaid_service.remove_plaid_connection_for_user(user)
            assert Balance.query.filter_by(user_id=plaid_user).count() == 1
            _deconfigure_plaid(flask_app)


# ── Balance update ──────────────────────────────────────────────────────────


class TestUpdateBalance:
    def test_noop_when_not_configured(self, flask_app, plaid_user):
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            result = plaid_service.update_plaid_balance_for_user(user)
            assert result["status"] == "skipped"
            assert result["reason"] == "not_configured"

    def test_noop_when_no_active_connection(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            user = User.query.get(plaid_user)
            result = plaid_service.update_plaid_balance_for_user(user)
            assert result["status"] == "skipped"
            assert result["reason"] == "no_connection"
            _deconfigure_plaid(flask_app)

    def test_uses_available_balance_when_present(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.accounts_balance_get.return_value = (
                    _make_balances_response("acct-1", available=500.25, current=600.00)
                )
                result = plaid_service.update_plaid_balance_for_user(user)
            assert result["status"] == "ok"
            assert result["source"] == "plaid_available_balance"
            today_row = (
                Balance.query.filter_by(user_id=plaid_user, date=date.today()).first()
            )
            assert today_row is not None
            assert float(today_row.amount) == pytest.approx(500.25)
            _deconfigure_plaid(flask_app)

    def test_falls_back_to_current_when_available_is_none(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.accounts_balance_get.return_value = (
                    _make_balances_response("acct-1", available=None, current=800.10)
                )
                result = plaid_service.update_plaid_balance_for_user(user)
            assert result["source"] == "plaid_current_balance_fallback"
            today_row = (
                Balance.query.filter_by(user_id=plaid_user, date=date.today()).first()
            )
            assert float(today_row.amount) == pytest.approx(800.10)
            _deconfigure_plaid(flask_app)

    def test_does_not_overwrite_when_both_balances_are_none(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            existing = Balance(user_id=plaid_user, amount=999.99, date=date.today())
            db.session.add(existing)
            db.session.commit()

            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.accounts_balance_get.return_value = (
                    _make_balances_response("acct-1", available=None, current=None)
                )
                result = plaid_service.update_plaid_balance_for_user(user)
            assert result["status"] == "skipped"
            today_row = (
                Balance.query.filter_by(user_id=plaid_user, date=date.today()).first()
            )
            assert float(today_row.amount) == pytest.approx(999.99)

            conn = (
                PlaidConnection.query.filter_by(user_id=plaid_user, is_active=True).first()
            )
            assert conn.last_sync_status == "no_balance_value"
            assert conn.last_sync_error  # non-empty, non-sensitive
            _deconfigure_plaid(flask_app)

    def test_updates_existing_row_instead_of_creating_duplicate(
        self, flask_app, plaid_user
    ):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            db.session.add(Balance(user_id=plaid_user, amount=100.0, date=date.today()))
            db.session.commit()

            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.accounts_balance_get.return_value = (
                    _make_balances_response("acct-1", available=250.0, current=300.0)
                )
                plaid_service.update_plaid_balance_for_user(user)

            rows = Balance.query.filter_by(user_id=plaid_user, date=date.today()).all()
            assert len(rows) == 1
            assert float(rows[0].amount) == pytest.approx(250.0)
            _deconfigure_plaid(flask_app)

    def test_creates_today_row_when_missing(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.accounts_balance_get.return_value = (
                    _make_balances_response("acct-1", available=42.0, current=None)
                )
                plaid_service.update_plaid_balance_for_user(user)

            row = (
                Balance.query.filter_by(user_id=plaid_user, date=date.today()).first()
            )
            assert row is not None
            assert float(row.amount) == pytest.approx(42.0)
            _deconfigure_plaid(flask_app)

    def test_safe_wrapper_swallows_unexpected_errors(self, flask_app, plaid_user):
        with flask_app.app_context():
            _configure_plaid(flask_app)
            _add_connection(plaid_user)
            user = User.query.get(plaid_user)
            with patch.object(plaid_service, "_plaid_client") as mock_client:
                mock_client.return_value.accounts_balance_get.side_effect = RuntimeError(
                    "boom"
                )
                # Must not raise.
                plaid_service.safe_update_plaid_balance_for_user(user)
            _deconfigure_plaid(flask_app)


# ── Dashboard integration ───────────────────────────────────────────────────


class TestDashboardIntegration:
    def test_dashboard_page_calls_update(self, auth_client, flask_app):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        with patch.object(plaid_service, "safe_update_plaid_balance_for_user") as mock_upd:
            # main.py imported the symbol directly; patch the imported name too.
            with patch("app.main.safe_update_plaid_balance_for_user") as mock_main_upd:
                resp = auth_client.get("/")
                assert resp.status_code == 200
                assert mock_main_upd.called
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_api_dashboard_calls_update(self, auth_client, flask_app):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        with patch("app.api.routes.data.safe_update_plaid_balance_for_user") as mock_upd:
            resp = auth_client.get("/api/v1/dashboard")
            assert resp.status_code == 200
            assert mock_upd.called
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_dashboard_still_loads_when_plaid_errors(self, auth_client, flask_app):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        # The safe wrapper around update_plaid_balance_for_user must swallow
        # any exception from the inner function so the dashboard still renders.
        with patch.object(plaid_service, "update_plaid_balance_for_user") as mock_inner:
            mock_inner.side_effect = RuntimeError("boom")
            try:
                resp = auth_client.get("/")
            except RuntimeError:
                pytest.fail("Dashboard should not propagate Plaid errors")
            assert resp.status_code == 200
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)


# ── Guest write restrictions ────────────────────────────────────────────────


class TestGuestWriteRestrictions:
    """Guest (admin=False) users must not be able to mutate Plaid state."""

    @pytest.fixture()
    def guest_client(self, flask_app):
        with flask_app.app_context():
            owner = User(
                email=f"plaid-owner-{datetime.utcnow().timestamp()}@test.local",
                password=generate_password_hash("pw", method="scrypt"),
                name="Owner",
                admin=True,
                is_account_owner=True,
                is_active=True,
            )
            db.session.add(owner)
            db.session.commit()
            guest = User(
                email=f"plaid-guest-{datetime.utcnow().timestamp()}@test.local",
                password=generate_password_hash("pw", method="scrypt"),
                name="Guest",
                admin=False,
                is_active=True,
                is_account_owner=False,
                owner_user_id=owner.id,
                account_owner_id=owner.id,
            )
            db.session.add(guest)
            db.session.commit()
            guest_id = guest.id
            owner_id = owner.id

        c = flask_app.test_client()
        with c.session_transaction() as sess:
            sess["_user_id"] = str(guest_id)
            sess["_fresh"] = True

        yield c

        with flask_app.app_context():
            PlaidConnection.query.filter(
                PlaidConnection.user_id.in_([guest_id, owner_id])
            ).delete(synchronize_session=False)
            User.query.filter(User.id.in_([guest_id, owner_id])).delete(
                synchronize_session=False
            )
            db.session.commit()

    def test_exchange_token_forbidden_for_guest(self, flask_app, guest_client):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        with patch.object(plaid_service, "_plaid_client") as mock_client:
            resp = guest_client.post(
                "/api/v1/plaid/exchange-token",
                json={
                    "public_token": "ptok",
                    "metadata": {
                        "institution": {"institution_id": "i", "name": "n"},
                        "accounts": [
                            {"id": "a", "type": "depository", "subtype": "checking"}
                        ],
                    },
                },
            )
            assert resp.status_code == 403
            assert resp.get_json()["code"] == "forbidden"
            assert not mock_client.return_value.item_public_token_exchange.called
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_remove_forbidden_for_guest(self, flask_app, guest_client):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        resp = guest_client.post("/api/v1/plaid/remove")
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "forbidden"
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_remove_delete_forbidden_for_guest(self, flask_app, guest_client):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        resp = guest_client.delete("/api/v1/plaid/remove")
        assert resp.status_code == 403
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_update_balance_forbidden_for_guest(self, flask_app, guest_client):
        with flask_app.app_context():
            _configure_plaid(flask_app)
        with patch.object(plaid_service, "update_plaid_balance_for_user") as mock_upd:
            resp = guest_client.post("/api/v1/plaid/update-balance")
            assert resp.status_code == 403
            assert not mock_upd.called
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)

    def test_status_allowed_for_guest(self, flask_app, guest_client):
        """Read-only status endpoint must remain accessible."""
        with flask_app.app_context():
            _configure_plaid(flask_app)
        resp = guest_client.get("/api/v1/plaid/status")
        assert resp.status_code == 200
        with flask_app.app_context():
            _deconfigure_plaid(flask_app)


# ── Model invariants ────────────────────────────────────────────────────────


class TestModelInvariants:
    def test_no_transaction_or_raw_payload_columns(self):
        cols = {c.name for c in PlaidConnection.__table__.columns}
        for forbidden in (
            "transactions",
            "raw_response",
            "balance",
            "available_balance",
            "current_balance",
            "routing_number",
            "account_number",
        ):
            assert forbidden not in cols, (
                f"PlaidConnection must not have column {forbidden!r}"
            )

    def test_unique_active_connection_per_user(self, flask_app, plaid_user):
        from sqlalchemy.exc import IntegrityError

        with flask_app.app_context():
            _add_connection(plaid_user)
            db.session.add(
                PlaidConnection(
                    user_id=plaid_user,
                    encrypted_access_token=encrypt_password("y"),
                    plaid_item_id="item-2",
                    plaid_account_id="acct-2",
                    is_active=True,
                )
            )
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
