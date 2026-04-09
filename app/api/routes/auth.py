"""API v1 authentication routes.

Endpoints
---------
POST   /api/v1/auth/login    Email + password → bearer token
POST   /api/v1/auth/logout   Invalidate the current bearer token
GET    /api/v1/auth/me       Current authenticated user profile

These endpoints are CSRF-exempt (the entire ``api`` blueprint is exempt).
Bearer tokens must be sent as ``Authorization: Bearer <token>`` on
subsequent requests.

Import note
-----------
``User`` and ``_DUMMY_HASH`` are imported at module level so they reference
the real objects captured during app creation, before test stubs can replace
``sys.modules['app.models']`` or ``sys.modules['app.auth']``.
"""

from flask import current_app, request
from werkzeug.security import check_password_hash

from app import limiter

# Module-level imports: bound to real objects at app-creation time.
from app.models import User
from app.auth import _DUMMY_HASH

from app.api import api
from app.api.auth_utils import (
    api_login_required,
    create_token_for_user,
    delete_token,
    get_api_user,
)
from app.api.errors import unauthorized, validation_error
from app.api.responses import api_ok
from app.api.serializers import serialize_user


# ── POST /api/v1/auth/login ───────────────────────────────────────────────────

@api.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute", exempt_when=lambda: current_app.testing)
def api_login():
    """Authenticate with email + password and receive a bearer token.

    Request body (JSON):
        { "email": "user@example.com", "password": "s3cr3t" }

    Response 200:
        { "data": { "token": "<raw_token>", "user": { ... } } }

    Response 422:
        Missing or empty ``email`` / ``password`` field.

    Response 401:
        Credentials invalid or account inactive.
    """
    body = request.get_json(silent=True) or {}

    # Validate presence of required fields
    errors: dict = {}
    if not body.get("email", "").strip():
        errors["email"] = "Email is required"
    if not body.get("password", ""):
        errors["password"] = "Password is required"
    if errors:
        return validation_error(errors)

    email = body["email"].strip().lower()
    password = body["password"]

    user = User.query.filter_by(email=email).first()

    # Constant-time check: always run check_password_hash even when the user
    # is not found, so response time does not reveal whether the email exists.
    candidate_hash = user.password if user else _DUMMY_HASH
    password_ok = check_password_hash(candidate_hash, password)

    # 2FA check is intentionally in the same condition to avoid leaking
    # whether the password was correct (credential-validation oracle).
    if not password_ok or user is None or not user.is_active or user.twofa_enabled:
        return unauthorized("Invalid credentials or account is not active")

    raw_token, _record = create_token_for_user(user)

    return api_ok({
        "token": raw_token,
        "user": serialize_user(user),
    })


# ── POST /api/v1/auth/logout ──────────────────────────────────────────────────

@api.route("/auth/logout", methods=["POST"])
@api_login_required
def api_logout():
    """Invalidate the bearer token used in this request.

    If the request was authenticated via session cookie (no Bearer header),
    the session is not modified — the caller should clear it via the
    existing ``/logout`` route.

    Response 200:
        { "data": { "message": "Logged out" } }
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
        delete_token(raw_token)

    return api_ok({"message": "Logged out"})


# ── GET /api/v1/auth/me ───────────────────────────────────────────────────────

@api.route("/auth/me", methods=["GET"])
@api_login_required
def api_me():
    """Return the authenticated user's public profile.

    Response 200:
        { "data": { "id": 1, "email": "...", "name": "...", ... } }
    """
    return api_ok(serialize_user(get_api_user()))
