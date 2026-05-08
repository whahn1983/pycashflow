"""
Unit tests for the AI insights helper layer:
  - normalize_do_base_url
  - select_provider (user OpenAI vs DigitalOcean fallback vs none)
  - is_refresh_due (2-hour limit)
  - fetch_insights_for_provider client construction
  - /api/v1/insights/refresh end-to-end honors the provider/refresh policy

These tests are backend-only and do not exercise the real OpenAI/DO APIs.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

# Capture real module references at conftest load time, before any sibling
# test modules (e.g. test_cash_risk_score.py) install sys.modules stubs.
from app import db as _db
from app import ai_insights as _ai_insights_module
from app.api.routes import data as _api_data_module
from app.ai_insights import (
    DEFAULT_MODEL,
    DO_DEFAULT_MODEL,
    AIProviderError,
    _is_subscription_tier_error,
    fetch_insights_for_provider,
    is_refresh_due,
    normalize_do_base_url,
    select_provider,
    validate_model,
)
from app.crypto_utils import encrypt_password
from app.models import AISettings


# ── normalize_do_base_url ────────────────────────────────────────────────────


class TestNormalizeDoBaseUrl:
    def test_appends_api_v1_when_missing(self):
        assert (
            normalize_do_base_url("https://example.do.run")
            == "https://example.do.run/api/v1/"
        )

    def test_handles_trailing_slash(self):
        assert (
            normalize_do_base_url("https://example.do.run/")
            == "https://example.do.run/api/v1/"
        )

    def test_keeps_existing_api_v1_segment(self):
        assert (
            normalize_do_base_url("https://example.do.run/api/v1")
            == "https://example.do.run/api/v1/"
        )

    def test_keeps_existing_api_v1_with_trailing_slash(self):
        assert (
            normalize_do_base_url("https://example.do.run/api/v1/")
            == "https://example.do.run/api/v1/"
        )

    def test_avoids_double_slash(self):
        # Trailing slashes should never produce '//api/v1/'
        url = normalize_do_base_url("https://example.do.run//")
        assert "//api/v1" not in url
        assert url.endswith("/api/v1/")


# ── select_provider ──────────────────────────────────────────────────────────


def _ai_config(api_key="enc-key", model="gpt-4o"):
    return SimpleNamespace(api_key=api_key, model_version=model, last_updated=None,
                           last_insights=None)


class TestSelectProvider:
    def test_user_openai_settings_take_precedence_when_model_is_explicit(self, monkeypatch):
        # With an explicit user-selected model, OpenAI settings still win.
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
        provider = select_provider(_ai_config(api_key="encrypted", model="gpt-4o"))
        assert provider["kind"] == "openai"
        assert provider["api_key"] == "encrypted"
        assert provider["model"] == "gpt-4o"

    def test_do_agent_preferred_when_user_model_is_not_set(self, monkeypatch):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
        provider = select_provider(_ai_config(api_key="encrypted", model=None))
        assert provider["kind"] == "digitalocean"
        assert provider["model"] == DO_DEFAULT_MODEL

    def test_user_openai_default_model_when_none(self, monkeypatch):
        provider = select_provider(_ai_config(api_key="encrypted", model=None))
        assert provider["kind"] == "openai"
        assert provider["model"] == DEFAULT_MODEL

    def test_falls_back_to_digitalocean_when_no_user_key(self, monkeypatch):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
        monkeypatch.delenv("DO_AI_MODEL", raising=False)
        # No AISettings record at all
        provider = select_provider(None)
        assert provider["kind"] == "digitalocean"
        assert provider["api_key"] == "do-secret"
        assert provider["base_url"] == "https://example.do.run/api/v1/"
        assert provider["model"] == DO_DEFAULT_MODEL

    def test_falls_back_when_user_record_has_no_api_key(self, monkeypatch):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run/")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
        # DO_AI_MODEL must be ignored — agent endpoints require model="n/a".
        monkeypatch.setenv("DO_AI_MODEL", "llama-3")
        # AISettings exists but api_key is None
        provider = select_provider(_ai_config(api_key=None, model=None))
        assert provider["kind"] == "digitalocean"
        assert provider["model"] == DO_DEFAULT_MODEL
        assert provider["base_url"] == "https://example.do.run/api/v1/"

    def test_returns_none_when_no_user_key_and_no_do_env(self, monkeypatch):
        monkeypatch.delenv("DO_AI_BASE_URL", raising=False)
        monkeypatch.delenv("DO_AI_API_KEY", raising=False)
        assert select_provider(None) is None
        assert select_provider(_ai_config(api_key=None, model=None)) is None

    def test_requires_both_do_env_vars(self, monkeypatch):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.delenv("DO_AI_API_KEY", raising=False)
        assert select_provider(None) is None
        monkeypatch.delenv("DO_AI_BASE_URL", raising=False)
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
        assert select_provider(None) is None


# ── is_refresh_due ───────────────────────────────────────────────────────────


class TestIsRefreshDue:
    def test_missing_timestamp_is_due(self):
        assert is_refresh_due(None) is True

    def test_within_2_hours_is_not_due(self):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        assert is_refresh_due(recent, now=now) is False

    def test_just_under_2_hours_is_not_due(self):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1, minutes=59)
        assert is_refresh_due(recent, now=now) is False

    def test_exactly_2_hours_is_due(self):
        now = datetime.now(timezone.utc)
        boundary = now - timedelta(hours=2)
        assert is_refresh_due(boundary, now=now) is True

    def test_older_than_2_hours_is_due(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=3)
        assert is_refresh_due(old, now=now) is True

    def test_handles_naive_timestamp_as_utc(self):
        now = datetime.now(timezone.utc)
        naive_recent = (now - timedelta(hours=1)).replace(tzinfo=None)
        assert is_refresh_due(naive_recent, now=now) is False


# ── fetch_insights_for_provider client construction ──────────────────────────


class TestFetchInsightsForProvider:
    def test_digitalocean_uses_base_url_and_plain_key(self, monkeypatch):
        captured = {}

        class FakeClient:
            def __init__(self, *, api_key, base_url=None):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = SimpleNamespace(completions=SimpleNamespace(
                    create=lambda **kwargs: (
                        captured.update(create_kwargs=kwargs)
                        or SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(
                                content='{"insights": []}'))]
                        )
                    )
                ))

        monkeypatch.setattr(_ai_insights_module, "OpenAI", FakeClient)
        monkeypatch.setattr(
            _ai_insights_module,
            "build_payload",
            lambda *a, **kw: {"today": "2026-05-08"},
        )

        provider = {
            "kind": "digitalocean",
            "api_key": "do-plain-key",
            "base_url": "https://example.do.run/api/v1/",
            "model": "n/a",
        }
        out = fetch_insights_for_provider(provider, 0.0, [], [], [])
        assert out == '{"insights": []}'
        assert captured["api_key"] == "do-plain-key"
        assert captured["base_url"] == "https://example.do.run/api/v1/"

        # DO GenAI agents reject system/developer messages — only a single
        # user message should be sent, with the prompt folded in.
        messages = captured["create_kwargs"]["messages"]
        assert [m["role"] for m in messages] == ["user"]
        assert _ai_insights_module.SYSTEM_PROMPT in messages[0]["content"]
        assert '"today": "2026-05-08"' in messages[0]["content"]

    def test_openai_decrypts_user_key_and_uses_no_base_url(self, monkeypatch):
        captured = {}

        class FakeClient:
            def __init__(self, *, api_key, base_url=None):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = SimpleNamespace(completions=SimpleNamespace(
                    create=lambda **kwargs: (
                        captured.update(create_kwargs=kwargs)
                        or SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(
                                content='{"insights": []}'))]
                        )
                    )
                ))

        monkeypatch.setattr(_ai_insights_module, "OpenAI", FakeClient)
        monkeypatch.setattr(
            _ai_insights_module,
            "build_payload",
            lambda *a, **kw: {"today": "2026-05-08"},
        )
        monkeypatch.setattr(
            _ai_insights_module,
            "decrypt_password",
            lambda enc: "decrypted-" + enc,
        )

        provider = {
            "kind": "openai",
            "api_key": "ENC",
            "model": "gpt-4o",
        }
        out = fetch_insights_for_provider(provider, 0.0, [], [], [])
        assert out == '{"insights": []}'
        assert captured["api_key"] == "decrypted-ENC"
        assert captured["base_url"] is None

        # OpenAI proper still gets the system message.
        messages = captured["create_kwargs"]["messages"]
        assert [m["role"] for m in messages] == ["system", "user"]
        assert messages[0]["content"] == _ai_insights_module.SYSTEM_PROMPT
        assert '"today": "2026-05-08"' in messages[1]["content"]


# ── End-to-end: /api/v1/insights/refresh respects provider + 2h limit ───────


def _login(client, email="admin@test.local", password="testpass123"):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        content_type="application/json",
    )
    return resp.get_json()["data"]["token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def clean_ai_settings(flask_app):
    """Wipe the admin's AISettings before/after each test so independent runs
    don't leak state through the session-scoped in-memory database."""
    from conftest import _ADMIN_USER_ID  # type: ignore
    with flask_app.app_context():
        AISettings.query.filter_by(user_id=_ADMIN_USER_ID).delete()
        _db.session.commit()
    yield _ADMIN_USER_ID
    with flask_app.app_context():
        AISettings.query.filter_by(user_id=_ADMIN_USER_ID).delete()
        _db.session.commit()


@pytest.fixture()
def clear_do_env(monkeypatch):
    monkeypatch.delenv("DO_AI_BASE_URL", raising=False)
    monkeypatch.delenv("DO_AI_API_KEY", raising=False)
    monkeypatch.delenv("DO_AI_MODEL", raising=False)


class TestRefreshEndpointProviderAndLimit:
    def test_no_provider_returns_validation_error(self, client, clean_ai_settings, clear_do_env):
        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["code"] == "validation_error"
        assert "api_key" in body["fields"]

    def test_uses_user_openai_when_configured(self, client, flask_app, clean_ai_settings, monkeypatch):
        # Even with DO env present, user OpenAI must win.
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")

        user_id = clean_ai_settings
        with flask_app.app_context():
            _db.session.add(AISettings(
                user_id=user_id,
                api_key=encrypt_password("sk-user"),
                model_version="gpt-4o",
            ))
            _db.session.commit()

        captured = {}

        def fake_fetch(provider, *args, **kwargs):
            captured["provider"] = provider
            return '{"insights": []}'

        monkeypatch.setattr(
            _api_data_module, "fetch_insights_for_provider",
            fake_fetch,
        )

        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 200, resp.get_json()
        assert captured["provider"]["kind"] == "openai"

    def test_uses_digitalocean_when_user_key_missing_and_env_set(self, client, flask_app, clean_ai_settings, monkeypatch):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run/")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
        # DO_AI_MODEL must be ignored — agent endpoints require model="n/a".
        monkeypatch.setenv("DO_AI_MODEL", "do-model")

        captured = {}

        def fake_fetch(provider, *args, **kwargs):
            captured["provider"] = provider
            return '{"insights": []}'

        monkeypatch.setattr(
            _api_data_module, "fetch_insights_for_provider",
            fake_fetch,
        )

        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 200, resp.get_json()
        assert captured["provider"]["kind"] == "digitalocean"
        assert captured["provider"]["base_url"] == "https://example.do.run/api/v1/"
        assert captured["provider"]["model"] == DO_DEFAULT_MODEL

        # And it should have created an AISettings row with last_updated set
        # so the cache check works on subsequent calls.
        with flask_app.app_context():
            row = AISettings.query.filter_by(user_id=clean_ai_settings).first()
            assert row is not None
            assert row.last_updated is not None
            assert row.last_insights == '{"insights": []}'

    def test_recent_refresh_returns_cached_without_calling_provider(self, client, flask_app, clean_ai_settings, monkeypatch):
        # Even though DO env is present and would otherwise be used, a refresh
        # less than 2 hours ago must skip the AI call entirely.
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")

        user_id = clean_ai_settings
        cached_payload = '{"insights": [{"type": "observation", "title": "cached"}]}'
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        with flask_app.app_context():
            _db.session.add(AISettings(
                user_id=user_id,
                api_key=None,
                model_version=None,
                last_updated=recent,
                last_insights=cached_payload,
            ))
            _db.session.commit()

        called = {"count": 0}

        def fake_fetch(*args, **kwargs):
            called["count"] += 1
            return '{"insights": []}'

        monkeypatch.setattr(
            _api_data_module, "fetch_insights_for_provider",
            fake_fetch,
        )

        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 200, resp.get_json()
        assert called["count"] == 0
        body = resp.get_json()["data"]
        assert body["insights"] == json.loads(cached_payload)

    def test_invalid_cached_json_within_window_returns_without_regenerating(self, client, flask_app, clean_ai_settings, monkeypatch):
        # A malformed cached payload inside the 2-hour window should not trigger
        # a provider call, and must preserve the existing last_updated timestamp.
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")

        user_id = clean_ai_settings
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        with flask_app.app_context():
            _db.session.add(AISettings(
                user_id=user_id,
                api_key=None,
                model_version=None,
                last_updated=recent,
                last_insights="not-json{",
            ))
            _db.session.commit()

        called = {"count": 0}

        def fake_fetch(provider, *args, **kwargs):
            called["count"] += 1
            return '{"insights": [{"title": "fresh"}]}'

        monkeypatch.setattr(
            _api_data_module, "fetch_insights_for_provider",
            fake_fetch,
        )

        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 200, resp.get_json()
        assert called["count"] == 0
        body = resp.get_json()["data"]
        assert body["insights"] is None

        with flask_app.app_context():
            row = AISettings.query.filter_by(user_id=user_id).first()
            assert row.last_insights == "not-json{"
            assert row.last_updated is not None
            row_dt = row.last_updated if row.last_updated.tzinfo else row.last_updated.replace(tzinfo=timezone.utc)
            assert abs((row_dt - recent).total_seconds()) < 5

    def test_stale_refresh_calls_provider_and_updates_timestamp(self, client, flask_app, clean_ai_settings, monkeypatch):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")

        user_id = clean_ai_settings
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        with flask_app.app_context():
            _db.session.add(AISettings(
                user_id=user_id,
                api_key=None,
                model_version=None,
                last_updated=old,
                last_insights='{"insights": [{"title": "stale"}]}',
            ))
            _db.session.commit()

        called = {"count": 0}

        def fake_fetch(provider, *args, **kwargs):
            called["count"] += 1
            return '{"insights": [{"title": "fresh"}]}'

        monkeypatch.setattr(
            _api_data_module, "fetch_insights_for_provider",
            fake_fetch,
        )

        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 200, resp.get_json()
        assert called["count"] == 1

        with flask_app.app_context():
            row = AISettings.query.filter_by(user_id=user_id).first()
            assert row.last_insights == '{"insights": [{"title": "fresh"}]}'
            # last_updated was bumped — should be within the last few seconds
            row_dt = row.last_updated
            if row_dt.tzinfo is None:
                row_dt = row_dt.replace(tzinfo=timezone.utc)
            assert (datetime.now(timezone.utc) - row_dt) < timedelta(minutes=1)


class TestRemoveApiKeyRoute:
    def test_remove_clears_key_and_model_and_falls_back_to_digitalocean(
        self, auth_client, flask_app, clean_ai_settings, monkeypatch
    ):
        user_id = clean_ai_settings
        cached_payload = '{"insights": [{"title": "kept"}]}'
        cached_ts = datetime.now(timezone.utc)
        with flask_app.app_context():
            _db.session.add(AISettings(
                user_id=user_id,
                api_key=encrypt_password("sk-user"),
                model_version="gpt-4o",
                last_insights=cached_payload,
                last_updated=cached_ts,
            ))
            _db.session.commit()

        resp = auth_client.post("/ai_settings/remove", follow_redirects=False)
        assert resp.status_code in (302, 303)

        with flask_app.app_context():
            row = AISettings.query.filter_by(user_id=user_id).first()
            assert row is not None
            assert row.api_key is None
            assert row.model_version is None
            # Cached insights and the 2h refresh window are shared with the
            # DigitalOcean provider and must be preserved.
            assert row.last_insights == cached_payload
            assert row.last_updated is not None

            # With the user key cleared and DO env vars set, provider must
            # fall back to DigitalOcean.
            monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
            monkeypatch.setenv("DO_AI_API_KEY", "do-secret")
            provider = select_provider(row)
            assert provider is not None
            assert provider["kind"] == "digitalocean"

    def test_remove_when_no_key_saved_is_a_noop(self, auth_client, clean_ai_settings):
        # No AISettings row at all — endpoint should redirect without 500.
        resp = auth_client.post("/ai_settings/remove", follow_redirects=False)
        assert resp.status_code in (302, 303)


# ── Provider error classification ────────────────────────────────────────────


class _FakeAuthError(Exception):
    """Stand-in for openai.AuthenticationError that bypasses the SDK's
    httpx.Response-bound constructor.  Subclasses the real class so the
    isinstance() checks in fetch_insights_for_provider still match."""

    def __new__(cls, message, body=None):
        from openai import AuthenticationError
        # Build a real subclass instance without invoking the real __init__
        # (which would require a live httpx.Response).
        kls = type("_TestAuthError", (AuthenticationError,), {})
        inst = Exception.__new__(kls)
        Exception.__init__(inst, message)
        inst.body = body
        return inst


def _make_permission_error(message, body=None):
    from openai import PermissionDeniedError
    kls = type("_TestPermErr", (PermissionDeniedError,), {})
    inst = Exception.__new__(kls)
    Exception.__init__(inst, message)
    inst.body = body
    return inst


def _make_not_found_error(message, body=None):
    from openai import NotFoundError
    kls = type("_TestNotFound", (NotFoundError,), {})
    inst = Exception.__new__(kls)
    Exception.__init__(inst, message)
    inst.body = body
    return inst


# The exact wrapped body the user reported: a 401 envelope from the DO GenAI
# gateway whose "error" string contains a 403 "subscription tier" rejection.
_WRAPPED_TIER_BODY = {
    "error": (
        "Error code: 403 - {'error': {'message': 'this model is not "
        "available for your subscription tier', 'type': 'forbidden_error'}, "
        "'message': 'this model is not available for your subscription "
        "tier', 'status_code': 403}"
    ),
    "code": 401,
}


class TestIsSubscriptionTierError:
    def test_detects_wrapped_401_with_inner_403_tier_message(self):
        exc = _FakeAuthError("Error code: 401", body=_WRAPPED_TIER_BODY)
        assert _is_subscription_tier_error(exc) is True

    def test_detects_dict_error_with_message_key(self):
        body = {"error": {"message": "this model is not available for your subscription tier"}}
        exc = _FakeAuthError("oops", body=body)
        assert _is_subscription_tier_error(exc) is True

    def test_does_not_match_plain_invalid_key(self):
        body = {"error": {"message": "Incorrect API key provided"}}
        exc = _FakeAuthError("Error code: 401", body=body)
        assert _is_subscription_tier_error(exc) is False

    def test_handles_missing_body(self):
        exc = _FakeAuthError("boom", body=None)
        assert _is_subscription_tier_error(exc) is False


class TestFetchInsightsErrorClassification:
    def _patch_client_to_raise(self, monkeypatch, exc):
        class FakeClient:
            def __init__(self, *, api_key, base_url=None):
                def _raise(**_kwargs):
                    raise exc
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=_raise)
                )

        monkeypatch.setattr(_ai_insights_module, "OpenAI", FakeClient)
        monkeypatch.setattr(
            _ai_insights_module, "build_payload",
            lambda *a, **kw: {"today": "2026-05-08"},
        )
        monkeypatch.setattr(
            _ai_insights_module, "decrypt_password", lambda enc: "plain",
        )

    def test_wrapped_tier_401_becomes_subscription_tier_error(self, monkeypatch):
        wrapped = _FakeAuthError("Error code: 401", body=_WRAPPED_TIER_BODY)
        self._patch_client_to_raise(monkeypatch, wrapped)
        provider = {"kind": "openai", "api_key": "ENC", "model": "gpt-4o"}
        with pytest.raises(AIProviderError) as ei:
            fetch_insights_for_provider(provider, 0.0, [], [], [])
        assert "subscription tier" in ei.value.user_message.lower()
        assert ei.value.original is wrapped

    def test_plain_authentication_error_signals_bad_key(self, monkeypatch):
        exc = _FakeAuthError(
            "Error code: 401",
            body={"error": {"message": "Incorrect API key provided"}},
        )
        self._patch_client_to_raise(monkeypatch, exc)
        provider = {"kind": "openai", "api_key": "ENC", "model": "gpt-4o"}
        with pytest.raises(AIProviderError) as ei:
            fetch_insights_for_provider(provider, 0.0, [], [], [])
        msg = ei.value.user_message.lower()
        assert "api key" in msg
        assert "subscription tier" not in msg

    def test_permission_denied_becomes_provider_error(self, monkeypatch):
        exc = _make_permission_error(
            "Error code: 403",
            body={"error": {"message": "model not available for your subscription tier"}},
        )
        self._patch_client_to_raise(monkeypatch, exc)
        provider = {"kind": "openai", "api_key": "ENC", "model": "gpt-4o"}
        with pytest.raises(AIProviderError) as ei:
            fetch_insights_for_provider(provider, 0.0, [], [], [])
        assert "subscription tier" in ei.value.user_message.lower()

    def test_not_found_includes_model_name(self, monkeypatch):
        exc = _make_not_found_error("Error code: 404", body={})
        self._patch_client_to_raise(monkeypatch, exc)
        provider = {"kind": "openai", "api_key": "ENC", "model": "made-up"}
        with pytest.raises(AIProviderError) as ei:
            fetch_insights_for_provider(provider, 0.0, [], [], [])
        assert "made-up" in ei.value.user_message


class TestValidateModelTierError:
    def test_validate_model_handles_permission_denied(self, monkeypatch):
        exc = _make_permission_error(
            "Error code: 403",
            body={"error": {"message": "model not available for your subscription tier"}},
        )

        class FakeClient:
            def __init__(self, *, api_key, base_url=None):
                self.models = SimpleNamespace(retrieve=lambda _name: (_ for _ in ()).throw(exc))

        monkeypatch.setattr(_ai_insights_module, "OpenAI", FakeClient)
        ok, msg = validate_model("sk-test", "gpt-4o")
        assert ok is False
        assert "subscription tier" in msg.lower()

    def test_validate_model_handles_wrapped_tier_in_auth_error(self, monkeypatch):
        # The DO gateway pattern: AuthenticationError carrying a wrapped 403
        # tier rejection in its body.  Should classify as a tier issue, not
        # an invalid key.
        exc = _FakeAuthError("Error code: 401", body=_WRAPPED_TIER_BODY)

        class FakeClient:
            def __init__(self, *, api_key, base_url=None):
                self.models = SimpleNamespace(retrieve=lambda _name: (_ for _ in ()).throw(exc))

        monkeypatch.setattr(_ai_insights_module, "OpenAI", FakeClient)
        ok, msg = validate_model("sk-test", "gpt-4o")
        assert ok is False
        assert "subscription tier" in msg.lower()
        assert "invalid api key" not in msg.lower()


class TestRefreshEndpointSurfacesProviderError:
    def test_subscription_tier_error_returned_as_validation_error(
        self, client, flask_app, clean_ai_settings, monkeypatch
    ):
        monkeypatch.setenv("DO_AI_BASE_URL", "https://example.do.run")
        monkeypatch.setenv("DO_AI_API_KEY", "do-secret")

        def _raise(provider, *args, **kwargs):
            raise AIProviderError(
                "The selected AI model is not available for your subscription "
                "tier. Choose a different model in AI Settings."
            )

        monkeypatch.setattr(_api_data_module, "fetch_insights_for_provider", _raise)

        token = _login(client)
        resp = client.post("/api/v1/insights/refresh", headers=_bearer(token))
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["code"] == "validation_error"
        assert "subscription tier" in body["fields"]["insights"].lower()
