"""App Store subscription verification helpers.

Implements Apple App Store Server API authentication (ES256 JWT) and
subscription-state retrieval.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


APPSTORE_PRODUCTION_URL = "https://api.storekit.itunes.apple.com"
APPSTORE_SANDBOX_URL = "https://api.storekit-sandbox.itunes.apple.com"

_ACTIVE_STATUSES = {1, 3, 4}


class AppStoreVerificationError(Exception):
    """Raised when App Store verification cannot be completed."""


@dataclass
class AppStoreVerificationResult:
    is_active: bool
    status_code: int | None
    environment: str
    original_transaction_id: str | None
    transaction_id: str | None
    expiry: datetime | None
    raw_status: str
    bundle_id: str | None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_es256(issuer_id: str, key_id: str, private_key_pem: str, audience: str) -> str:
    now = int(time.time())
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + 300,
        "aud": audience,
        "nonce": str(uuid.uuid4()),
    }
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}".encode()

    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise AppStoreVerificationError("APPLE_PRIVATE_KEY must be an EC private key")

    signature_der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    # Convert DER ECDSA signature into raw R||S format required by JWT ES256.
    r, s = _decode_dss_signature(signature_der)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input.decode()}.{_b64url(raw_sig)}"


def _decode_dss_signature(signature_der: bytes) -> tuple[int, int]:
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    return decode_dss_signature(signature_der)


def _read_private_key(private_key: str | None, private_key_path: str | None) -> str:
    if private_key and private_key.strip():
        return private_key.replace("\\n", "\n")
    if private_key_path and private_key_path.strip():
        with open(private_key_path, "r", encoding="utf-8") as f:
            return f.read()
    raise AppStoreVerificationError("APPLE_PRIVATE_KEY or APPLE_PRIVATE_KEY_PATH is required")


def _decode_jws_payload(jws: str) -> dict[str, Any]:
    parts = jws.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


def _ms_to_dt(raw_ms: Any) -> datetime | None:
    if raw_ms in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(raw_ms) / 1000, tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _apple_api_get(base_url: str, path: str, bearer_token: str) -> dict[str, Any]:
    req = request.Request(
        url=f"{base_url}{path}",
        headers={"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        details: dict[str, Any] = {}
        try:
            details = json.loads(body) if body else {}
        except json.JSONDecodeError:
            details = {"raw": body}
        details["http_status"] = exc.code
        raise AppStoreVerificationError(f"Apple API error: {json.dumps(details)}") from exc
    except error.URLError as exc:
        raise AppStoreVerificationError(f"Apple API request failed: {exc.reason}") from exc


def verify_app_store_subscription(
    *,
    original_transaction_id: str,
    issuer_id: str,
    key_id: str,
    private_key: str | None,
    private_key_path: str | None,
    environment: str,
) -> AppStoreVerificationResult:
    """Verify a subscription using Apple's App Store Server API."""
    private_key_pem = _read_private_key(private_key, private_key_path)
    token = _jwt_es256(issuer_id, key_id, private_key_pem, audience="appstoreconnect-v1")

    env = (environment or "production").strip().lower()
    if env not in {"production", "sandbox", "auto"}:
        raise AppStoreVerificationError("APPLE_ENVIRONMENT must be production, sandbox, or auto")

    urls = [APPSTORE_PRODUCTION_URL]
    if env == "sandbox":
        urls = [APPSTORE_SANDBOX_URL]
    elif env == "auto":
        urls = [APPSTORE_PRODUCTION_URL, APPSTORE_SANDBOX_URL]

    path = f"/inApps/v1/subscriptions/{original_transaction_id}"
    last_error: Exception | None = None
    for base_url in urls:
        try:
            payload = _apple_api_get(base_url, path, token)
        except AppStoreVerificationError as exc:
            last_error = exc
            continue

        data = payload.get("data") or []
        for group in data:
            for txn in group.get("lastTransactions") or []:
                status_code = txn.get("status")
                signed_info = txn.get("signedTransactionInfo") or ""
                decoded = _decode_jws_payload(signed_info)
                expiry = _ms_to_dt(decoded.get("expiresDate"))
                return AppStoreVerificationResult(
                    is_active=status_code in _ACTIVE_STATUSES,
                    status_code=status_code,
                    environment=(payload.get("environment") or base_url).lower(),
                    original_transaction_id=decoded.get("originalTransactionId") or original_transaction_id,
                    transaction_id=decoded.get("transactionId"),
                    expiry=expiry,
                    raw_status=str(status_code),
                    bundle_id=decoded.get("bundleId"),
                )

        return AppStoreVerificationResult(
            is_active=False,
            status_code=None,
            environment=(payload.get("environment") or base_url).lower(),
            original_transaction_id=original_transaction_id,
            transaction_id=None,
            expiry=None,
            raw_status="not_found",
            bundle_id=None,
        )

    assert last_error is not None
    raise last_error
