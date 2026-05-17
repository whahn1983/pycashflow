"""Plaid Balance integration service layer.

Encapsulates all Plaid SDK interactions so routes/templates never call Plaid
directly. Stores only the minimum connection metadata required to call
/accounts/balance/get for a single depository account per user.

This module never returns Plaid secrets, access tokens, or raw Plaid response
payloads to callers, and it never logs them either.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

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
    try:
        body = getattr(api_exception, "body", None)
        if body:
            import json as _json

            data = _json.loads(body) if isinstance(body, (str, bytes)) else body
            rid = data.get("request_id") if isinstance(data, dict) else None
            if rid:
                return str(rid)
    except Exception:  # noqa: BLE001 - never let logging break the flow
        return None
    return None


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
        request_kwargs["redirect_uri"] = redirect_uri

    try:
        client = _plaid_client()
        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
    except ApiException as exc:
        logger.warning(
            "Plaid link_token_create failed for user %s (request_id=%s)",
            user.id,
            _plaid_request_id(exc),
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
        logger.warning(
            "Plaid public_token exchange failed for user %s (request_id=%s)",
            user.id,
            _plaid_request_id(exc),
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
        plaid_account_id=str(selected.get("id") or ""),
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


def remove_plaid_connection_for_user(user) -> bool:
    """Remove the active Plaid connection for ``user``. Returns True if removed."""
    conn = get_active_connection(user)
    if conn is None:
        return False

    # Best-effort call to /item/remove; never propagate raw errors to caller.
    if plaid_is_configured():
        from plaid.exceptions import ApiException
        from plaid.model.item_remove_request import ItemRemoveRequest

        try:
            access_token = decrypt_password(conn.encrypted_access_token)
            client = _plaid_client()
            client.item_remove(ItemRemoveRequest(access_token=access_token))
        except ApiException as exc:
            logger.warning(
                "Plaid item_remove failed for user %s (request_id=%s); deleting local record anyway",
                user.id,
                _plaid_request_id(exc),
            )
        except Exception:
            logger.exception(
                "Unexpected error calling Plaid item_remove for user %s; deleting local record anyway",
                user.id,
            )

    db.session.delete(conn)
    db.session.commit()
    return True


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
    from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
    from plaid.model.accounts_balance_get_request_options import (
        AccountsBalanceGetRequestOptions,
    )

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

    try:
        client = _plaid_client()
        request = AccountsBalanceGetRequest(
            access_token=access_token,
            options=AccountsBalanceGetRequestOptions(account_ids=[conn.plaid_account_id]),
        )
        response = client.accounts_balance_get(request)
    except ApiException as exc:
        logger.warning(
            "Plaid accounts_balance_get failed for user %s (request_id=%s)",
            user.id,
            _plaid_request_id(exc),
        )
        _record_sync_status(conn, "plaid_api_error", "Plaid balance request failed.")
        db.session.commit()
        result = {"status": "error", "reason": "plaid_api_error"}
        if cache is not None:
            cache[user.id] = result
        return result
    except Exception:
        logger.exception("Unexpected error calling Plaid balance API for user %s", user.id)
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
