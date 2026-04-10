"""API v1 authentication routes."""

from datetime import datetime, timedelta, timezone
from threading import Lock

from flask import current_app, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash

from app import limiter, db
from app.models import User, UserToken
from app.auth import _DUMMY_HASH
from app.totp_utils import decrypt_totp_secret, verify_totp, verify_and_consume_backup_code

from app.api import api
from app.api.auth_utils import (
    api_login_required,
    create_token_for_user,
    delete_token,
    get_api_user,
    hash_token,
)
from app.api.errors import unauthorized, validation_error, forbidden
from app.api.responses import api_ok
from app.api.serializers import serialize_user


_TWOFA_CHALLENGE_MAX_AGE_SECONDS = 300
_CONSUMED_TWOFA_CHALLENGES: dict[str, datetime] = {}
_CONSUMED_TWOFA_CHALLENGES_LOCK = Lock()


def _challenge_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="api-login-2fa")


def _purge_expired_consumed_challenges(now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    expired = [
        token
        for token, expires_at in _CONSUMED_TWOFA_CHALLENGES.items()
        if expires_at <= now
    ]
    for token in expired:
        _CONSUMED_TWOFA_CHALLENGES.pop(token, None)


def _is_twofa_challenge_consumed(challenge: str) -> bool:
    with _CONSUMED_TWOFA_CHALLENGES_LOCK:
        _purge_expired_consumed_challenges()
        return challenge in _CONSUMED_TWOFA_CHALLENGES


def _try_mark_twofa_challenge_consumed(challenge: str) -> bool:
    now = datetime.now(timezone.utc)
    with _CONSUMED_TWOFA_CHALLENGES_LOCK:
        _purge_expired_consumed_challenges(now)
        if challenge in _CONSUMED_TWOFA_CHALLENGES:
            return False
        _CONSUMED_TWOFA_CHALLENGES[challenge] = now + timedelta(
            seconds=_TWOFA_CHALLENGE_MAX_AGE_SECONDS
        )
        return True


def _build_twofa_challenge(user: User) -> str:
    payload = {
        "uid": user.id,
        "email": user.email,
        "nonce": hash_token(f"{user.id}:{datetime.now(timezone.utc).isoformat()}"),
    }
    return _challenge_serializer().dumps(payload)


def _verify_twofa_challenge(challenge: str) -> User | None:
    if _is_twofa_challenge_consumed(challenge):
        return None

    try:
        payload = _challenge_serializer().loads(
            challenge,
            max_age=_TWOFA_CHALLENGE_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None

    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        return None
    return db.session.get(User, user_id)


@api.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute", exempt_when=lambda: current_app.testing)
def api_login():
    body = request.get_json(silent=True) or {}

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

    candidate_hash = user.password if user else _DUMMY_HASH
    password_ok = check_password_hash(candidate_hash, password)

    if not password_ok or user is None or not user.is_active:
        return unauthorized("Invalid credentials or account is not active")

    if user.twofa_enabled:
        return api_ok({
            "twofa_required": True,
            "challenge": _build_twofa_challenge(user),
            "user": serialize_user(user),
        })

    raw_token, _record = create_token_for_user(user)

    return api_ok({
        "token": raw_token,
        "user": serialize_user(user),
    })


@api.route("/auth/login/2fa", methods=["POST"])
@limiter.limit("10 per minute", exempt_when=lambda: current_app.testing)
def api_login_2fa():
    body = request.get_json(silent=True) or {}
    errors: dict = {}
    challenge_raw = body.get("challenge")
    challenge = challenge_raw.strip() if isinstance(challenge_raw, str) else ""
    if not challenge:
        errors["challenge"] = "Challenge is required"
    code_raw = body.get("code")
    code = code_raw.strip() if isinstance(code_raw, str) else ""
    if not code:
        errors["code"] = "Code is required"
    if errors:
        return validation_error(errors)

    user = _verify_twofa_challenge(challenge)
    if user is None or not user.is_active or not user.twofa_enabled:
        return unauthorized("Invalid or expired 2FA challenge")

    submitted = code
    twofa_ok = False

    try:
        secret = decrypt_totp_secret(user.twofa_secret) if user.twofa_secret else ""
    except Exception:
        secret = ""

    if secret:
        twofa_ok = verify_totp(secret, submitted)

    if not twofa_ok:
        twofa_ok = verify_and_consume_backup_code(user, submitted)

    if not twofa_ok:
        return unauthorized("Invalid verification code")

    if not _try_mark_twofa_challenge_consumed(challenge):
        return unauthorized("Invalid or expired 2FA challenge")
    raw_token, _record = create_token_for_user(user)
    return api_ok({"token": raw_token, "user": serialize_user(user)})


@api.route("/auth/refresh", methods=["POST"])
@api_login_required(require_bearer=True)
def api_refresh_token():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return unauthorized("Bearer token required for refresh")

    raw_token = auth_header[7:].strip()
    if not raw_token:
        return unauthorized("Bearer token required for refresh")

    delete_token(raw_token)
    new_raw_token, _record = create_token_for_user(get_api_user())
    return api_ok({"token": new_raw_token, "user": serialize_user(get_api_user())})


@api.route("/auth/logout", methods=["POST"])
@api_login_required(require_bearer=True)
def api_logout():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
        delete_token(raw_token)

    return api_ok({"message": "Logged out"})


@api.route("/auth/password", methods=["PUT"])
@api_login_required(require_bearer=True)
def api_change_password():
    user = get_api_user()
    if not user.admin:
        return forbidden("Guest users cannot change account passwords")

    body = request.get_json(silent=True) or {}
    errors: dict = {}
    if not body.get("current_password", ""):
        errors["current_password"] = "Current password is required"
    if not body.get("new_password", ""):
        errors["new_password"] = "New password is required"
    if body.get("new_password", "") and len(body["new_password"]) < 8:
        errors["new_password"] = "New password must be at least 8 characters"
    if errors:
        return validation_error(errors)

    if not check_password_hash(user.password, body["current_password"]):
        return unauthorized("Current password is incorrect")

    user.password = generate_password_hash(body["new_password"], method="scrypt")
    UserToken.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.commit()
    return api_ok({"message": "Password updated"})


@api.route("/auth/me", methods=["GET"])
@api_login_required
def api_me():
    return api_ok(serialize_user(get_api_user()))
