from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import secrets
import os
import logging
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
csrf = CSRFProtect()


def create_app():

    app = Flask(__name__, static_url_path='/static')

    # Load environment variables from .env file
    load_dotenv()

    app.config["PASSKEY_RP_ID"] = os.environ.get("PASSKEY_RP_ID", "")
    app.config["PASSKEY_RP_NAME"] = os.environ.get("PASSKEY_RP_NAME", "PyCashFlow")
    app.config["PASSKEY_ORIGIN"] = os.environ.get("PASSKEY_ORIGIN", "")

    basedir = os.path.abspath(os.path.dirname(__file__))

    # Prefer a stable SECRET_KEY from the environment so sessions survive restarts.
    # Fall back to a per-process random value only when no key is configured.
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)

    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data/db.sqlite')

    # Harden session and remember-me cookies.
    # SESSION_COOKIE_SECURE defaults to True; set SESSION_COOKIE_SECURE=false in .env
    # only when running without TLS (e.g. local dev over plain HTTP).
    # Use == 'true' (not != 'false') so that any value other than exactly 'true'
    # keeps cookies secure, preventing accidental exposure from typos like 'False'.
    _secure_cookies = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() == 'true'
    app.config['SESSION_COOKIE_SECURE'] = _secure_cookies
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_SECURE'] = _secure_cookies
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

    # Reject request bodies larger than 2 MB before any route handler runs,
    # preventing the server from buffering huge uploads into memory.
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB

    # Configure Flask-Limiter storage backend.
    # Defaults to in-memory (single-process only). For multi-process deployments,
    # set RATELIMIT_STORAGE_URI to a Redis URL, e.g. redis://localhost:6379/0
    app.config['RATELIMIT_STORAGE_URI'] = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    csrf.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        # since the user_id is just the primary key of our user table, use it in the query for the user
        return User.query.get(int(user_id))

    # blueprint for auth routes in our app
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # blueprint for non-auth parts of app
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # API v1 blueprint — CSRF-exempt; uses Bearer token auth
    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix="/api/v1")
    csrf.exempt(api_blueprint)

    # Don't use db.create_all() - use flask db upgrade instead
    # with app.app_context():
    #     db.create_all()

    # Bootstrap global admin from environment variables.
    # Set BOOTSTRAP_ADMIN_EMAIL + BOOTSTRAP_ADMIN_PASSWORD only for initial setup.
    # IMPORTANT: Remove these environment variables after the first admin account
    # has been created to avoid leaving credentials in the process environment.
    _bootstrap_email = os.environ.get('BOOTSTRAP_ADMIN_EMAIL')
    _bootstrap_password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD')
    if _bootstrap_email and _bootstrap_password:
        with app.app_context():
            try:
                from .models import User
                from werkzeug.security import generate_password_hash
                if not User.query.filter_by(is_global_admin=True).first():
                    if not User.query.filter_by(email=_bootstrap_email).first():
                        bootstrap_user = User(
                            email=_bootstrap_email,
                            name='Admin',
                            password=generate_password_hash(_bootstrap_password, method='scrypt'),
                            admin=True,
                            is_global_admin=True,
                            is_active=True,
                        )
                        db.session.add(bootstrap_user)
                        db.session.commit()
            except Exception as exc:
                # Expected during pre-migration startup when tables don't exist yet.
                logger.debug(
                    "Bootstrap admin creation skipped (%s); tables may not exist yet",
                    type(exc).__name__,
                )

    return app
