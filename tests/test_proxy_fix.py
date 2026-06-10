"""
Tests for the ProxyFix middleware wiring in app/__init__.py.

ProxyFix lets the app resolve the real client IP from X-Forwarded-For when
deployed behind a reverse proxy, so Flask-Limiter keys per-IP rate limits on
the actual client rather than the proxy's internal address.

These tests build dedicated app instances (varying TRUSTED_PROXY_COUNT) and
register a temporary route that reports request.remote_addr / request.is_secure,
rather than reaching into Flask-Limiter internals.
"""

import os
from contextlib import contextmanager

from flask import request


@contextmanager
def _env(**overrides):
    """Temporarily set environment variables, restoring prior values after."""
    sentinel = object()
    previous = {k: os.environ.get(k, sentinel) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, prev in previous.items():
            if prev is sentinel:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def _build_app(create_app, trusted_proxy_count):
    """Create an app with TRUSTED_PROXY_COUNT set, plus a probe route."""
    with _env(TRUSTED_PROXY_COUNT=trusted_proxy_count):
        app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @app.route("/_proxy_probe")
    def _proxy_probe():
        return {
            "remote_addr": request.remote_addr,
            "is_secure": request.is_secure,
        }

    return app


def test_forwarded_ip_is_used_behind_proxy(create_app):
    """With one trusted hop, X-Forwarded-For/-Proto drive remote_addr/is_secure."""
    app = _build_app(create_app, "1")
    client = app.test_client()

    resp = client.get(
        "/_proxy_probe",
        headers={
            "X-Forwarded-For": "203.0.113.7",
            "X-Forwarded-Proto": "https",
        },
    )

    assert resp.json["remote_addr"] == "203.0.113.7"
    assert resp.json["is_secure"] is True


def test_direct_connection_uses_test_client_default(create_app):
    """Without forwarded headers, remote_addr is the test client default."""
    app = _build_app(create_app, "1")
    client = app.test_client()

    resp = client.get("/_proxy_probe")

    assert resp.json["remote_addr"] == "127.0.0.1"
    assert resp.json["is_secure"] is False


def test_spoofed_header_ignored_when_proxy_count_zero(create_app):
    """With TRUSTED_PROXY_COUNT=0, ProxyFix is off and forwarded headers can't
    change the apparent client IP, so spoofing is ignored."""
    app = _build_app(create_app, "0")
    client = app.test_client()

    resp = client.get(
        "/_proxy_probe",
        headers={
            "X-Forwarded-For": "203.0.113.7",
            "X-Forwarded-Proto": "https",
        },
    )

    assert resp.json["remote_addr"] == "127.0.0.1"
    assert resp.json["is_secure"] is False
