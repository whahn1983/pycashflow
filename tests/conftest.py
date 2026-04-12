"""
Pytest configuration for Flask integration tests.

IMPORTANT: This file is imported by pytest BEFORE any test_*.py files.
Other test files (e.g. test_projection_engine.py) install module stubs for
app/db/models so they can unit-test pure business logic without a database.
Those stubs replace sys.modules entries at import time.

By creating and fully initialising the real Flask test app HERE (at conftest
module load time), we capture all real references before any stubs are
installed. The fixtures below then expose those captured objects safely.
"""

import os
import pytest
from datetime import datetime

# ── Test environment — set before the real app is imported ───────────────────
# DATABASE_URL must be set BEFORE create_app() is called: Flask-SQLAlchemy
# reads it when create_app() calls db.init_app(app), creating the engine at
# that point.  Overriding app.config afterwards has no effect on the engine.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "pytest-secret-key-32chars-minimum!")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("APP_SECRET", "pytest-app-secret-for-crypto-utils-32!")
os.environ.setdefault("PASSKEY_RP_ID", "localhost")
os.environ.setdefault("PASSKEY_RP_NAME", "PyCashFlow Test")
os.environ.setdefault("PASSKEY_ORIGIN", "http://localhost")
os.environ.setdefault("PAYMENTS_ENABLED", "false")

# ── Capture real app references BEFORE stubs are set up ──────────────────────
# conftest.py is loaded before test_*.py files, so all imports here use the
# real modules.  Stubs installed later do NOT affect already-bound names.
from app import create_app as _create_app, db as _db               # noqa: E402
from app.models import (
    User as _User,
    Balance as _Balance,
    Settings as _Settings,
    TextSettings as _TextSettings,
    PasskeyCredential as _PasskeyCredential,
    PasswordSetupToken as _PasswordSetupToken,
)  # noqa: E402
from app.password_setup import (  # noqa: E402
    build_password_setup_url as _build_password_setup_url,
    create_password_setup_token as _create_password_setup_token,
)
from app.api.routes import billing as _billing_routes  # noqa: E402
import _helpers  # noqa: F401  – pre-load real cashflow refs before any test-module stubs
from werkzeug.security import generate_password_hash                # noqa: E402

# ── Create the test Flask app eagerly (before stubs) ─────────────────────────
# Calling create_app() here ensures internal blueprint/model imports happen
# with the real modules, so route handlers work correctly in route tests.
_test_app = _create_app()
_test_app.config.update(
    {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "WTF_CSRF_CHECK_DEFAULT": False,
        "SESSION_COOKIE_SECURE": False,
        "SECRET_KEY": "pytest-secret-key-32chars-minimum!",
    }
)

# ── Seed the in-memory database once for the whole session ───────────────────
with _test_app.app_context():
    _db.create_all()

    _admin = _User(
        email="admin@test.local",
        password=generate_password_hash("testpass123", method="scrypt"),
        name="Test Admin",
        admin=True,
        is_active=True,
        account_owner_id=None,
        is_global_admin=False,
    )
    _db.session.add(_admin)
    _db.session.commit()
    _ADMIN_USER_ID: int = _admin.id

    # Seed an initial balance so the dashboard route doesn't start from zero
    _db.session.add(
        _Balance(amount="5000.00", date=datetime.today().date(), user_id=_ADMIN_USER_ID)
    )
    _db.session.commit()


# ── Pytest fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def flask_app():
    """Session-scoped real Flask app backed by an in-memory SQLite database."""
    return _test_app


@pytest.fixture()
def client(flask_app):
    """Per-test Flask test client (unauthenticated)."""
    return flask_app.test_client()


@pytest.fixture()
def auth_client(flask_app):
    """Per-test Flask test client with an active admin session."""
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = str(_ADMIN_USER_ID)
        sess["_fresh"] = True
    return c


@pytest.fixture()
def app_ctx(flask_app):
    """Push an application context; useful for tests that query the DB directly."""
    with flask_app.app_context():
        yield _db


@pytest.fixture(scope="session")
def user_model():
    """Return the real User model captured before any module stubs are installed."""
    return _User


@pytest.fixture(scope="session")
def passkey_credential_model():
    """Return the real PasskeyCredential model captured before stubs are installed."""
    return _PasskeyCredential


@pytest.fixture(scope="session")
def password_setup_token_model():
    """Return the real PasswordSetupToken model captured before stubs are installed."""
    return _PasswordSetupToken


@pytest.fixture(scope="session")
def settings_model():
    """Return the real Settings model captured before any module stubs are installed."""
    return _Settings


@pytest.fixture(scope="session")
def text_settings_model():
    """Return the real TextSettings model captured before any module stubs are installed."""
    return _TextSettings


@pytest.fixture(scope="session")
def password_setup_helpers():
    """Return password setup helpers captured before any module stubs are installed."""
    return {
        "build_url": _build_password_setup_url,
        "create_token": _create_password_setup_token,
    }


@pytest.fixture(scope="session")
def billing_routes_module():
    """Return billing routes module captured before any module stubs are installed."""
    return _billing_routes
