"""Unit tests for App Store verification boundary."""

import base64
import json
from datetime import datetime, timezone

import pytest

import app.appstore as appstore


def test_verify_app_store_subscription_auto_falls_back_to_sandbox(monkeypatch):
    calls = []

    def _fake_get(base_url, path, bearer_token):
        calls.append(base_url)
        if "sandbox" not in base_url:
            raise appstore.AppStoreVerificationError("not found in production")
        return {
            "environment": "Sandbox",
            "data": [
                {
                    "lastTransactions": [
                        {
                            "status": 1,
                            "signedTransactionInfo": (
                                "eyJhbGciOiJFUzI1NiJ9."
                                "eyJvcmlnaW5hbFRyYW5zYWN0aW9uSWQiOiJvcmlnXzEiLCJ0cmFuc2FjdGlvbklkIjoidHhuXzEiLCJleHBpcmVzRGF0ZSI6MTkwMDAwMDAwMDAwMCwiYnVuZGxlSWQiOiJjb20uZXhhbXBsZS5weWNhc2hmbG93In0"
                                ".sig"
                            ),
                        }
                    ]
                }
            ],
        }

    monkeypatch.setattr(appstore, "_apple_api_get", _fake_get)
    monkeypatch.setattr(appstore, "_jwt_es256", lambda *args, **kwargs: "token")
    monkeypatch.setattr(appstore, "_read_private_key", lambda *args, **kwargs: "pem")

    result = appstore.verify_app_store_subscription(
        original_transaction_id="orig_1",
        issuer_id="issuer",
        key_id="kid",
        private_key="pem",
        private_key_path=None,
        environment="auto",
        bundle_id="com.example.pycashflow",
    )

    assert result.is_active is True
    assert result.original_transaction_id == "orig_1"
    assert result.transaction_id == "txn_1"
    assert result.bundle_id == "com.example.pycashflow"
    assert isinstance(result.expiry, datetime)
    assert result.expiry.tzinfo is None
    assert len(calls) == 2


def test_verify_app_store_subscription_expired_status(monkeypatch):
    def _fake_get(base_url, path, bearer_token):
        return {
            "environment": "Production",
            "data": [
                {
                    "lastTransactions": [
                        {
                            "status": 2,
                            "signedTransactionInfo": "eyJhbGciOiJFUzI1NiJ9.eyJvcmlnaW5hbFRyYW5zYWN0aW9uSWQiOiJvcmlnX2V4cCIsImV4cGlyZXNEYXRlIjoxNjAwMDAwMDAwMDAwfQ.sig",
                        }
                    ]
                }
            ],
        }

    monkeypatch.setattr(appstore, "_apple_api_get", _fake_get)
    monkeypatch.setattr(appstore, "_jwt_es256", lambda *args, **kwargs: "token")
    monkeypatch.setattr(appstore, "_read_private_key", lambda *args, **kwargs: "pem")

    result = appstore.verify_app_store_subscription(
        original_transaction_id="orig_exp",
        issuer_id="issuer",
        key_id="kid",
        private_key="pem",
        private_key_path=None,
        environment="production",
        bundle_id="com.example.pycashflow",
    )

    assert result.is_active is False
    assert result.status_code == 2
    assert result.expiry is not None
    assert result.expiry < datetime.now(timezone.utc).replace(tzinfo=None)


def test_jwt_es256_payload_includes_required_claims(monkeypatch):
    captured = {}

    def _fake_get(base_url, path, bearer_token):
        captured["token"] = bearer_token
        return {"environment": "Production", "data": []}

    def _capturing_jwt(issuer_id, key_id, private_key_pem, audience, bundle_id):
        header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
        payload = {
            "iss": issuer_id,
            "iat": 0,
            "exp": 300,
            "aud": audience,
            "bid": bundle_id,
        }
        def _b64(d):
            return base64.urlsafe_b64encode(
                json.dumps(d, separators=(",", ":")).encode()
            ).rstrip(b"=").decode()
        return f"{_b64(header)}.{_b64(payload)}.sig"

    monkeypatch.setattr(appstore, "_apple_api_get", _fake_get)
    monkeypatch.setattr(appstore, "_jwt_es256", _capturing_jwt)
    monkeypatch.setattr(appstore, "_read_private_key", lambda *args, **kwargs: "pem")

    appstore.verify_app_store_subscription(
        original_transaction_id="orig_x",
        issuer_id="issuer",
        key_id="kid",
        private_key="pem",
        private_key_path=None,
        environment="production",
        bundle_id="com.example.pycashflow",
    )

    payload_b64 = captured["token"].split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
    assert payload["iss"] == "issuer"
    assert payload["aud"] == "appstoreconnect-v1"
    assert payload["bid"] == "com.example.pycashflow"
    assert "nonce" not in payload


def test_verify_app_store_subscription_requires_bundle_id():
    with pytest.raises(appstore.AppStoreVerificationError):
        appstore.verify_app_store_subscription(
            original_transaction_id="orig_x",
            issuer_id="issuer",
            key_id="kid",
            private_key="pem",
            private_key_path=None,
            environment="production",
            bundle_id="",
        )
