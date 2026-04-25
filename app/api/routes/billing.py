"""API v1 billing routes (Stripe + App Store + manual activation hooks)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone

from flask import current_app, request
from werkzeug.security import generate_password_hash

from app import db
from app.models import User
from app.getemail import send_password_setup_email
from app.password_setup import (
    create_password_setup_link,
)
from app.appstore import (
    AppStoreVerificationError,
    verify_app_store_subscription,
)
from app.subscription import (
    SUB_ACTIVE,
    SUB_EXPIRED,
    apply_subscription_status,
    owner_for_user,
    payments_enabled,
    subscription_is_current,
)

from app.api import api
from app.api.auth_utils import api_login_required, get_api_user
from app.api.errors import unauthorized, validation_error
from app.api.responses import api_created, api_ok


logger = logging.getLogger(__name__)

def _frontend_base_url_configured() -> bool:
    frontend_base = (current_app.config.get("FRONTEND_BASE_URL") or "").strip()
    return bool(frontend_base.rstrip("/"))


def _can_create_paid_user(email: str) -> bool:
    if _frontend_base_url_configured():
        return True

    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        return True

    logger.error(
        "Cannot create payment user without FRONTEND_BASE_URL: email=%s",
        email,
    )
    return False


def _parse_unix_ts(raw) -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _create_or_get_owner(email: str) -> tuple[User, bool]:
    user = User.query.filter_by(email=email).first()
    if user:
        return user, False

    user = User(
        email=email,
        name=email.split("@")[0],
        password=generate_password_hash(secrets.token_urlsafe(48), method="scrypt"),
        admin=True,
        is_account_owner=True,
        is_active=True,
        subscription_status="inactive",
        subscription_source="none",
    )
    db.session.add(user)
    db.session.commit()
    logger.info("Auto-created account owner from payment flow email=%s user_id=%s", email, user.id)
    return user, True


def _send_setup_email_for_new_user(user: User, created: bool) -> None:
    if not created:
        return

    setup_url, expires_minutes = create_password_setup_link(user)
    sent = send_password_setup_email(
        user_name=user.name or user.email.split("@")[0],
        user_email=user.email,
        setup_url=setup_url,
        expires_minutes=expires_minutes,
    )
    if not sent:
        logger.warning("Password setup email could not be sent for user_id=%s", user.id)


def _verify_stripe_signature(payload: str, signature_header: str) -> bool:
    endpoint_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET") or os.environ.get(
        "STRIPE_WEBHOOK_SECRET"
    )
    if not endpoint_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured; rejecting webhook")
        return False

    try:
        parts = dict(item.split("=", 1) for item in signature_header.split(",") if "=" in item)
    except Exception:
        return False

    timestamp = parts.get("t")
    provided_sig = parts.get("v1")
    if not timestamp or not provided_sig:
        return False

    signed_payload = f"{timestamp}.{payload}".encode()
    expected = hmac.new(endpoint_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided_sig)


def _appstore_stub_verification_enabled() -> bool:
    configured = current_app.config.get("APPSTORE_ALLOW_STUB_VERIFICATION")
    if configured is None:
        configured = os.environ.get("APPSTORE_ALLOW_STUB_VERIFICATION", "")
    return str(configured).strip().lower() in {"1", "true", "yes", "on"}


def _verify_appstore_purchase(transaction_info: dict, receipt_data: str | None):
    """Verify App Store purchase data against Apple APIs.

    Stub verification can be enabled for local development/testing only.
    """
    def _strip_if_string(value) -> str:
        return value.strip() if isinstance(value, str) else ""

    original_transaction_id = (
        _strip_if_string(transaction_info.get("original_transaction_id"))
        or _strip_if_string(transaction_info.get("originalTransactionId"))
        or _strip_if_string(transaction_info.get("original_id"))
    )

    if _appstore_stub_verification_enabled():
        if not original_transaction_id:
            original_transaction_id = (
                _strip_if_string(transaction_info.get("id"))
                or _strip_if_string(receipt_data)
                or "stub-receipt"
            )
        if not original_transaction_id:
            raise AppStoreVerificationError("missing original transaction id")
        return {
            "verification_status": "verified_stub",
            "is_active": True,
            "expiry": None,
            "subscription_id": original_transaction_id,
            "environment": "stub",
        }

    if not original_transaction_id:
        raise AppStoreVerificationError(
            "transaction.original_transaction_id is required when stub verification is disabled"
        )

    issuer_id = (current_app.config.get("APPLE_ISSUER_ID") or os.environ.get("APPLE_ISSUER_ID") or "").strip()
    key_id = (current_app.config.get("APPLE_KEY_ID") or os.environ.get("APPLE_KEY_ID") or "").strip()
    private_key = current_app.config.get("APPLE_PRIVATE_KEY") or os.environ.get("APPLE_PRIVATE_KEY")
    private_key_path = current_app.config.get("APPLE_PRIVATE_KEY_PATH") or os.environ.get("APPLE_PRIVATE_KEY_PATH")
    environment = (
        current_app.config.get("APPLE_ENVIRONMENT")
        or os.environ.get("APPLE_ENVIRONMENT")
        or "production"
    )
    expected_bundle_id = (
        current_app.config.get("APPLE_BUNDLE_ID")
        or os.environ.get("APPLE_BUNDLE_ID")
        or ""
    ).strip()

    if not issuer_id or not key_id:
        raise AppStoreVerificationError(
            "Apple credentials are incomplete: APPLE_ISSUER_ID and APPLE_KEY_ID are required"
        )

    verification = verify_app_store_subscription(
        original_transaction_id=original_transaction_id,
        issuer_id=issuer_id,
        key_id=key_id,
        private_key=private_key,
        private_key_path=private_key_path,
        environment=environment,
    )

    if expected_bundle_id and verification.bundle_id and verification.bundle_id != expected_bundle_id:
        raise AppStoreVerificationError("App Store bundle identifier mismatch")

    return {
        "verification_status": "verified",
        "is_active": verification.is_active,
        "expiry": verification.expiry,
        "subscription_id": verification.original_transaction_id,
        "environment": verification.environment,
        "status_code": verification.status_code,
        "bundle_id": verification.bundle_id,
    }


def _apply_stripe_event(event_type: str, obj: dict) -> tuple[dict, int]:
    if event_type == "checkout.session.completed":
        email = (obj.get("customer_details") or {}).get("email") or obj.get("customer_email")
        if not email:
            return validation_error({"email": "customer email missing from checkout session"})
        normalized_email = email.strip().lower()
        if not _can_create_paid_user(normalized_email):
            return validation_error(
                {"frontend_base_url": "FRONTEND_BASE_URL is required to onboard new paid users"}
            )
        user, created = _create_or_get_owner(normalized_email)
        expiry = _parse_unix_ts(obj.get("current_period_end"))
        apply_subscription_status(
            user,
            status=SUB_ACTIVE,
            source="stripe",
            subscription_id=obj.get("subscription") or obj.get("id"),
            expiry=expiry,
            activate=True,
        )
        _send_setup_email_for_new_user(user, created)
        return api_ok({"processed": event_type, "user_id": user.id})

    if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        email = ((obj.get("customer_email") or "").strip().lower())
        if not email and obj.get("metadata"):
            email = (obj.get("metadata", {}).get("email") or "").strip().lower()
        subscription_id = obj.get("id")
        user = None
        if subscription_id:
            user = User.query.filter_by(subscription_id=subscription_id).first()
        created = False
        if user is None and email:
            if not _can_create_paid_user(email):
                return validation_error(
                    {"frontend_base_url": "FRONTEND_BASE_URL is required to onboard new paid users"}
                )
            user, created = _create_or_get_owner(email)
        if user is None:
            logger.warning(
                "Skipping Stripe subscription event without resolvable user: type=%s sub_id=%s",
                event_type,
                subscription_id,
            )
            return api_ok({"processed": event_type, "ignored": True})

        status = obj.get("status")
        expires_at = _parse_unix_ts(obj.get("current_period_end"))
        if status in {"active", "trialing"}:
            next_status = SUB_ACTIVE if status == "active" else "trial"
            activate = True
        else:
            next_status = SUB_EXPIRED
            activate = False

        apply_subscription_status(
            user,
            status=next_status,
            source="stripe",
            subscription_id=subscription_id,
            expiry=expires_at,
            activate=activate,
        )
        _send_setup_email_for_new_user(user, created)
        return api_ok({"processed": event_type, "user_id": user.id})

    if event_type in {"customer.subscription.deleted", "invoice.payment_failed"}:
        sub_id = obj.get("id") if event_type == "customer.subscription.deleted" else obj.get("subscription")
        if not sub_id:
            return validation_error({"subscription": "subscription id missing"})

        user = User.query.filter_by(subscription_id=sub_id).first()
        if not user:
            return api_ok({"processed": event_type, "ignored": True})

        apply_subscription_status(
            user,
            status=SUB_EXPIRED,
            source="stripe",
            subscription_id=sub_id,
            expiry=datetime.now(timezone.utc).replace(tzinfo=None),
            activate=False,
        )
        return api_ok({"processed": event_type, "user_id": user.id})

    return api_ok({"processed": event_type, "ignored": True})


@api.route("/billing/create-checkout-session", methods=["POST"])
@api_login_required(require_bearer=True)
def api_create_checkout_session():
    user = get_api_user()
    if not user.admin:
        return unauthorized("Guest users cannot create checkout sessions")

    body = request.get_json(silent=True) or {}
    success_url = (body.get("success_url") or "").strip()
    cancel_url = (body.get("cancel_url") or "").strip()
    if not success_url or not cancel_url:
        return validation_error(
            {
                "success_url": "success_url is required",
                "cancel_url": "cancel_url is required",
            }
        )

    session_id = f"cs_test_{secrets.token_urlsafe(18)}"
    return api_created(
        {
            "id": session_id,
            "checkout_url": f"https://checkout.stripe.com/pay/{session_id}",
            "mode": "subscription",
            "subscription_source": "stripe",
        }
    )


@api.route("/billing/status", methods=["GET"])
@api_login_required(enforce_active=False)
def api_billing_status():
    user = get_api_user()
    owner = owner_for_user(user)

    owner_is_global_admin = bool(owner and owner.is_global_admin)

    if not user.is_global_admin and not user.is_active:
        # Keep manual/admin deactivation checks, but allow expired users to
        # retrieve billing status when payments enforcement is enabled.
        if not payments_enabled() or owner_is_global_admin or subscription_is_current(owner):
            return unauthorized("Invalid credentials or account is not active")

    owner_id = user.owner_user_id or user.account_owner_id

    effective_is_active = bool(user.is_global_admin) or owner_is_global_admin
    if not effective_is_active:
        if payments_enabled():
            effective_is_active = subscription_is_current(owner)
        else:
            effective_is_active = bool(user.is_active)

    subscription_subject = owner or user
    expiry = subscription_subject.subscription_expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    return api_ok(
        {
            "user_id": user.id,
            "is_active": bool(user.is_active),
            "effective_is_active": effective_is_active,
            "subscription_status": subscription_subject.subscription_status,
            "subscription_source": subscription_subject.subscription_source,
            "subscription_expiry": expiry.strftime("%Y-%m-%dT%H:%M:%SZ") if expiry else None,
            "payments_enabled": payments_enabled(),
            "is_global_admin": bool(user.is_global_admin),
            "is_guest": owner_id is not None,
            "owner_user_id": owner_id,
        }
    )


@api.route("/billing/webhook/stripe", methods=["POST"])
def api_stripe_webhook():
    raw_payload = request.get_data(as_text=True)
    signature = request.headers.get("Stripe-Signature", "")
    if not _verify_stripe_signature(raw_payload, signature):
        return unauthorized("Invalid Stripe webhook signature")

    event = json.loads(raw_payload or "{}")
    event_type = event.get("type")
    event_object = ((event.get("data") or {}).get("object")) or {}
    if not event_type:
        return validation_error({"type": "Stripe event type missing"})

    return _apply_stripe_event(event_type, event_object)


@api.route("/billing/verify-appstore", methods=["POST"])
def api_verify_appstore():
    body = request.get_json(silent=True) or {}

    receipt_data = body.get("receipt_data")
    transaction_info = body.get("transaction") or {}
    email = (body.get("email") or "").strip().lower()
    errors = {}
    if not email:
        errors["email"] = "email is required"
    if not receipt_data and not transaction_info:
        errors["receipt_data"] = "receipt_data or transaction is required"
    if errors:
        return validation_error(errors)

    try:
        verification = _verify_appstore_purchase(transaction_info, receipt_data)
    except AppStoreVerificationError as exc:
        logger.warning("App Store verification failed: %s", exc)
        return unauthorized("App Store verification failed")

    expiry = verification.get("expiry")
    is_active = bool(verification.get("is_active"))
    subscription_status = SUB_ACTIVE if is_active else SUB_EXPIRED

    if not _can_create_paid_user(email):
        return validation_error(
            {"frontend_base_url": "FRONTEND_BASE_URL is required to onboard new paid users"}
        )

    user, created = _create_or_get_owner(email)
    apply_subscription_status(
        user,
        status=subscription_status,
        source="app_store",
        subscription_id=verification.get("subscription_id"),
        expiry=expiry,
        activate=is_active,
    )
    _send_setup_email_for_new_user(user, created)

    return api_ok(
        {
            "verification_status": verification.get("verification_status"),
            "user_id": user.id,
            "subscription_status": user.subscription_status,
            "subscription_source": user.subscription_source,
            "environment": verification.get("environment"),
        }
    )
