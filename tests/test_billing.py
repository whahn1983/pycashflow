"""Billing and subscription enforcement tests."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app import db
from app.models import User
from app.api.auth_utils import create_token_for_user


def _sign(payload: str, secret: str, timestamp: int = 1712700000) -> str:
    signed = f"{timestamp}.{payload}".encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _json(resp):
    body = resp.get_json()
    assert body is not None
    return body


def test_stripe_webhook_checkout_activation_flow(flask_app, client):
    with flask_app.app_context():
        flask_app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "subscription": "sub_123",
                "customer_details": {"email": "stripe-user@test.local"},
                "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            }
        },
    }
    raw = json.dumps(payload)

    resp = client.post(
        "/api/v1/billing/webhook/stripe",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign(raw, "whsec_test_secret"),
        },
    )
    assert resp.status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(email="stripe-user@test.local").first()
        assert user is not None
        assert user.subscription_status == "active"
        assert user.subscription_source == "stripe"
        assert user.subscription_id == "sub_123"
        assert user.is_active is True
        assert user.is_account_owner is True


def test_stripe_subscription_deleted_expires_user(flask_app, client):
    with flask_app.app_context():
        flask_app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
        user = User(
            email="cancel@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Cancel",
            admin=True,
            is_account_owner=True,
            is_active=True,
            subscription_status="active",
            subscription_source="stripe",
            subscription_id="sub_cancel_1",
        )
        db.session.add(user)
        db.session.commit()

    payload = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_cancel_1"}},
    }
    raw = json.dumps(payload)
    resp = client.post(
        "/api/v1/billing/webhook/stripe",
        data=raw,
        headers={"Stripe-Signature": _sign(raw, "whsec_test_secret")},
    )
    assert resp.status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(email="cancel@test.local").first()
        assert user.subscription_status == "expired"
        assert user.is_active is False


def test_appstore_verification_creates_or_updates_owner(flask_app, client):
    expiry = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-user@test.local",
            "receipt_data": "dummy-receipt",
            "expiry_date": expiry,
            "transaction": {"original_transaction_id": "ios_txn_1"},
        },
    )
    assert resp.status_code == 401

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-user@test.local").first()
        assert user is None


def test_appstore_verification_stub_mode_can_activate_owner(flask_app, client):
    with flask_app.app_context():
        flask_app.config["APPSTORE_ALLOW_STUB_VERIFICATION"] = True

    expiry = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-stub@test.local",
            "receipt_data": "dummy-receipt",
            "expiry_date": expiry,
            "transaction": {"original_transaction_id": "ios_txn_1"},
        },
    )
    assert resp.status_code == 200
    body = _json(resp)["data"]
    assert body["verification_status"] == "verified_stub"

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-stub@test.local").first()
        assert user is not None
        assert user.subscription_source == "app_store"
        assert user.subscription_status == "active"
        assert user.is_active is True


def test_guest_access_depends_on_owner_subscription(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
        owner = User(
            email="owner-expired@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Owner",
            admin=True,
            is_active=True,
            subscription_status="expired",
            subscription_source="stripe",
        )
        db.session.add(owner)
        db.session.commit()

        guest = User(
            email="guest-expired@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Guest",
            admin=False,
            is_active=True,
            account_owner_id=owner.id,
            owner_user_id=owner.id,
            is_account_owner=False,
            subscription_status="inactive",
            subscription_source="none",
        )
        db.session.add(guest)
        db.session.commit()

        raw, _ = create_token_for_user(guest)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 401

    with flask_app.app_context():
        guest_db = User.query.filter_by(email="guest-expired@test.local").first()
        assert guest_db.is_active is False
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_inactive_guest_is_reactivated_when_owner_subscription_is_current(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
        owner = User(
            email="owner-active@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Owner",
            admin=True,
            is_active=True,
            subscription_status="active",
            subscription_source="stripe",
            subscription_expiry=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        )
        db.session.add(owner)
        db.session.commit()

        guest = User(
            email="guest-inactive@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Guest",
            admin=False,
            is_active=False,
            account_owner_id=owner.id,
            owner_user_id=owner.id,
            is_account_owner=False,
            subscription_status="inactive",
            subscription_source="none",
        )
        db.session.add(guest)
        db.session.commit()

        raw, _ = create_token_for_user(guest)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200

    with flask_app.app_context():
        guest_db = User.query.filter_by(email="guest-inactive@test.local").first()
        assert guest_db.is_active is True
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_subscription_webhook_update_without_email_uses_existing_subscription_id(flask_app, client):
    with flask_app.app_context():
        flask_app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
        user = User(
            email="sub-update@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="SubUpdate",
            admin=True,
            is_account_owner=True,
            is_active=False,
            subscription_status="expired",
            subscription_source="stripe",
            subscription_id="sub_existing_123",
        )
        db.session.add(user)
        db.session.commit()

    payload = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_existing_123",
                "status": "active",
                "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=45)).timestamp()),
            }
        },
    }
    raw = json.dumps(payload)
    resp = client.post(
        "/api/v1/billing/webhook/stripe",
        data=raw,
        headers={"Stripe-Signature": _sign(raw, "whsec_test_secret")},
    )
    assert resp.status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(email="sub-update@test.local").first()
        assert user.subscription_status == "active"
        assert user.is_active is True


def test_global_admin_is_subscription_exempt(flask_app, client):
    with flask_app.app_context():
        admin = User(
            email="gadmin@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Global",
            admin=True,
            is_global_admin=True,
            is_active=True,
            subscription_status="expired",
            subscription_source="none",
        )
        db.session.add(admin)
        db.session.commit()
        raw, _ = create_token_for_user(admin)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200


def test_payments_toggle_disables_subscription_enforcement(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = False
        user = User(
            email="manual@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Manual",
            admin=True,
            is_active=True,
            subscription_status="expired",
            subscription_source="manual",
        )
        db.session.add(user)
        db.session.commit()
        raw, _ = create_token_for_user(user)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200

    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_billing_status_endpoint_returns_subscription_snapshot(flask_app, client):
    with flask_app.app_context():
        user = User(
            email="billing-status@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="BillingStatus",
            admin=True,
            is_active=True,
            subscription_status="active",
            subscription_source="stripe",
            subscription_expiry=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        )
        db.session.add(user)
        db.session.commit()
        raw, _ = create_token_for_user(user)

    resp = client.get("/api/v1/billing/status", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200
    body = _json(resp)["data"]
    assert body["user_id"] is not None
    assert body["is_active"] is True
    assert body["effective_is_active"] is True
    assert body["subscription_status"] == "active"
    assert body["subscription_source"] == "stripe"
    assert isinstance(body["payments_enabled"], bool)
    assert body["is_guest"] is False
    assert body["owner_user_id"] is None


def test_billing_status_endpoint_for_guest_uses_owner_subscription(flask_app, client):
    with flask_app.app_context():
        owner = User(
            email="billing-owner@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Owner",
            admin=True,
            is_active=True,
            subscription_status="active",
            subscription_source="stripe",
            subscription_expiry=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        )
        db.session.add(owner)
        db.session.commit()

        guest = User(
            email="billing-guest@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Guest",
            admin=False,
            is_active=True,
            is_account_owner=False,
            owner_user_id=owner.id,
            account_owner_id=owner.id,
            subscription_status="inactive",
            subscription_source="none",
        )
        db.session.add(guest)
        db.session.commit()
        raw, _ = create_token_for_user(guest)

    resp = client.get("/api/v1/billing/status", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200
    body = _json(resp)["data"]
    assert body["effective_is_active"] is True
    assert body["subscription_status"] == "active"
    assert body["subscription_source"] == "stripe"
    assert body["is_guest"] is True
    assert body["owner_user_id"] is not None


def test_billing_status_allows_inactive_users_for_refresh(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
        user = User(
            email="billing-expired@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="BillingExpired",
            admin=True,
            is_active=False,
            subscription_status="expired",
            subscription_source="stripe",
            subscription_expiry=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
        )
        db.session.add(user)
        db.session.commit()
        raw, _ = create_token_for_user(user)

    resp = client.get("/api/v1/billing/status", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200
    body = _json(resp)["data"]
    assert body["is_active"] is False
    assert body["effective_is_active"] is False
    assert body["subscription_status"] == "expired"

    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle
