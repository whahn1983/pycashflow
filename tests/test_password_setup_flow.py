"""Password setup onboarding flow tests."""

from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

def _json(resp):
    body = resp.get_json()
    assert body is not None
    return body


def test_complete_password_setup_success(flask_app, client, app_ctx, user_model, password_setup_helpers):
    create_password_setup_token = password_setup_helpers["create_token"]
    with flask_app.app_context():
        user = user_model(
            email="setup-success@test.local",
            password=generate_password_hash("TempPass123", method="scrypt"),
            name="Setup Success",
            admin=True,
            is_active=True,
        )
        app_ctx.session.add(user)
        app_ctx.session.commit()
        raw_token, _record = create_password_setup_token(user)

    resp = client.post(
        "/api/v1/auth/complete-password-setup",
        json={"token": raw_token, "password": "NewSecure123"},
    )
    assert resp.status_code == 200
    assert _json(resp)["data"]["message"] == "Password setup complete"

    with flask_app.app_context():
        db_user = user_model.query.filter_by(email="setup-success@test.local").first()
        assert db_user is not None
        assert check_password_hash(db_user.password, "NewSecure123")


def test_complete_password_setup_rejects_expired_token(
    flask_app, client, app_ctx, user_model, password_setup_helpers
):
    create_password_setup_token = password_setup_helpers["create_token"]
    with flask_app.app_context():
        user = user_model(
            email="setup-expired@test.local",
            password=generate_password_hash("TempPass123", method="scrypt"),
            name="Setup Expired",
            admin=True,
            is_active=True,
        )
        app_ctx.session.add(user)
        app_ctx.session.commit()
        raw_token, token = create_password_setup_token(user)
        token.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        app_ctx.session.commit()

    resp = client.post(
        "/api/v1/auth/complete-password-setup",
        json={"token": raw_token, "password": "NewSecure123"},
    )
    assert resp.status_code == 401


def test_complete_password_setup_one_time_use(flask_app, client, app_ctx, user_model, password_setup_helpers):
    create_password_setup_token = password_setup_helpers["create_token"]
    with flask_app.app_context():
        user = user_model(
            email="setup-onetime@test.local",
            password=generate_password_hash("TempPass123", method="scrypt"),
            name="Setup OneTime",
            admin=True,
            is_active=True,
        )
        app_ctx.session.add(user)
        app_ctx.session.commit()
        raw_token, _record = create_password_setup_token(user)

    first = client.post(
        "/api/v1/auth/complete-password-setup",
        json={"token": raw_token, "password": "NewSecure123"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/complete-password-setup",
        json={"token": raw_token, "password": "AnotherSecure123"},
    )
    assert second.status_code == 401

    with flask_app.app_context():
        db_user = user_model.query.filter_by(email="setup-onetime@test.local").first()
        assert db_user is not None
        assert check_password_hash(db_user.password, "NewSecure123")


def test_complete_password_setup_invalid_token(flask_app, client):
    resp = client.post(
        "/api/v1/auth/complete-password-setup",
        json={"token": "definitely-not-a-valid-token", "password": "NewSecure123"},
    )
    assert resp.status_code == 401


def test_password_setup_url_uses_frontend_base_url(flask_app, password_setup_helpers):
    build_password_setup_url = password_setup_helpers["build_url"]
    with flask_app.app_context():
        flask_app.config["FRONTEND_BASE_URL"] = "https://app.yourdomain.com/"
        assert (
            build_password_setup_url("abc123")
            == "https://app.yourdomain.com/auth/set-password/abc123"
        )


def test_password_setup_token_stored_hashed_only(
    flask_app,
    app_ctx,
    user_model,
    password_setup_token_model,
    password_setup_helpers,
):
    create_password_setup_token = password_setup_helpers["create_token"]
    with flask_app.app_context():
        user = user_model(
            email="setup-hash@test.local",
            password=generate_password_hash("TempPass123", method="scrypt"),
            name="Setup Hash",
            admin=True,
            is_active=True,
        )
        app_ctx.session.add(user)
        app_ctx.session.commit()

        raw_token, _record = create_password_setup_token(user)
        stored = password_setup_token_model.query.filter_by(user_id=user.id).first()

        assert stored is not None
        assert stored.token_hash != raw_token
        assert len(stored.token_hash) == 64
