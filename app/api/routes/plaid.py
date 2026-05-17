"""API endpoints for the Plaid Balance integration.

Endpoints:
- GET    /api/v1/plaid/status         – is Plaid configured, and is the
                                        current user connected?
- POST   /api/v1/plaid/link-token     – create a Plaid Link token
- POST   /api/v1/plaid/exchange-token – exchange public_token + metadata
- POST   /api/v1/plaid/remove         – disconnect the current user's account
- DELETE /api/v1/plaid/remove         – same as POST /remove
- POST   /api/v1/plaid/update-balance – manual balance refresh trigger

All endpoints require login and operate strictly on the authenticated user.
None of them return access tokens, encrypted tokens, or raw Plaid payloads.
"""

from flask import request

from app.api import api
from app.api.auth_utils import api_login_required, get_api_user
from app.api.errors import api_error
from app.api.responses import api_ok, api_no_content
from app.plaid_service import (
    PlaidServiceError,
    create_link_token_for_user,
    exchange_public_token_for_user,
    get_plaid_connection_status,
    remove_plaid_connection_for_user,
    update_plaid_balance_for_user,
)


def _service_error(exc: PlaidServiceError):
    return api_error(exc.user_message, exc.code, exc.status)


@api.route("/plaid/status", methods=["GET"])
@api_login_required
def api_plaid_status():
    user = get_api_user()
    return api_ok(get_plaid_connection_status(user))


@api.route("/plaid/link-token", methods=["POST"])
@api_login_required
def api_plaid_link_token():
    user = get_api_user()
    try:
        token = create_link_token_for_user(user)
    except PlaidServiceError as exc:
        return _service_error(exc)
    return api_ok({"link_token": token})


@api.route("/plaid/exchange-token", methods=["POST"])
@api_login_required
def api_plaid_exchange_token():
    user = get_api_user()
    body = request.get_json(silent=True) or {}
    public_token = body.get("public_token")
    metadata = body.get("metadata") or {}
    try:
        exchange_public_token_for_user(user, public_token, metadata)
    except PlaidServiceError as exc:
        return _service_error(exc)
    return api_ok(get_plaid_connection_status(user))


@api.route("/plaid/remove", methods=["POST", "DELETE"])
@api_login_required
def api_plaid_remove():
    user = get_api_user()
    remove_plaid_connection_for_user(user)
    return api_no_content()


@api.route("/plaid/update-balance", methods=["POST"])
@api_login_required
def api_plaid_update_balance():
    user = get_api_user()
    try:
        result = update_plaid_balance_for_user(user)
    except Exception:
        return api_error(
            "Could not refresh balance from Plaid.",
            "plaid_error",
            502,
        )
    return api_ok(result)
