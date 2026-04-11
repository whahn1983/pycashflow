"""Bearer-token authentication utilities for the API blueprint.

Usage
-----
Decorate API route handlers with ``@api_login_required``:

    from app.api.auth_utils import api_login_required, get_api_user

    @api.route('/example')
    @api_login_required
    def example():
        user = get_api_user()
        ...

Authentication order (per request)
-----------------------------------
1. ``Authorization: Bearer <token>`` header → validated against ``UserToken``
   table; if valid, the associated ``User`` is placed in ``flask.g``.
2. Flask-Login session cookie → ``current_user`` is already populated by
   Flask-Login's session loader; accepted for read-only convenience from
   browser sessions (e.g. same-origin API calls from the web app).

Token lifecycle
---------------
- Tokens are generated with ``secrets.token_urlsafe(32)`` (256 bits).
- Only the SHA-256 hash is stored; the raw token is returned once.
- Default TTL: 30 days.  Expired tokens are rejected and can be purged.

Import note
-----------
``db`` and ``UserToken`` are imported at module level (not inside functions)
so that the real objects are captured when the app is first created — before
any test stubs can replace ``sys.modules['app.models']``.  This is consistent
with the pattern established in ``tests/conftest.py``.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import g, request
from flask_login import current_user

# Module-level imports: captured at app-creation time, before test stubs.
from app import db
from app.models import UserToken
from app.subscription import enforce_user_access

from .errors import unauthorized

# Default token lifetime
_TOKEN_TTL_DAYS = 30


# ── Token helpers ─────────────────────────────────────────────────────────────

def generate_raw_token() -> str:
    """Return a new URL-safe random token (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of *raw_token*."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_token_for_user(user) -> tuple[str, object]:
    """Persist a new ``UserToken`` for *user* and return ``(raw_token, record)``.

    The raw token is NOT stored — only its hash.  Callers must return the
    raw token to the client immediately; it cannot be recovered later.
    """
    raw = generate_raw_token()
    record = UserToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=_TOKEN_TTL_DAYS),
    )
    db.session.add(record)
    db.session.commit()
    return raw, record


def delete_token(raw_token: str) -> bool:
    """Delete the ``UserToken`` matching *raw_token*.  Returns ``True`` if found."""
    record = UserToken.query.filter_by(token_hash=hash_token(raw_token)).first()
    if record:
        db.session.delete(record)
        db.session.commit()
        return True
    return False


# ── Request-level token validation ────────────────────────────────────────────

def _load_user_from_bearer() -> object | None:
    """Extract and validate a Bearer token from the request.

    Returns the associated ``User`` on success, or ``None``.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    raw_token = auth_header[7:].strip()
    if not raw_token:
        return None

    record = UserToken.query.filter_by(token_hash=hash_token(raw_token)).first()
    if record is None:
        return None
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    return record.user


def get_api_user():
    """Return the authenticated user for the current API request.

    Prefers the Bearer-token user stored in ``flask.g``; falls back to
    Flask-Login's ``current_user`` for session-authenticated requests.
    Returns ``None`` if neither is authenticated.
    """
    api_user = getattr(g, "api_user", None)
    if api_user is not None:
        return api_user
    if current_user.is_authenticated:
        return current_user._get_current_object()
    return None


# ── Decorator ─────────────────────────────────────────────────────────────────

def api_login_required(f=None, *, require_bearer: bool = False, enforce_active: bool = True):
    """Require authentication via Bearer token or active Flask-Login session.

    On success, the authenticated user is available via ``get_api_user()``.
    On failure, returns a 401 JSON error.
    """
    def _decorate(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            # 1. Bearer token takes precedence
            user = _load_user_from_bearer()
            if user is not None:
                if enforce_active and not enforce_user_access(user):
                    return unauthorized("Invalid credentials or account is not active")
                g.api_user = user
                return func(*args, **kwargs)

            # 2. Optional session cookie fallback (Flask-Login)
            if not require_bearer and current_user.is_authenticated:
                session_user = current_user._get_current_object()
                if enforce_active and not enforce_user_access(session_user):
                    return unauthorized("Invalid credentials or account is not active")
                g.api_user = session_user
                return func(*args, **kwargs)

            if require_bearer:
                return unauthorized("Bearer token required")
            return unauthorized()

        return decorated

    # Supports both @api_login_required and keyword-argument variants.
    if f is None:
        return _decorate
    return _decorate(f)
