from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from app import db
import app.auth as auth_module
from app.auth import User, PasskeyCredential


def _login_session(client, user_id: int):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_passkey_login_options_requires_email(client, monkeypatch):
    monkeypatch.setattr(auth_module, "_WEBAUTHN_AVAILABLE", True)
    monkeypatch.setattr(auth_module, "_passkey_enabled", lambda: True)

    resp = client.post("/passkey_login/options", json={})

    assert resp.status_code == 400
    assert "Unable to start passkey login." in resp.get_json()["error"]


def test_passkey_login_verify_without_challenge_redirects(client, monkeypatch):
    monkeypatch.setattr(auth_module, "_WEBAUTHN_AVAILABLE", True)
    monkeypatch.setattr(auth_module, "_passkey_enabled", lambda: True)

    resp = client.post(
        "/passkey_login/verify",
        json={"id": "cred-login", "response": {}},
        follow_redirects=False,
    )

    assert resp.status_code in (301, 302)
    assert resp.headers["Location"].endswith("/passkey_login")


def test_passkey_register_verify_creates_credential(client, app_ctx, monkeypatch):
    monkeypatch.setattr(auth_module, "_WEBAUTHN_AVAILABLE", True)
    monkeypatch.setattr(auth_module, "_passkey_enabled", lambda: True)

    user = User.query.filter_by(email="admin@test.local").first()
    _login_session(client, user.id)

    with client.session_transaction() as sess:
        sess["passkey_register_challenge"] = "cmVnLWNoYWxsZW5nZQ"
        sess["passkey_register_expires_at"] = int((datetime.now(timezone.utc) + timedelta(minutes=2)).timestamp())

    monkeypatch.setattr(
        auth_module,
        "verify_registration_response",
        lambda **kwargs: SimpleNamespace(
            credential_id=b"registered-cred",
            credential_public_key=b"registered-pub",
            sign_count=1,
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "bytes_to_base64url",
        lambda b: b.decode("utf-8") if isinstance(b, bytes) else str(b),
    )

    resp = client.post(
        "/passkeys/register/verify",
        json={"id": "new-cred", "response": {}, "label": "Laptop"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    created = PasskeyCredential.query.filter_by(user_id=user.id, credential_id="registered-cred").first()
    assert created is not None
    assert created.label == "Laptop"
