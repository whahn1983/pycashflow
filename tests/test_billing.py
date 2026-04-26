"""Billing and subscription enforcement tests."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app import db
from app.models import PasswordSetupToken, Subscription, User
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
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com"

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
        sub = Subscription.query.filter_by(user_id=user.id, source="stripe").first()
        assert sub is not None
        assert sub.status == "active"
        assert sub.external_subscription_id == "sub_123"
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
        )
        db.session.add(user)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=user.id,
                source="stripe",
                status="expired",
                external_subscription_id="sub_existing_123",
            )
        )
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=user.id,
                source="stripe",
                status="active",
                external_subscription_id="sub_cancel_1",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            )
        )
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
        sub = Subscription.query.filter_by(user_id=user.id, source="stripe").first()
        assert sub is not None
        assert sub.status == "expired"
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
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com"

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
        sub = Subscription.query.filter_by(user_id=user.id, source="apple").first()
        assert sub is not None
        assert sub.status == "active"
        assert user.is_active is True


def test_appstore_verification_stub_mode_accepts_original_id_alias(flask_app, client):
    with flask_app.app_context():
        flask_app.config["APPSTORE_ALLOW_STUB_VERIFICATION"] = True
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com"

    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-stub-alias@test.local",
            "receipt_data": "dummy-receipt",
            "transaction": {"original_id": "ios_txn_alias_1"},
        },
    )
    assert resp.status_code == 200
    body = _json(resp)["data"]
    assert body["verification_status"] == "verified_stub"

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-stub-alias@test.local").first()
        assert user is not None
        sub = Subscription.query.filter_by(user_id=user.id, source="apple").first()
        assert sub is not None
        assert sub.original_transaction_id == "ios_txn_alias_1"


def test_appstore_verification_stub_mode_rejects_non_string_original_id(flask_app, client):
    with flask_app.app_context():
        flask_app.config["APPSTORE_ALLOW_STUB_VERIFICATION"] = True
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com"

    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-stub-alias-nonstr@test.local",
            "receipt_data": "dummy-receipt",
            "transaction": {"original_id": 123},
        },
    )
    assert resp.status_code == 200
    body = _json(resp)["data"]
    assert body["verification_status"] == "verified_stub"

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-stub-alias-nonstr@test.local").first()
        assert user is not None
        sub = Subscription.query.filter_by(user_id=user.id, source="apple").first()
        assert sub is not None
        assert sub.original_transaction_id == "dummy-receipt"


def test_appstore_existing_user_subscription_update_no_duplicate(
    flask_app, client, monkeypatch, billing_routes_module
):
    with flask_app.app_context():
        existing = User(
            email="ios-existing@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Existing iOS",
            admin=True,
            is_account_owner=True,
            is_active=False,
        )
        db.session.add(existing)
        db.session.commit()
        existing_id = existing.id

    monkeypatch.setattr(
        billing_routes_module,
        "_verify_appstore_purchase",
        lambda transaction_info, receipt_data: {
            "verification_status": "verified",
            "is_active": True,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=40),
            "original_transaction_id": "orig_txn_renewed",
            "latest_transaction_id": "ios_latest_renew_1",
            "environment": "production",
        },
    )

    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-existing@test.local",
            "receipt_data": "receipt",
            "transaction": {"original_transaction_id": "orig_txn_renewed"},
        },
    )
    assert resp.status_code == 200

    with flask_app.app_context():
        users = User.query.filter_by(email="ios-existing@test.local").all()
        assert len(users) == 1
        user = users[0]
        assert user.id == existing_id
        sub = Subscription.query.filter_by(
            user_id=user.id,
            source="apple",
            environment="production",
            original_transaction_id="orig_txn_renewed",
        ).first()
        assert sub is not None
        assert sub.status == "active"
        assert user.is_active is True
        assert sub.latest_transaction_id == "ios_latest_renew_1"


def test_appstore_expired_subscription_deactivates_owner_and_guest(
    flask_app, client, monkeypatch, billing_routes_module
):
    with flask_app.app_context():
        owner = User(
            email="ios-owner-expire@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Owner",
            admin=True,
            is_account_owner=True,
            is_active=True,
        )
        db.session.add(owner)
        db.session.commit()
        guest = User(
            email="ios-guest-expire@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Guest",
            admin=False,
            is_active=True,
            is_account_owner=False,
            owner_user_id=owner.id,
            account_owner_id=owner.id,
        )
        db.session.add(guest)
        db.session.commit()

    monkeypatch.setattr(
        billing_routes_module,
        "_verify_appstore_purchase",
        lambda transaction_info, receipt_data: {
            "verification_status": "verified",
            "is_active": False,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            "original_transaction_id": "orig_expire",
            "latest_transaction_id": "ios_latest_expire_1",
            "environment": "production",
        },
    )

    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-owner-expire@test.local",
            "receipt_data": "receipt",
            "transaction": {"original_transaction_id": "orig_expire"},
        },
    )
    assert resp.status_code == 200

    with flask_app.app_context():
        owner = User.query.filter_by(email="ios-owner-expire@test.local").first()
        guest = User.query.filter_by(email="ios-guest-expire@test.local").first()
        assert owner is not None
        assert guest is not None
        sub = Subscription.query.filter_by(
            user_id=owner.id, source="apple", original_transaction_id="orig_expire"
        ).first()
        assert sub is not None
        assert sub.status == "expired"
        assert owner.is_active is False
        assert guest.is_active is True

        # Enforced access checks must also disable guests when owner is expired.
        raw, _ = create_token_for_user(guest)

    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert me_resp.status_code == 401
    with flask_app.app_context():
        refreshed_guest = User.query.filter_by(email="ios-guest-expire@test.local").first()
        assert refreshed_guest.is_active is False
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_appstore_renewed_subscription_reactivates_deactivated_owner(
    flask_app, client, monkeypatch, billing_routes_module
):
    with flask_app.app_context():
        owner = User(
            email="ios-owner-renew@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Owner Renew",
            admin=True,
            is_account_owner=True,
            is_active=False,
        )
        db.session.add(owner)
        db.session.commit()

    monkeypatch.setattr(
        billing_routes_module,
        "_verify_appstore_purchase",
        lambda transaction_info, receipt_data: {
            "verification_status": "verified",
            "is_active": True,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=25),
            "original_transaction_id": "orig_renew",
            "latest_transaction_id": "ios_latest_renew_2",
            "environment": "sandbox",
        },
    )

    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-owner-renew@test.local",
            "receipt_data": "receipt",
            "transaction": {"original_transaction_id": "orig_renew"},
        },
    )
    assert resp.status_code == 200
    assert _json(resp)["data"]["environment"] == "sandbox"

    with flask_app.app_context():
        owner = User.query.filter_by(email="ios-owner-renew@test.local").first()
        assert owner is not None
        sub = Subscription.query.filter_by(
            user_id=owner.id, source="apple", original_transaction_id="orig_renew"
        ).first()
        assert sub is not None
        assert sub.status == "active"
        assert owner.is_active is True


def test_appstore_failed_verification_does_not_activate_user(
    flask_app, client, monkeypatch, billing_routes_module
):
    with flask_app.app_context():
        user = User(
            email="ios-fail@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Failed",
            admin=True,
            is_account_owner=True,
            is_active=False,
        )
        db.session.add(user)
        db.session.commit()

    def _raise_verification_error(transaction_info, receipt_data):
        raise billing_routes_module.AppStoreVerificationError("bad receipt")

    monkeypatch.setattr(billing_routes_module, "_verify_appstore_purchase", _raise_verification_error)

    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={"email": "ios-fail@test.local", "receipt_data": "bad", "transaction": {}},
    )
    assert resp.status_code == 401

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-fail@test.local").first()
        assert user is not None
        sub = Subscription.query.filter_by(user_id=user.id, source="apple").first()
        assert sub is None
        assert user.is_active is False


def test_stripe_new_user_generates_setup_token_and_sends_email(
    flask_app, client, monkeypatch, billing_routes_module
):
    sent_links = []
    with flask_app.app_context():
        flask_app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com/"

    def _fake_send_password_setup_email(user_name, user_email, setup_url, expires_minutes):
        sent_links.append((user_email, setup_url, expires_minutes))
        return True

    monkeypatch.setattr(billing_routes_module, "send_password_setup_email", _fake_send_password_setup_email)

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_setup_1",
                "subscription": "sub_setup_1",
                "customer_details": {"email": "new-stripe-setup@test.local"},
                "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
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
        user = User.query.filter_by(email="new-stripe-setup@test.local").first()
        assert user is not None
        token = PasswordSetupToken.query.filter_by(user_id=user.id).first()
        assert token is not None
        assert token.used_at is None
    assert len(sent_links) == 1
    assert sent_links[0][0] == "new-stripe-setup@test.local"
    assert sent_links[0][1].startswith("https://app.example.com/auth/set-password/")


def test_stripe_new_user_requires_frontend_base_url(flask_app, client):
    with flask_app.app_context():
        flask_app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
        flask_app.config["FRONTEND_BASE_URL"] = ""

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_setup_missing_frontend",
                "subscription": "sub_setup_missing_frontend",
                "customer_details": {"email": "missing-frontend@test.local"},
                "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            }
        },
    }
    raw = json.dumps(payload)
    resp = client.post(
        "/api/v1/billing/webhook/stripe",
        data=raw,
        headers={"Stripe-Signature": _sign(raw, "whsec_test_secret")},
    )
    assert resp.status_code == 422

    with flask_app.app_context():
        user = User.query.filter_by(email="missing-frontend@test.local").first()
        assert user is None


def test_appstore_new_user_generates_setup_token_and_sends_email(
    flask_app, client, monkeypatch, billing_routes_module
):
    sent_links = []
    with flask_app.app_context():
        flask_app.config["APPSTORE_ALLOW_STUB_VERIFICATION"] = True
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com"

    def _fake_send_password_setup_email(user_name, user_email, setup_url, expires_minutes):
        sent_links.append((user_email, setup_url, expires_minutes))
        return True

    monkeypatch.setattr(billing_routes_module, "send_password_setup_email", _fake_send_password_setup_email)

    expiry = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "new-appstore-setup@test.local",
            "receipt_data": "dummy-receipt",
            "expiry_date": expiry,
            "transaction": {"original_transaction_id": "ios_txn_setup_1"},
        },
    )
    assert resp.status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(email="new-appstore-setup@test.local").first()
        assert user is not None
        token = PasswordSetupToken.query.filter_by(user_id=user.id).first()
        assert token is not None
    assert len(sent_links) == 1
    assert sent_links[0][1].startswith("https://app.example.com/auth/set-password/")


def test_appstore_new_user_requires_frontend_base_url(flask_app, client):
    with flask_app.app_context():
        flask_app.config["APPSTORE_ALLOW_STUB_VERIFICATION"] = True
        flask_app.config["FRONTEND_BASE_URL"] = ""

    expiry = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "missing-appstore-frontend@test.local",
            "receipt_data": "dummy-receipt",
            "expiry_date": expiry,
            "transaction": {"original_transaction_id": "ios_txn_setup_missing_frontend"},
        },
    )
    assert resp.status_code == 422

    with flask_app.app_context():
        user = User.query.filter_by(email="missing-appstore-frontend@test.local").first()
        assert user is None


def test_existing_user_does_not_get_password_setup_email(
    flask_app, client, monkeypatch, billing_routes_module
):
    sent_calls = []
    with flask_app.app_context():
        flask_app.config["APPSTORE_ALLOW_STUB_VERIFICATION"] = True
        existing = User(
            email="existing-paid-user@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Existing",
            admin=True,
            is_account_owner=True,
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

    def _fake_send_password_setup_email(user_name, user_email, setup_url, expires_minutes):
        sent_calls.append(user_email)
        return True

    monkeypatch.setattr(billing_routes_module, "send_password_setup_email", _fake_send_password_setup_email)

    expiry = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "existing-paid-user@test.local",
            "receipt_data": "dummy-receipt",
            "expiry_date": expiry,
            "transaction": {"original_transaction_id": "ios_txn_existing_1"},
        },
    )
    assert resp.status_code == 200
    assert sent_calls == []

    with flask_app.app_context():
        user = User.query.filter_by(email="existing-paid-user@test.local").first()
        assert user is not None
        assert PasswordSetupToken.query.filter_by(user_id=user.id).first() is None


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
        )
        db.session.add(owner)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=owner.id,
                source="stripe",
                status="active",
                external_subscription_id="sub_owner_active_reactivate_1",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            )
        )
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
        )
        db.session.add(user)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=user.id,
                source="stripe",
                status="expired",
                external_subscription_id="sub_existing_update_123",
            )
        )
        db.session.commit()

    payload = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_existing_update_123",
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
        sub = Subscription.query.filter_by(
            user_id=user.id, source="stripe", external_subscription_id="sub_existing_update_123"
        ).first()
        assert sub is not None
        assert sub.status == "active"
        assert user.is_active is True
        assert (
            Subscription.query.filter_by(
                source="stripe", external_subscription_id="sub_existing_update_123"
            ).count()
            == 1
        )


def test_guest_of_global_admin_is_subscription_exempt(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
        admin = User(
            email="gadmin-owner@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="GlobalAdmin",
            admin=True,
            is_global_admin=True,
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()

        guest = User(
            email="gadmin-guest@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Guest",
            admin=False,
            is_active=True,
            account_owner_id=admin.id,
            owner_user_id=admin.id,
            is_account_owner=False,
        )
        db.session.add(guest)
        db.session.commit()

        raw, _ = create_token_for_user(guest)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200

    with flask_app.app_context():
        guest_db = User.query.filter_by(email="gadmin-guest@test.local").first()
        assert guest_db.is_active is True
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_inactive_guest_of_global_admin_is_reactivated(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
        admin = User(
            email="gadmin-owner2@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="GlobalAdmin",
            admin=True,
            is_global_admin=True,
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()

        guest = User(
            email="gadmin-guest-inactive@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Guest",
            admin=False,
            is_active=False,
            account_owner_id=admin.id,
            owner_user_id=admin.id,
            is_account_owner=False,
        )
        db.session.add(guest)
        db.session.commit()

        raw, _ = create_token_for_user(guest)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200

    with flask_app.app_context():
        guest_db = User.query.filter_by(email="gadmin-guest-inactive@test.local").first()
        assert guest_db.is_active is True
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_global_admin_is_subscription_exempt(flask_app, client):
    with flask_app.app_context():
        admin = User(
            email="gadmin@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Global",
            admin=True,
            is_global_admin=True,
            is_active=True,
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
        )
        db.session.add(user)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=user.id,
                source="stripe",
                status="active",
                external_subscription_id="sub_billing_status_1",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            )
        )
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
        )
        db.session.add(owner)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=owner.id,
                source="stripe",
                status="active",
                external_subscription_id="sub_billing_owner_1",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            )
        )
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


def test_billing_status_rejects_manual_deactivated_user(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = False
        user = User(
            email="billing-manual-inactive@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="BillingManualInactive",
            admin=True,
            is_active=False,
        )
        db.session.add(user)
        db.session.commit()
        raw, _ = create_token_for_user(user)

    resp = client.get("/api/v1/billing/status", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 401

    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


def test_billing_status_rejects_admin_deactivated_user_with_current_subscription(flask_app, client):
    original_toggle = flask_app.config["PAYMENTS_ENABLED"]
    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = True
        user = User(
            email="billing-admin-inactive@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="BillingAdminInactive",
            admin=True,
            is_active=False,
        )
        db.session.add(user)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=user.id,
                source="stripe",
                status="active",
                external_subscription_id="sub_billing_admin_1",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10),
            )
        )
        db.session.commit()
        raw, _ = create_token_for_user(user)

    resp = client.get("/api/v1/billing/status", headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 401

    with flask_app.app_context():
        flask_app.config["PAYMENTS_ENABLED"] = original_toggle


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
        )
        db.session.add(user)
        db.session.commit()
        db.session.add(
            Subscription(
                user_id=user.id,
                source="stripe",
                status="expired",
                external_subscription_id="sub_billing_expired_1",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            )
        )
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


def test_appstore_same_original_transaction_id_different_user_rejected(
    flask_app, client, monkeypatch, billing_routes_module
):
    with flask_app.app_context():
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.example.com"
        first = User(
            email="ios-owner-a@test.local",
            password=generate_password_hash("pass12345", method="scrypt"),
            name="Owner A",
            admin=True,
            is_account_owner=True,
            is_active=True,
        )
        db.session.add(first)
        db.session.commit()
        first_id = first.id

    monkeypatch.setattr(
        billing_routes_module,
        "_verify_appstore_purchase",
        lambda *_args, **_kwargs: {
            "verification_status": "verified",
            "is_active": True,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            "original_transaction_id": "orig_unique_lock_1",
            "latest_transaction_id": "latest_unique_lock_1",
            "environment": "production",
        },
    )
    resp_a = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-owner-a@test.local",
            "receipt_data": "receipt-a",
            "transaction": {"original_transaction_id": "orig_unique_lock_1"},
        },
    )
    assert resp_a.status_code == 200

    resp_b = client.post(
        "/api/v1/billing/verify-appstore",
        json={
            "email": "ios-owner-b@test.local",
            "receipt_data": "receipt-b",
            "transaction": {"original_transaction_id": "orig_unique_lock_1"},
        },
    )
    assert resp_b.status_code == 401

    with flask_app.app_context():
        sub = Subscription.query.filter_by(
            source="apple",
            environment="production",
            original_transaction_id="orig_unique_lock_1",
        ).one()
        assert sub.user_id == first_id
        user_b = User.query.filter_by(email="ios-owner-b@test.local").first()
        assert user_b is None


def test_appstore_idempotent_reverify_does_not_duplicate_subscription(
    flask_app, client, monkeypatch, billing_routes_module
):
    monkeypatch.setattr(
        billing_routes_module,
        "_verify_appstore_purchase",
        lambda *_args, **_kwargs: {
            "verification_status": "verified",
            "is_active": True,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=15),
            "original_transaction_id": "orig_idempotent_1",
            "latest_transaction_id": "latest_idempotent_1",
            "environment": "sandbox",
        },
    )
    payload = {
        "email": "ios-idempotent@test.local",
        "receipt_data": "receipt",
        "transaction": {"original_transaction_id": "orig_idempotent_1"},
    }
    assert client.post("/api/v1/billing/verify-appstore", json=payload).status_code == 200
    assert client.post("/api/v1/billing/verify-appstore", json=payload).status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-idempotent@test.local").one()
        subs = Subscription.query.filter_by(
            user_id=user.id,
            source="apple",
            environment="sandbox",
            original_transaction_id="orig_idempotent_1",
        ).all()
        assert len(subs) == 1


def test_appstore_same_original_transaction_id_different_environment_allowed(
    flask_app, client, monkeypatch, billing_routes_module
):
    responses = [
        {
            "verification_status": "verified",
            "is_active": True,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=15),
            "original_transaction_id": "orig_env_dual_1",
            "latest_transaction_id": "latest_env_prod",
            "environment": "production",
        },
        {
            "verification_status": "verified",
            "is_active": True,
            "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=15),
            "original_transaction_id": "orig_env_dual_1",
            "latest_transaction_id": "latest_env_sandbox",
            "environment": "sandbox",
        },
    ]

    def _mock_verify(*_args, **_kwargs):
        return responses.pop(0)

    monkeypatch.setattr(billing_routes_module, "_verify_appstore_purchase", _mock_verify)
    payload = {
        "email": "ios-env@test.local",
        "receipt_data": "receipt",
        "transaction": {"original_transaction_id": "orig_env_dual_1"},
    }
    assert client.post("/api/v1/billing/verify-appstore", json=payload).status_code == 200
    assert client.post("/api/v1/billing/verify-appstore", json=payload).status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(email="ios-env@test.local").one()
        assert (
            Subscription.query.filter_by(
                user_id=user.id,
                source="apple",
                environment="production",
                original_transaction_id="orig_env_dual_1",
            ).count()
            == 1
        )
        assert (
            Subscription.query.filter_by(
                user_id=user.id,
                source="apple",
                environment="sandbox",
                original_transaction_id="orig_env_dual_1",
            ).count()
            == 1
        )
