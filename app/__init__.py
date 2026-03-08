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

    PROJECT_ID: str = os.environ.get("PROJECT_ID") or ""
    API_SECRET: str = os.environ.get("API_SECRET") or ""
    FRONTEND_URI: str = os.environ.get("FRONTEND_URI") or ""

    # Use the API_SECRET from the environment variables
    app.config["API_SECRET"] = API_SECRET

    # Pass PROJECT_ID as a context variable to templates
    app.config["PROJECT_ID"] = PROJECT_ID

    # Pass FRONTEND_URI as a context variable to templates
    app.config["FRONTEND_URI"] = FRONTEND_URI

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
    _secure_cookies = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() != 'false'
    app.config['SESSION_COOKIE_SECURE'] = _secure_cookies
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_SECURE'] = _secure_cookies
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

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

    # Don't use db.create_all() - use flask db upgrade instead
    # with app.app_context():
    #     db.create_all()

    # Bootstrap global admin from environment variables.
    # Set BOOTSTRAP_ADMIN_EMAIL + BOOTSTRAP_ADMIN_PASSWORD to create the initial
    # admin account on first startup instead of relying on signup-flow auto-elevation.
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
                logger.warning(
                    "Bootstrap admin creation skipped (%s: %s); tables may not exist yet",
                    type(exc).__name__, exc,
                )

    return app
