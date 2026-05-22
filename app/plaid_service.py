"""Plaid Balance integration service layer.

Encapsulates all Plaid SDK interactions so routes/templates never call Plaid
directly. Stores only the minimum connection metadata required to call
/accounts/balance/get for a single depository account per user.

This module never returns Plaid secrets, access tokens, or raw Plaid response
payloads to callers, and it never logs them either.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from flask import current_app, g
from sqlalchemy import desc

from app import db
from app.crypto_utils import encrypt_password, decrypt_password
from app.models import Balance, PlaidConnection

logger = logging.getLogger(__name__)


# Plaid Link products that are valid for create_link_token; "balance" is not.
_INVALID_LINK_PRODUCTS = {"balance"}

# Only depository cash accounts are appropriate for cash-flow forecasting.
_ALLOWED_ACCOUNT_TYPES = {"depository"}
_ALLOWED_ACCOUNT_SUBTYPES = {
    "checking",
    "savings",
    "cash management",
    "money market",
    "ebt",
    "hsa",
    "paypal",
    "prepaid",
}

_BALANCE_SOURCE_AVAILABLE = "plaid_available_balance"
_BALANCE_SOURCE_CURRENT_FALLBACK = "plaid_current_balance_fallback"
_BALANCE_SOURCE_REALTIME_AVAILABLE = "plaid_realtime_available_balance"
_BALANCE_SOURCE_REALTIME_CURRENT_FALLBACK = "plaid_realtime_current_balance_fallback"

# Plaid charges per /accounts/balance/get call, so the manual real-time
# refresh is rate-limited to once every 24 hours per connection.
REALTIME_BALANCE_COOLDOWN_SECONDS = 24 * 60 * 60


class PlaidServiceError(Exception):
    """Raised for any Plaid-related failure surfaced to a route.

    The ``user_message`` is safe to show to end users (no Plaid secrets,
    no raw payloads, no tokens). ``code`` is a stable slug for callers.
    """

    def __init__(self, user_message: str, code: str = "plaid_error", status: int = 400):
        super().__init__(user_message)
        self.user_message = user_message
        self.code = code
        self.status = status


# ── Configuration ────────────────────────────────────────────────────────────


def _config(key: str) -> str:
    return (current_app.config.get(key) or "").strip()


def plaid_is_configured() -> bool:
    """Return True only when all required Plaid config values are present.

    Does NOT make any network call. Required values:
    PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV, PLAID_PRODUCTS.
    """
    if not current_app:
        return False
    return all(_config(k) for k in ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV", "PLAID_PRODUCTS"))


def get_configured_products() -> list[str]:
    raw = _config("PLAID_PRODUCTS")
    products = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in products if p not in _INVALID_LINK_PRODUCTS]


def get_configured_country_codes() -> list[str]:
    raw = _config("PLAID_COUNTRY_CODES") or "US"
    return [c.strip().upper() for c in raw.split(",") if c.strip()]


# ── Plaid SDK helpers ────────────────────────────────────────────────────────


def _plaid_environment_host():
    """Map PLAID_ENV string to the SDK's environment host constant."""
    from plaid.configuration import Environment

    env = _config("PLAID_ENV").lower()
    if env == "production":
        return Environment.Production
    if env in ("development", "dev"):
        # Plaid SDK v39 removed the dedicated Development host; fall back to
        # Sandbox for unrecognized values so we never hit Production unintentionally.
        return getattr(Environment, "Development", Environment.Sandbox)
    return Environment.Sandbox


def _plaid_client():
    """Build an authenticated Plaid API client from current config."""
    from plaid.api import plaid_api
    from plaid.api_client import ApiClient
    from plaid.configuration import Configuration

    config = Configuration(
        host=_plaid_environment_host(),
        api_key={
            "clientId": _config("PLAID_CLIENT_ID"),
            "secret": _config("PLAID_SECRET"),
        },
    )
    return plaid_api.PlaidApi(ApiClient(config))


def _plaid_request_id(api_exception) -> str | None:
    """Extract Plaid request_id from an ApiException body for safe logging."""
    info = _plaid_error_info(api_exception)
    return info.get("request_id")


def _plaid_error_info(api_exception) -> dict:
    """Extract safe diagnostic fields from a Plaid ApiException body.

    Returns a dict with any of ``request_id``, ``error_type``, ``error_code``,
    ``error_message`` that were present. These fields are documented as the
    error envelope Plaid returns and never contain secrets or access tokens,
    so they are safe to write to application logs.
    """
    info: dict = {}
    try:
        body = getattr(api_exception, "body", None)
        if not body:
            return info
        import json as _json

        data = _json.loads(body) if isinstance(body, (str, bytes)) else body
        if not isinstance(data, dict):
            return info
        for key in ("request_id", "error_type", "error_code", "error_message"):
            val = data.get(key)
            if val:
                info[key] = str(val)
    except Exception:  # noqa: BLE001 - never let logging break the flow
        return info
    return info


# ── Connection lookup ────────────────────────────────────────────────────────


def get_active_connection(user) -> PlaidConnection | None:
    if not user or not getattr(user, "id", None):
        return None
    return (
        PlaidConnection.query.filter_by(user_id=user.id, is_active=True)
        .order_by(desc(PlaidConnection.id))
        .first()
    )


def get_plaid_connection_status(user) -> dict:
    """Return a safe, JSON-friendly status payload for the settings UI."""
    configured = plaid_is_configured()
    payload: dict = {"configured": configured, "connected": False, "connection": None}
    if not configured:
        return payload

    conn = get_active_connection(user)
    if conn is None:
        return payload

    payload["connected"] = True
    payload["connection"] = {
        "institution_name": conn.institution_name,
        "account_name": conn.account_name,
        "account_mask": conn.account_mask,
        "account_type": conn.account_type,
        "account_subtype": conn.account_subtype,
        "iso_currency_code": conn.iso_currency_code,
        "last_balance_sync_at": (
            conn.last_balance_sync_at.replace(microsecond=0).isoformat() + "Z"
            if conn.last_balance_sync_at
            else None
        ),
        "last_sync_status": conn.last_sync_status,
        "last_sync_error": conn.last_sync_error,
        "last_realtime_balance_at": (
            conn.last_realtime_balance_at.replace(microsecond=0).isoformat() + "Z"
            if conn.last_realtime_balance_at
            else None
        ),
        "realtime_refresh_retry_after_seconds": _seconds_until_realtime_refresh(conn),
    }
    return payload


# ── Link token ───────────────────────────────────────────────────────────────


def create_link_token_for_user(user) -> str:
    """Build a Plaid Link token for the current user. Returns the link_token."""
    if not plaid_is_configured():
        raise PlaidServiceError(
            "Plaid is not configured. Set PLAID_CLIENT_ID, PLAID_SECRET, "
            "PLAID_ENV, and PLAID_PRODUCTS.",
            code="plaid_not_configured",
            status=400,
        )

    from plaid.exceptions import ApiException
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products

    products = [Products(p) for p in get_configured_products()]
    if not products:
        raise PlaidServiceError(
            "Plaid is not configured with a valid PLAID_PRODUCTS value.",
            code="plaid_not_configured",
            status=400,
        )
    country_codes = [CountryCode(c) for c in get_configured_country_codes()]

    request_kwargs = dict(
        user=LinkTokenCreateRequestUser(client_user_id=str(user.id)),
        client_name="PyCashFlow",
        products=products,
        country_codes=country_codes,
        language="en",
    )
    redirect_uri = _config("PLAID_REDIRECT_URI")
    if redirect_uri:
        # Plaid rejects redirect_uri values that include a query string or
        # fragment ("redirect_uri cannot include query"). The dashboard-
        # registered URI is the bare path; OAuth-return params are appended
        # by Plaid on the way back, not configured here.
        parts = urlsplit(redirect_uri)
        request_kwargs["redirect_uri"] = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", "")
        )

    try:
        client = _plaid_client()
        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
    except ApiException as exc:
        info = _plaid_error_info(exc)
        logger.warning(
            "Plaid link_token_create failed for user %s "
            "(request_id=%s, error_type=%s, error_code=%s, error_message=%s, "
            "env=%s, products=%s, country_codes=%s, redirect_uri_set=%s)",
            user.id,
            info.get("request_id"),
            info.get("error_type"),
            info.get("error_code"),
            info.get("error_message"),
            _config("PLAID_ENV"),
            ",".join(get_configured_products()),
            ",".join(get_configured_country_codes()),
            bool(_config("PLAID_REDIRECT_URI")),
        )
        raise PlaidServiceError(
            "Could not start Plaid Link. Please try again later.",
            code="plaid_link_failed",
            status=502,
        ) from None
    except Exception:
        logger.exception("Unexpected error creating Plaid link token for user %s", user.id)
        raise PlaidServiceError(
            "Could not start Plaid Link. Please try again later.",
            code="plaid_link_failed",
            status=502,
        ) from None

    return response.link_token


# ── Link client-side event logging ───────────────────────────────────────────


# Whitelisted fields we accept from the client. Plaid documents these as the
# onExit error envelope and metadata; none of them carry credentials, access
# tokens, or balances, so it is safe to write them to server logs.
_LINK_EVENT_ERROR_FIELDS = (
    "error_type",
    "error_code",
    "error_message",
    "display_message",
)
_LINK_EVENT_METADATA_FIELDS = (
    "status",
    "link_session_id",
    "request_id",
    "institution_name",
)


# Strip ASCII control characters (incl. CR/LF) so a client-supplied value
# cannot inject forged log lines when interpolated into a single-line warning.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _scrub_log_value(val: str) -> str:
    return _CONTROL_CHARS_RE.sub(" ", val)[:255]


def _sanitize_link_event_payload(payload: dict) -> dict:
    """Pick only whitelisted, short string fields from a client-supplied payload."""
    safe: dict = {}
    if not isinstance(payload, dict):
        return safe
    err = payload.get("error")
    if isinstance(err, dict):
        for key in _LINK_EVENT_ERROR_FIELDS:
            val = err.get(key)
            if isinstance(val, str) and val:
                safe[key] = _scrub_log_value(val)
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        for key in _LINK_EVENT_METADATA_FIELDS:
            val = meta.get(key)
            if isinstance(val, str) and val:
                safe["metadata_" + key] = _scrub_log_value(val)
    return safe


def log_plaid_link_exit_for_user(user, payload: dict) -> None:
    """Log client-reported Plaid Link exit diagnostics for a user.

    Plaid Link reports failures (especially OAuth handoff problems for real
    banks in production) entirely client-side; the server otherwise sees no
    error. This bridges that gap by accepting a whitelisted subset of the
    onExit ``err`` + ``metadata`` fields and emitting them to the server log.
    """
    safe = _sanitize_link_event_payload(payload or {})
    if not safe:
        logger.warning(
            "Plaid Link exited with no recoverable diagnostics for user %s "
            "(env=%s, products=%s, country_codes=%s, redirect_uri_set=%s)",
            getattr(user, "id", None),
            _config("PLAID_ENV"),
            ",".join(get_configured_products()),
            ",".join(get_configured_country_codes()),
            bool(_config("PLAID_REDIRECT_URI")),
        )
        return
    logger.warning(
        "Plaid Link exit reported by user %s: %s "
        "(env=%s, products=%s, country_codes=%s, redirect_uri_set=%s)",
        getattr(user, "id", None),
        ", ".join("%s=%s" % (k, v) for k, v in safe.items()),
        _config("PLAID_ENV"),
        ",".join(get_configured_products()),
        ",".join(get_configured_country_codes()),
        bool(_config("PLAID_REDIRECT_URI")),
    )


# ── Public token exchange ────────────────────────────────────────────────────


def _pick_single_account_from_metadata(metadata: dict) -> dict | None:
    """Return the single Plaid-Link-selected account, or None if ambiguous."""
    accounts = metadata.get("accounts") if isinstance(metadata, dict) else None
    if not isinstance(accounts, list) or not accounts:
        return None
    if len(accounts) == 1:
        return accounts[0]
    return None


def _validate_account_type(account: dict) -> None:
    acct_type = (account.get("type") or "").lower()
    subtype = (account.get("subtype") or "").lower()
    if acct_type not in _ALLOWED_ACCOUNT_TYPES:
        raise PlaidServiceError(
            "Only depository (checking/savings) accounts are supported.",
            code="plaid_unsupported_account_type",
            status=422,
        )
    if subtype and subtype not in _ALLOWED_ACCOUNT_SUBTYPES:
        raise PlaidServiceError(
            "Only checking/savings depository subtypes are supported.",
            code="plaid_unsupported_account_subtype",
            status=422,
        )


def exchange_public_token_for_user(user, public_token: str, metadata: dict) -> PlaidConnection:
    """Exchange a Link public_token and persist minimal connection metadata."""
    if not plaid_is_configured():
        raise PlaidServiceError(
            "Plaid is not configured.",
            code="plaid_not_configured",
            status=400,
        )

    if not public_token or not isinstance(public_token, str):
        raise PlaidServiceError(
            "Missing Plaid public_token.",
            code="validation_error",
            status=422,
        )

    if get_active_connection(user) is not None:
        raise PlaidServiceError(
            "A Plaid account is already connected. Remove it before connecting a new one.",
            code="plaid_already_connected",
            status=409,
        )

    metadata = metadata if isinstance(metadata, dict) else {}
    selected = _pick_single_account_from_metadata(metadata)
    if selected is None:
        raise PlaidServiceError(
            "Please select a single Plaid account, or enable Plaid Account Select "
            "for a single account in your Plaid dashboard.",
            code="plaid_select_one_account",
            status=422,
        )

    _validate_account_type(selected)

    account_id_raw = selected.get("id")
    account_id = account_id_raw.strip() if isinstance(account_id_raw, str) else ""
    if not account_id:
        raise PlaidServiceError(
            "Plaid did not return an account id for the selected account.",
            code="plaid_missing_account_id",
            status=422,
        )

    from plaid.exceptions import ApiException
    from plaid.model.item_public_token_exchange_request import (
        ItemPublicTokenExchangeRequest,
    )

    try:
        client = _plaid_client()
        exchange = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
    except ApiException as exc:
        info = _plaid_error_info(exc)
        logger.warning(
            "Plaid public_token exchange failed for user %s "
            "(request_id=%s, error_type=%s, error_code=%s, error_message=%s)",
            user.id,
            info.get("request_id"),
            info.get("error_type"),
            info.get("error_code"),
            info.get("error_message"),
        )
        raise PlaidServiceError(
            "Could not finalize Plaid connection. Please try again.",
            code="plaid_exchange_failed",
            status=502,
        ) from None
    except Exception:
        logger.exception("Unexpected error exchanging Plaid public token for user %s", user.id)
        raise PlaidServiceError(
            "Could not finalize Plaid connection. Please try again.",
            code="plaid_exchange_failed",
            status=502,
        ) from None

    access_token = exchange.access_token
    item_id = exchange.item_id

    institution = metadata.get("institution") if isinstance(metadata, dict) else None
    institution_id = institution.get("institution_id") if isinstance(institution, dict) else None
    institution_name = institution.get("name") if isinstance(institution, dict) else None

    encrypted = encrypt_password(access_token)
    conn = PlaidConnection(
        user_id=user.id,
        encrypted_access_token=encrypted,
        plaid_item_id=str(item_id),
        plaid_account_id=account_id,
        institution_id=str(institution_id) if institution_id else None,
        institution_name=str(institution_name) if institution_name else None,
        account_name=(selected.get("name") or None),
        account_mask=(selected.get("mask") or None),
        account_type=(selected.get("type") or None),
        account_subtype=(selected.get("subtype") or None),
        iso_currency_code=(selected.get("iso_currency_code") or None),
        is_active=True,
    )
    db.session.add(conn)
    db.session.commit()
    return conn


# ── Remove connection ────────────────────────────────────────────────────────


def _detach_plaid_item(conn: PlaidConnection) -> None:
    """Best-effort call to Plaid's /item/remove for ``conn``. Never raises.

    Calling /item/remove ends the Plaid Transactions subscription for the
    underlying Item; skipping this step means Plaid keeps billing us for the
    Item even after the local record is gone.
    """
    if not plaid_is_configured():
        return

    from plaid.exceptions import ApiException
    from plaid.model.item_remove_request import ItemRemoveRequest

    try:
        access_token = decrypt_password(conn.encrypted_access_token)
        client = _plaid_client()
        client.item_remove(ItemRemoveRequest(access_token=access_token))
    except ApiException as exc:
        info = _plaid_error_info(exc)
        logger.warning(
            "Plaid item_remove failed for user %s connection %s "
            "(request_id=%s, error_type=%s, error_code=%s, error_message=%s); "
            "deleting local record anyway",
            conn.user_id,
            conn.id,
            info.get("request_id"),
            info.get("error_type"),
            info.get("error_code"),
            info.get("error_message"),
        )
    except Exception:
        logger.exception(
            "Unexpected error calling Plaid item_remove for user %s connection %s; "
            "deleting local record anyway",
            conn.user_id,
            conn.id,
        )


def remove_plaid_connection_for_user(user) -> bool:
    """Remove the active Plaid connection for ``user``. Returns True if removed."""
    conn = get_active_connection(user)
    if conn is None:
        return False

    _detach_plaid_item(conn)
    db.session.delete(conn)
    db.session.commit()
    return True


def remove_plaid_connections_for_user_ids(user_ids, *, commit: bool = False) -> int:
    """Remove every PlaidConnection owned by the given user IDs.

    For each row, best-effort calls Plaid's /item/remove (so we stop being
    billed for the Item's Transactions subscription) and then deletes the
    local record. Returns the number of rows removed. Caller is responsible
    for committing the session unless ``commit=True``.
    """
    if not user_ids:
        return 0

    connections = (
        PlaidConnection.query.filter(PlaidConnection.user_id.in_(list(user_ids))).all()
    )
    for conn in connections:
        _detach_plaid_item(conn)
        db.session.delete(conn)

    if commit and connections:
        db.session.commit()

    return len(connections)


# ── Balance update ───────────────────────────────────────────────────────────


def _today_date() -> date:
    return datetime.today().date()


def _upsert_today_balance(user_id: int, amount: float) -> Balance:
    today = _today_date()
    existing = (
        Balance.query.filter_by(user_id=user_id, date=today)
        .order_by(desc(Balance.id))
        .first()
    )
    if existing is not None:
        existing.amount = amount
        return existing
    row = Balance(user_id=user_id, amount=amount, date=today)
    db.session.add(row)
    return row


def _record_sync_status(conn: PlaidConnection, status: str, error: Optional[str]) -> None:
    conn.last_balance_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.last_sync_status = status[:64] if status else None
    conn.last_sync_error = error[:255] if error else None


def update_plaid_balance_for_user(user) -> dict:
    """Refresh today's PyCashFlow balance from the connected Plaid account.

    Safe to call from the dashboard path: never raises on Plaid/configuration
    errors. Returns a small status dict useful for tests/optional API responses.
    """
    if user is None or not getattr(user, "id", None):
        return {"status": "skipped", "reason": "no_user"}

    if not plaid_is_configured():
        return {"status": "skipped", "reason": "not_configured"}

    # Avoid duplicate Plaid calls within a single request.
    cache = getattr(g, "_plaid_update_cache", None)
    if cache is None:
        cache = {}
        try:
            g._plaid_update_cache = cache
        except RuntimeError:
            cache = None  # outside request context
    if cache is not None and user.id in cache:
        return cache[user.id]

    conn = get_active_connection(user)
    if conn is None:
        result = {"status": "skipped", "reason": "no_connection"}
        if cache is not None:
            cache[user.id] = result
        return result

    from plaid.exceptions import ApiException
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.accounts_get_request_options import AccountsGetRequestOptions

    try:
        access_token = decrypt_password(conn.encrypted_access_token)
    except Exception:
        logger.warning("Could not decrypt Plaid access token for user %s", user.id)
        _record_sync_status(conn, "decrypt_failed", "Stored Plaid token could not be read.")
        db.session.commit()
        result = {"status": "error", "reason": "decrypt_failed"}
        if cache is not None:
            cache[user.id] = result
        return result

    # Use /accounts/get rather than /accounts/balance/get: the latter requires
    # the "balance" product authorization, while /accounts/get is included
    # with "transactions" and returns the same available/current balance
    # fields (refreshed as part of regular transaction sync).
    try:
        client = _plaid_client()
        request = AccountsGetRequest(
            access_token=access_token,
            options=AccountsGetRequestOptions(account_ids=[conn.plaid_account_id]),
        )
        response = client.accounts_get(request)
    except ApiException as exc:
        info = _plaid_error_info(exc)
        logger.warning(
            "Plaid accounts_get failed for user %s "
            "(request_id=%s, error_type=%s, error_code=%s, error_message=%s)",
            user.id,
            info.get("request_id"),
            info.get("error_type"),
            info.get("error_code"),
            info.get("error_message"),
        )
        _record_sync_status(conn, "plaid_api_error", "Plaid balance request failed.")
        db.session.commit()
        result = {"status": "error", "reason": "plaid_api_error"}
        if cache is not None:
            cache[user.id] = result
        return result
    except Exception:
        logger.exception("Unexpected error calling Plaid accounts API for user %s", user.id)
        _record_sync_status(conn, "unexpected_error", "Unexpected Plaid error.")
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        result = {"status": "error", "reason": "unexpected_error"}
        if cache is not None:
            cache[user.id] = result
        return result

    # Pull the matching account from the response.
    target = None
    try:
        accounts = list(response.accounts or [])
    except Exception:
        accounts = []
    for acct in accounts:
        if str(getattr(acct, "account_id", "")) == conn.plaid_account_id:
            target = acct
            break

    if target is None:
        _record_sync_status(
            conn,
            "account_not_found",
            "Connected Plaid account was not in the balance response.",
        )
        db.session.commit()
        result = {"status": "error", "reason": "account_not_found"}
        if cache is not None:
            cache[user.id] = result
        return result

    balances = getattr(target, "balances", None)
    available = getattr(balances, "available", None) if balances is not None else None
    current = getattr(balances, "current", None) if balances is not None else None

    if available is not None:
        balance_value = float(available)
        source = _BALANCE_SOURCE_AVAILABLE
    elif current is not None:
        balance_value = float(current)
        source = _BALANCE_SOURCE_CURRENT_FALLBACK
    else:
        _record_sync_status(
            conn,
            "no_balance_value",
            "Plaid did not return available or current balance.",
        )
        db.session.commit()
        result = {"status": "skipped", "reason": "no_balance_value"}
        if cache is not None:
            cache[user.id] = result
        return result

    _upsert_today_balance(user.id, balance_value)
    _record_sync_status(conn, source, None)
    db.session.commit()
    result = {"status": "ok", "source": source}
    if cache is not None:
        cache[user.id] = result
    return result


def safe_update_plaid_balance_for_user(user) -> None:
    """Wrapper that never raises — for use from dashboard request paths."""
    try:
        update_plaid_balance_for_user(user)
    except Exception:
        logger.exception("Plaid balance update failed for user %s", getattr(user, "id", None))
        try:
            db.session.rollback()
        except Exception:
            pass


# ── Real-time balance refresh (/accounts/balance/get) ────────────────────────


def _seconds_until_realtime_refresh(conn: PlaidConnection) -> int:
    """Return seconds remaining before the next real-time refresh is allowed.

    Zero means a refresh is allowed now. Treat any value > 0 as rate-limited.
    """
    last = conn.last_realtime_balance_at
    if last is None:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed = (now - last).total_seconds()
    remaining = REALTIME_BALANCE_COOLDOWN_SECONDS - int(elapsed)
    return max(remaining, 0)


def realtime_update_plaid_balance_for_user(user) -> dict:
    """Force-refresh today's balance from Plaid's /accounts/balance/get endpoint.

    Plaid charges per call for this product, so callers are rate-limited to one
    successful refresh every ``REALTIME_BALANCE_COOLDOWN_SECONDS`` per
    connection. Returns a status dict; never returns Plaid secrets or raw
    payloads.
    """
    if user is None or not getattr(user, "id", None):
        return {"status": "skipped", "reason": "no_user"}

    if not plaid_is_configured():
        return {"status": "skipped", "reason": "not_configured"}

    conn = get_active_connection(user)
    if conn is None:
        return {"status": "skipped", "reason": "no_connection"}

    retry_after = _seconds_until_realtime_refresh(conn)
    if retry_after > 0:
        return {
            "status": "rate_limited",
            "reason": "cooldown_active",
            "retry_after_seconds": retry_after,
            "last_realtime_balance_at": (
                conn.last_realtime_balance_at.replace(microsecond=0).isoformat() + "Z"
                if conn.last_realtime_balance_at
                else None
            ),
        }

    from plaid.exceptions import ApiException
    from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
    from plaid.model.accounts_balance_get_request_options import (
        AccountsBalanceGetRequestOptions,
    )

    try:
        access_token = decrypt_password(conn.encrypted_access_token)
    except Exception:
        logger.warning(
            "Could not decrypt Plaid access token for user %s (realtime refresh)",
            user.id,
        )
        _record_sync_status(conn, "decrypt_failed", "Stored Plaid token could not be read.")
        db.session.commit()
        return {"status": "error", "reason": "decrypt_failed"}

    try:
        client = _plaid_client()
        request = AccountsBalanceGetRequest(
            access_token=access_token,
            options=AccountsBalanceGetRequestOptions(
                account_ids=[conn.plaid_account_id]
            ),
        )
        response = client.accounts_balance_get(request)
    except ApiException as exc:
        info = _plaid_error_info(exc)
        logger.warning(
            "Plaid accounts_balance_get failed for user %s "
            "(request_id=%s, error_type=%s, error_code=%s, error_message=%s)",
            user.id,
            info.get("request_id"),
            info.get("error_type"),
            info.get("error_code"),
            info.get("error_message"),
        )
        _record_sync_status(
            conn, "plaid_realtime_api_error", "Plaid real-time balance request failed."
        )
        db.session.commit()
        return {"status": "error", "reason": "plaid_api_error"}
    except Exception:
        logger.exception(
            "Unexpected error calling Plaid /accounts/balance/get for user %s", user.id
        )
        _record_sync_status(
            conn, "plaid_realtime_unexpected_error", "Unexpected Plaid error."
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return {"status": "error", "reason": "unexpected_error"}

    target = None
    try:
        accounts = list(response.accounts or [])
    except Exception:
        accounts = []
    for acct in accounts:
        if str(getattr(acct, "account_id", "")) == conn.plaid_account_id:
            target = acct
            break

    if target is None:
        _record_sync_status(
            conn,
            "account_not_found",
            "Connected Plaid account was not in the balance response.",
        )
        db.session.commit()
        return {"status": "error", "reason": "account_not_found"}

    balances = getattr(target, "balances", None)
    available = getattr(balances, "available", None) if balances is not None else None
    current = getattr(balances, "current", None) if balances is not None else None

    if available is not None:
        balance_value = float(available)
        source = _BALANCE_SOURCE_REALTIME_AVAILABLE
    elif current is not None:
        balance_value = float(current)
        source = _BALANCE_SOURCE_REALTIME_CURRENT_FALLBACK
    else:
        # The call still counts against Plaid billing, so record the cooldown
        # to prevent rapid retries even when no usable balance was returned.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        conn.last_realtime_balance_at = now
        _record_sync_status(
            conn,
            "no_balance_value",
            "Plaid did not return available or current balance.",
        )
        db.session.commit()
        return {"status": "skipped", "reason": "no_balance_value"}

    _upsert_today_balance(user.id, balance_value)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.last_realtime_balance_at = now
    _record_sync_status(conn, source, None)
    db.session.commit()
    return {
        "status": "ok",
        "source": source,
        "amount": balance_value,
        "last_realtime_balance_at": now.replace(microsecond=0).isoformat() + "Z",
    }
