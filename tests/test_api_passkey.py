"""Tests for the mobile passkey login API endpoints."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app import db
import app.api.routes.auth as api_auth_module
from app.models import PasskeyCredential, User


def _enable_passkey(monkeypatch):
    monkeypatch.setattr(api_auth_module, "_WEBAUTHN_AVAILABLE", True)
    monkeypatch.setattr(api_auth_module, "_passkey_enabled", lambda: True)


def _seed_passkey_user(app_ctx, email: str, credential_id: str = "ios-cred") -> User:
    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(
            email=email,
            password="x",
            name="Passkey User",
            admin=True,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

    if not PasskeyCredential.query.filter_by(credential_id=credential_id).first():
        db.session.add(
            PasskeyCredential(
                user_id=user.id,
                credential_id=credential_id,
                public_key="pub",
                sign_count=0,
                label="iPhone",
                last_used_at=datetime.now(timezone.utc),
            )
        )
        db.session.commit()
    return user


def test_api_passkey_options_returns_challenge_token(client, app_ctx, monkeypatch):
    _enable_passkey(monkeypatch)

    user = _seed_passkey_user(app_ctx, email="passkey-options@test.local")

    stub_options = SimpleNamespace(challenge=b"challenge-bytes")
    monkeypatch.setattr(
        api_auth_module,
        "generate_authentication_options",
        lambda **kwargs: stub_options,
    )
    monkeypatch.setattr(
        api_auth_module,
        "options_to_json",
        lambda opts: '{"challenge": "Y2hhbGxlbmdlLWJ5dGVz", "rpId": "localhost"}',
    )
    monkeypatch.setattr(
        api_auth_module,
        "bytes_to_base64url",
        lambda b: "Y2hhbGxlbmdlLWJ5dGVz" if b == b"challenge-bytes" else str(b),
    )
    monkeypatch.setattr(
        api_auth_module,
        "base64url_to_bytes",
        lambda s: s.encode("utf-8"),
    )
    monkeypatch.setattr(
        api_auth_module,
        "PublicKeyCredentialDescriptor",
        lambda id: SimpleNamespace(id=id),
    )
    monkeypatch.setattr(
        api_auth_module,
        "UserVerificationRequirement",
        SimpleNamespace(REQUIRED="required"),
    )

    resp = client.post("/api/v1/auth/passkey/options", json={"email": user.email})
    assert resp.status_code == 200

    data = resp.get_json()["data"]
    assert data["challenge_token"]
    assert data["options"]["challenge"] == "Y2hhbGxlbmdlLWJ5dGVz"


def test_api_passkey_options_requires_email(client, monkeypatch):
    _enable_passkey(monkeypatch)

    resp = client.post("/api/v1/auth/passkey/options", json={})
    assert resp.status_code == 422
    assert resp.get_json()["fields"]["email"]


def test_api_passkey_options_unknown_user_returns_decoy(client, monkeypatch):
    _enable_passkey(monkeypatch)

    stub_options = SimpleNamespace(challenge=b"decoy-challenge-bytes")
    monkeypatch.setattr(
        api_auth_module,
        "generate_authentication_options",
        lambda **kwargs: stub_options,
    )
    monkeypatch.setattr(
        api_auth_module,
        "options_to_json",
        lambda opts: '{"challenge": "ZGVjb3ktY2hhbGxlbmdlLWJ5dGVz"}',
    )
    monkeypatch.setattr(
        api_auth_module,
        "bytes_to_base64url",
        lambda b: "ZGVjb3ktY2hhbGxlbmdlLWJ5dGVz",
    )
    monkeypatch.setattr(
        api_auth_module,
        "base64url_to_bytes",
        lambda s: s.encode("utf-8"),
    )
    monkeypatch.setattr(
        api_auth_module,
        "PublicKeyCredentialDescriptor",
        lambda id: SimpleNamespace(id=id),
    )
    monkeypatch.setattr(
        api_auth_module,
        "UserVerificationRequirement",
        SimpleNamespace(REQUIRED="required"),
    )

    resp = client.post(
        "/api/v1/auth/passkey/options",
        json={"email": "no-such-user@test.local"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["challenge_token"]
    assert data["options"]["challenge"] == "ZGVjb3ktY2hhbGxlbmdlLWJ5dGVz"

    # The decoy token must not grant access when submitted to /verify.
    verify_resp = client.post(
        "/api/v1/auth/passkey/verify",
        json={
            "challenge_token": data["challenge_token"],
            "credential": {
                "id": "anything",
                "rawId": "anything",
                "type": "public-key",
                "response": {
                    "authenticatorData": "AAAA",
                    "clientDataJSON": "AAAA",
                    "signature": "AAAA",
                },
            },
        },
    )
    assert verify_resp.status_code == 401


def test_api_passkey_options_decoy_is_indistinguishable_from_real(
    client, app_ctx, monkeypatch
):
    # Enumeration-resistance regression: the signed (not encrypted) challenge
    # token and the options payload must not expose whether the email maps to
    # an eligible passkey user.
    _enable_passkey(monkeypatch)

    _seed_passkey_user(
        app_ctx,
        email="indistinguishable-real@test.local",
        credential_id="abcd1234",  # hex-encoded for the hex stubs below
    )

    # Stub webauthn helpers so we can exercise both the real-user and decoy
    # paths without the optional dependency. The stubs echo inputs so the
    # response shape reflects what the route actually produces.
    monkeypatch.setattr(
        api_auth_module,
        "generate_authentication_options",
        lambda **kwargs: SimpleNamespace(
            challenge=b"c",
            allow_credentials=list(kwargs.get("allow_credentials") or []),
        ),
    )
    monkeypatch.setattr(
        api_auth_module,
        "options_to_json",
        lambda opts: (
            '{"challenge": "Yw", "allowCredentials": ['
            + ", ".join(
                f'{{"id": "{c.id.hex()}"}}' for c in opts.allow_credentials
            )
            + "]}"
        ),
    )
    monkeypatch.setattr(api_auth_module, "bytes_to_base64url", lambda b: b.hex())
    monkeypatch.setattr(api_auth_module, "base64url_to_bytes", lambda s: bytes.fromhex(s))
    monkeypatch.setattr(
        api_auth_module,
        "PublicKeyCredentialDescriptor",
        lambda id: SimpleNamespace(id=id),
    )
    monkeypatch.setattr(
        api_auth_module,
        "UserVerificationRequirement",
        SimpleNamespace(REQUIRED="required"),
    )

    real_resp = client.post(
        "/api/v1/auth/passkey/options",
        json={"email": "indistinguishable-real@test.local"},
    )
    decoy_resp = client.post(
        "/api/v1/auth/passkey/options",
        json={"email": "indistinguishable-missing@test.local"},
    )

    assert real_resp.status_code == 200
    assert decoy_resp.status_code == 200

    real_data = real_resp.get_json()["data"]
    decoy_data = decoy_resp.get_json()["data"]

    # Both responses expose the same top-level keys.
    assert set(real_data) == set(decoy_data) == {"challenge_token", "options"}

    # Both options payloads expose the same keys (rpId, challenge, etc.) so a
    # caller cannot distinguish by inspecting the shape.
    assert set(real_data["options"]) == set(decoy_data["options"])

    # allow_credentials has the same length — 1 for a user with one passkey,
    # 1 for the decoy case.
    assert len(real_data["options"]["allowCredentials"]) == 1
    assert len(decoy_data["options"]["allowCredentials"]) == 1

    # The decoded challenge_token payloads must have the same keys; nothing
    # like `uid=0` or a `decoy:` nonce prefix may leak the user state.
    serializer = api_auth_module._passkey_challenge_serializer()
    real_payload = serializer.loads(real_data["challenge_token"])
    decoy_payload = serializer.loads(decoy_data["challenge_token"])
    assert set(real_payload) == set(decoy_payload)
    assert "uid" not in real_payload and "uid" not in decoy_payload


def test_api_passkey_verify_returns_bearer_token(client, app_ctx, monkeypatch):
    _enable_passkey(monkeypatch)

    user = _seed_passkey_user(
        app_ctx,
        email="passkey-verify@test.local",
        credential_id="cred-xyz",
    )

    # First: obtain options to receive a signed challenge_token.
    stub_options = SimpleNamespace(challenge=b"verify-challenge-bytes")
    monkeypatch.setattr(
        api_auth_module,
        "generate_authentication_options",
        lambda **kwargs: stub_options,
    )
    monkeypatch.setattr(
        api_auth_module,
        "options_to_json",
        lambda opts: '{"challenge": "dmVyaWZ5LWNoYWxsZW5nZS1ieXRlcw"}',
    )
    monkeypatch.setattr(
        api_auth_module,
        "bytes_to_base64url",
        lambda b: "dmVyaWZ5LWNoYWxsZW5nZS1ieXRlcw",
    )
    monkeypatch.setattr(
        api_auth_module,
        "base64url_to_bytes",
        lambda s: s.encode("utf-8"),
    )
    monkeypatch.setattr(
        api_auth_module,
        "PublicKeyCredentialDescriptor",
        lambda id: SimpleNamespace(id=id),
    )
    monkeypatch.setattr(
        api_auth_module,
        "UserVerificationRequirement",
        SimpleNamespace(REQUIRED="required"),
    )

    options_resp = client.post(
        "/api/v1/auth/passkey/options",
        json={"email": user.email},
    )
    assert options_resp.status_code == 200
    challenge_token = options_resp.get_json()["data"]["challenge_token"]

    # Now: stub the verification itself and call verify.
    monkeypatch.setattr(
        api_auth_module,
        "verify_authentication_response",
        lambda **kwargs: SimpleNamespace(new_sign_count=7),
    )

    credential_payload = {
        "id": "cred-xyz",
        "rawId": "cred-xyz",
        "type": "public-key",
        "response": {
            "authenticatorData": "AAAA",
            "clientDataJSON": "AAAA",
            "signature": "AAAA",
        },
    }
    verify_resp = client.post(
        "/api/v1/auth/passkey/verify",
        json={"challenge_token": challenge_token, "credential": credential_payload},
    )
    assert verify_resp.status_code == 200

    body = verify_resp.get_json()["data"]
    assert body["token"]
    assert body["user"]["email"] == user.email

    refreshed = PasskeyCredential.query.filter_by(credential_id="cred-xyz").first()
    assert refreshed.sign_count == 7
    assert refreshed.last_used_at is not None


def test_api_passkey_verify_rejects_replay(client, app_ctx, monkeypatch):
    _enable_passkey(monkeypatch)

    user = _seed_passkey_user(
        app_ctx,
        email="passkey-replay@test.local",
        credential_id="cred-replay",
    )

    stub_options = SimpleNamespace(challenge=b"replay-bytes")
    monkeypatch.setattr(
        api_auth_module,
        "generate_authentication_options",
        lambda **kwargs: stub_options,
    )
    monkeypatch.setattr(
        api_auth_module,
        "options_to_json",
        lambda opts: '{"challenge": "cmVwbGF5LWJ5dGVz"}',
    )
    monkeypatch.setattr(
        api_auth_module,
        "bytes_to_base64url",
        lambda b: "cmVwbGF5LWJ5dGVz",
    )
    monkeypatch.setattr(
        api_auth_module,
        "base64url_to_bytes",
        lambda s: s.encode("utf-8"),
    )
    monkeypatch.setattr(
        api_auth_module,
        "PublicKeyCredentialDescriptor",
        lambda id: SimpleNamespace(id=id),
    )
    monkeypatch.setattr(
        api_auth_module,
        "UserVerificationRequirement",
        SimpleNamespace(REQUIRED="required"),
    )
    monkeypatch.setattr(
        api_auth_module,
        "verify_authentication_response",
        lambda **kwargs: SimpleNamespace(new_sign_count=1),
    )

    options_resp = client.post(
        "/api/v1/auth/passkey/options",
        json={"email": user.email},
    )
    challenge_token = options_resp.get_json()["data"]["challenge_token"]

    credential_payload = {
        "id": "cred-replay",
        "rawId": "cred-replay",
        "type": "public-key",
        "response": {
            "authenticatorData": "AAAA",
            "clientDataJSON": "AAAA",
            "signature": "AAAA",
        },
    }

    first = client.post(
        "/api/v1/auth/passkey/verify",
        json={"challenge_token": challenge_token, "credential": credential_payload},
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/v1/auth/passkey/verify",
        json={"challenge_token": challenge_token, "credential": credential_payload},
    )
    assert replay.status_code == 401
