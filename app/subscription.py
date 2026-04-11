"""Subscription and account-activation helpers.

This module centralises payment gating so both web sessions and API requests
apply the same account-owner and guest-user rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from flask import current_app

from app import db
from app.models import User


logger = logging.getLogger(__name__)

SUB_ACTIVE = "active"
SUB_INACTIVE = "inactive"
SUB_TRIAL = "trial"
SUB_EXPIRED = "expired"


VALID_SUBSCRIPTION_STATUSES = {SUB_ACTIVE, SUB_INACTIVE, SUB_TRIAL, SUB_EXPIRED}


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
    if user.subscription_status not in {SUB_ACTIVE, SUB_TRIAL}:
        return False
    if user.subscription_expiry is None:
        return True

    expiry = user.subscription_expiry
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry >= datetime.now(timezone.utc)


def _expire_user(user: User) -> bool:
    """Mark non-admin user expired/inactive. Returns True when mutated."""
    changed = False
    if user.subscription_status != SUB_EXPIRED:
        user.subscription_status = SUB_EXPIRED
        changed = True
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
) -> None:
    """Apply a subscription mutation and persist audit log entry."""
    old_status = user.subscription_status
    old_active = bool(user.is_active)

    if status not in VALID_SUBSCRIPTION_STATUSES:
        raise ValueError(f"Invalid subscription status: {status}")

    user.subscription_status = status
    user.subscription_source = source
    user.subscription_id = subscription_id
    user.subscription_expiry = expiry
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
    db.session.commit()
    logger.info(
        "Subscription change user_id=%s status=%s->%s active=%s->%s source=%s sub_id=%s expiry=%s",
        user.id,
        old_status,
        user.subscription_status,
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
