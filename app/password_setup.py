"""Password setup token and onboarding helpers for payment-created users."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

from app import db
from app.models import PasswordSetupToken, User, UserToken

DEFAULT_PASSWORD_SETUP_TTL_MINUTES = 60
PASSWORD_SETUP_ROUTE = "/auth/set-password"


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_password_setup_ttl_minutes() -> int:
    configured = current_app.config.get("PASSWORD_SETUP_TOKEN_TTL_MINUTES", DEFAULT_PASSWORD_SETUP_TTL_MINUTES)
    try:
        ttl = int(configured)
    except (TypeError, ValueError):
        ttl = DEFAULT_PASSWORD_SETUP_TTL_MINUTES
    return max(5, ttl)


def build_password_setup_url(raw_token: str) -> str:
    frontend_base = (current_app.config.get("FRONTEND_BASE_URL") or "").strip()
    normalized_base = frontend_base.rstrip("/")
    if not normalized_base:
        raise RuntimeError("FRONTEND_BASE_URL must be configured for password setup links")
    return f"{normalized_base}{PASSWORD_SETUP_ROUTE}/{raw_token}"


def create_password_setup_token(user: User) -> tuple[str, PasswordSetupToken]:
    raw_token = secrets.token_urlsafe(32)
    token_record = PasswordSetupToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=_utc_now_naive() + timedelta(minutes=get_password_setup_ttl_minutes()),
    )
    db.session.add(token_record)
    db.session.commit()
    return raw_token, token_record


def consume_password_setup_token(raw_token: str) -> User | None:
    token_record = PasswordSetupToken.query.filter_by(token_hash=hash_token(raw_token)).first()
    if token_record is None:
        return None

    now = _utc_now_naive()
    if token_record.used_at is not None or token_record.expires_at <= now:
        return None

    user = db.session.get(User, token_record.user_id)
    if user is None:
        return None

    token_record.used_at = now
    # Revoke active API tokens so password setup starts from clean auth state.
    UserToken.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.commit()
    return user
