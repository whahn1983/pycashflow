"""Subscription and account-activation helpers.

This module centralises payment gating so both web sessions and API requests
apply the same account-owner and guest-user rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from flask import current_app

from app import db
from app.models import Subscription, User


logger = logging.getLogger(__name__)

SUB_ACTIVE = "active"
SUB_INACTIVE = "inactive"
SUB_TRIAL = "trial"
SUB_GRACE_PERIOD = "grace_period"
SUB_EXPIRED = "expired"
SUB_CANCELED = "canceled"


VALID_SUBSCRIPTION_STATUSES = {
    SUB_ACTIVE,
    SUB_INACTIVE,
    SUB_TRIAL,
    SUB_GRACE_PERIOD,
    SUB_EXPIRED,
    SUB_CANCELED,
}
ACTIVE_SUBSCRIPTION_STATUSES = {SUB_ACTIVE, SUB_TRIAL, SUB_GRACE_PERIOD}


def payments_enabled() -> bool:
    """Return whether payment enforcement is enabled."""
    return bool(current_app.config.get("PAYMENTS_ENABLED", False))


def owner_for_user(user: User | None) -> User | None:
    """Return account owner for *user* (or user itself when already owner)."""
    if user is None:
        return None

    owner_id = user.owner_user_id or user.account_owner_id
    if owner_id:
        return db.session.get(User, owner_id)
    return user


def subscription_is_current(user: User | None) -> bool:
    """Return True when user subscription status/expiry is currently valid."""
    if user is None:
        return False
    subscription = get_effective_subscription(user)
    if subscription is None:
        return False
    if subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return False
    if subscription.expires_at is None:
        return True

    expiry = subscription.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry >= datetime.now(timezone.utc)


def get_effective_subscription(user: User | None) -> Subscription | None:
    """Return a user's most recently-updated subscription record, if present."""
    if user is None:
        return None

    latest_active = (
        Subscription.query.filter_by(user_id=user.id)
        .filter(Subscription.status.in_(tuple(ACTIVE_SUBSCRIPTION_STATUSES)))
        .order_by(Subscription.expires_at.desc(), Subscription.updated_at.desc())
        .first()
    )
    if latest_active is not None:
        return latest_active

    latest = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.updated_at.desc(), Subscription.id.desc())
        .first()
    )
    return latest


def _canonical_source(source: str) -> str:
    source = (source or "").strip().lower()
    if source in {"app_store", "apple"}:
        return "apple"
    return source or "manual"


def upsert_subscription(
    user: User,
    *,
    source: str,
    status: str,
    environment: str | None = None,
    product_id: str | None = None,
    original_transaction_id: str | None = None,
    latest_transaction_id: str | None = None,
    external_subscription_id: str | None = None,
    expires_at: datetime | None = None,
    raw_last_verified_at: datetime | None = None,
) -> Subscription:
    """Create or update a provider subscription for a user."""
    canonical_source = _canonical_source(source)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    raw_last_verified_at = raw_last_verified_at or now
    if status not in VALID_SUBSCRIPTION_STATUSES:
        raise ValueError(f"Invalid subscription status: {status}")

    query = Subscription.query.filter_by(user_id=user.id, source=canonical_source)
    if canonical_source == "apple" and original_transaction_id:
        query = query.filter_by(
            environment=environment,
            original_transaction_id=original_transaction_id,
        )
    elif canonical_source == "stripe" and external_subscription_id:
        query = query.filter_by(external_subscription_id=external_subscription_id)

    subscription = query.order_by(Subscription.id.desc()).first()
    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            source=canonical_source,
            environment=environment,
            product_id=product_id,
            original_transaction_id=original_transaction_id,
            latest_transaction_id=latest_transaction_id,
            external_subscription_id=external_subscription_id,
            status=status,
            expires_at=expires_at,
            raw_last_verified_at=raw_last_verified_at,
        )
    else:
        subscription.environment = environment
        subscription.product_id = product_id
        subscription.original_transaction_id = original_transaction_id or subscription.original_transaction_id
        subscription.latest_transaction_id = latest_transaction_id or subscription.latest_transaction_id
        subscription.external_subscription_id = external_subscription_id or subscription.external_subscription_id
        subscription.status = status
        subscription.expires_at = expires_at
        subscription.raw_last_verified_at = raw_last_verified_at
        subscription.updated_at = now

    db.session.add(subscription)
    db.session.flush()
    return subscription


def _expire_user(user: User) -> bool:
    """Mark non-admin user expired/inactive. Returns True when mutated."""
    changed = False
    if not user.is_global_admin and user.is_active:
        user.is_active = False
        changed = True
    return changed


def apply_subscription_status(
    user: User,
    *,
    status: str,
    source: str,
    subscription_id: str | None = None,
    expiry: datetime | None = None,
    activate: bool = True,
    commit: bool = True,
) -> None:
    """Apply a subscription mutation and persist audit log entry."""
    old_active = bool(user.is_active)

    if status not in VALID_SUBSCRIPTION_STATUSES:
        raise ValueError(f"Invalid subscription status: {status}")

    user.is_account_owner = True
    user.owner_user_id = None
    user.account_owner_id = None
    user.admin = True

    if user.is_global_admin:
        user.is_active = True
    elif activate:
        user.is_active = True
    elif status == SUB_EXPIRED:
        user.is_active = False

    db.session.add(user)
    if commit:
        db.session.commit()
    logger.info(
        "Subscription change user_id=%s status=%s->%s active=%s->%s source=%s sub_id=%s expiry=%s",
        user.id,
        "n/a",
        status,
        old_active,
        user.is_active,
        source,
        subscription_id,
        expiry,
    )


def enforce_user_access(user: User | None) -> bool:
    """Validate account activity and subscription status.

    Returns True when user should retain access, False otherwise.
    """
    if user is None:
        return False
    if user.is_global_admin:
        if not user.is_active:
            user.is_active = True
            db.session.commit()
        return True

    if not payments_enabled():
        return bool(user.is_active)

    owner = owner_for_user(user)
    if owner is None:
        return False

    if owner.is_global_admin:
        changed = False
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            db.session.commit()
        return True

    # Reviewer accounts (used for App Store review) bypass subscription
    # enforcement and remain active.
    if getattr(owner, "is_review_user", False):
        changed = False
        if not owner.is_active:
            owner.is_active = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            db.session.commit()
        return True

    if subscription_is_current(owner):
        changed = False
        if not owner.is_global_admin and not owner.is_active:
            owner.is_active = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            db.session.commit()
        return True

    changed = _expire_user(owner)

    # Guests inherit owner status; mark inactive for consistency in admin UIs.
    guests = User.query.filter(
        (User.account_owner_id == owner.id) | (User.owner_user_id == owner.id)
    ).all()
    for guest in guests:
        if guest.is_active:
            guest.is_active = False
            changed = True

    if changed:
        db.session.commit()
        logger.info("Access denied due to expired subscription owner_user_id=%s", owner.id)

    return False
