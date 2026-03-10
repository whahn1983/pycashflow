from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, Settings
from app import db, limiter
from .getemail import send_new_user_notification
from .totp_utils import verify_totp, decrypt_totp_secret, verify_and_consume_backup_code
import logging
import os
from functools import wraps
from werkzeug.exceptions import Unauthorized
from corbado_python_sdk import Config, CorbadoSDK, UserEntity

logger = logging.getLogger(__name__)

# Pre-computed hash used to perform a constant-time dummy check when the
# submitted email doesn't match any user, preventing username enumeration
# via response-time differences.
_DUMMY_HASH = generate_password_hash('__dummy__', method='scrypt')

auth = Blueprint('auth', __name__)


short_session_cookie_name = "cbo_short_session"

# Read environment variables safely (returns None if missing)
API_SECRET = os.getenv("API_SECRET")
PROJECT_ID = os.getenv("PROJECT_ID")
FRONTEND_URI = os.getenv("FRONTEND_URI")

corbado_config = None
corbado_enabled = all([API_SECRET, PROJECT_ID, FRONTEND_URI])

# Config has a default values for 'short_session_cookie_name' and 'BACKEND_API'
if corbado_enabled:
    config: Config = Config(
        api_secret=os.environ['API_SECRET'],
        project_id=os.environ['PROJECT_ID'],
        frontend_api=os.environ['FRONTEND_URI'],
        backend_api="https://backendapi.cloud.corbado.io",
    )
    config.frontend_api = os.environ['FRONTEND_URI']

    # Initialize SDK
    sdk: CorbadoSDK = CorbadoSDK(config=config)


@auth.route('/login')
def login():
    return render_template('login.html', corbado_enabled=corbado_enabled)


@auth.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login_post():
    # login code goes here
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    user = User.query.filter_by(email=email).first()

    # Always run the hash comparison to prevent username enumeration via timing.
    # When no user is found we compare against a dummy hash so the response time
    # is indistinguishable from a wrong-password attempt for a real user.
    if user:
        password_ok = check_password_hash(user.password, password)
    else:
        check_password_hash(_DUMMY_HASH, password)
        password_ok = False

    if not password_ok:
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login'))

    # check if the user account is active
    if not user.is_active:
        flash('Your account is pending approval. Please contact an administrator.')
        return redirect(url_for('auth.login'))

    # If 2FA is enabled, redirect to TOTP verification step
    if user.twofa_enabled:
        session['twofa_pending_user_id'] = user.id
        session['twofa_remember'] = remember
        return redirect(url_for('auth.login_2fa'))

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)
    session['name'] = user.name
    session['email'] = user.email

    return redirect(url_for('main.index'))


@auth.route('/login/2fa', methods=['GET'])
def login_2fa():
    if 'twofa_pending_user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('2fa_verify.html')


@auth.route('/login/2fa', methods=['POST'])
@limiter.limit("10 per minute")
def login_2fa_post():
    pending_id = session.get('twofa_pending_user_id')
    if not pending_id:
        flash('Session expired. Please log in again.')
        return redirect(url_for('auth.login'))

    user = User.query.get(pending_id)
    if not user:
        session.pop('twofa_pending_user_id', None)
        session.pop('twofa_remember', None)
        flash('User not found. Please log in again.')
        return redirect(url_for('auth.login'))

    code = request.form.get('code', '').strip()
    use_backup = request.form.get('use_backup')

    verified = False

    if use_backup:
        # Attempt backup code verification
        verified = verify_and_consume_backup_code(user, code)
        if not verified:
            flash('Invalid or already-used backup code.')
            return redirect(url_for('auth.login_2fa'))
    else:
        # Attempt TOTP verification
        if user.twofa_secret:
            plain_secret = decrypt_totp_secret(user.twofa_secret)
            verified = verify_totp(plain_secret, code)
        if not verified:
            flash('Invalid or expired verification code.')
            return redirect(url_for('auth.login_2fa'))

    # Verification passed – complete login
    remember = session.pop('twofa_remember', False)
    session.pop('twofa_pending_user_id', None)

    login_user(user, remember=remember)
    session['name'] = user.name
    session['email'] = user.email

    return redirect(url_for('main.index'))


@auth.route('/signup')
def signup():
    try:
        setting = Settings.query.filter_by(name='signup').first()
        if setting and setting.value == 1:
            return render_template('login.html')
    except Exception as exc:
        logger.debug("Settings table not available: %s", exc)

    return render_template('signup.html')


@auth.route('/signup', methods=['POST'])
@limiter.limit("5 per minute")
def signup_post():
    # code to validate and add user to database goes here
    email = (request.form.get('email') or '').strip().lower()
    name = request.form.get('name')
    password = request.form.get('password')

    user = User.query.filter_by(email=email).first() # if this returns a user, then the email already exists in database

    if user: # if a user is found, we want to redirect back to signup page so user can try again
        flash('Email address already exists')
        return redirect(url_for('auth.signup'))

    # Signup never auto-elevates anyone to global admin regardless of whether an
    # admin already exists.  The bootstrap env-var path in __init__.py is the sole
    # mechanism for creating the first global admin account.
    admin = True
    is_global_admin = False
    is_active = False

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = User(
        email=email,
        name=name,
        password=generate_password_hash(password, method='scrypt'),
        admin=admin,
        is_global_admin=is_global_admin,
        is_active=is_active
    )

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    # Send notification to global admin if this is not the first user
    # (first user becomes global admin, so no need to notify themselves)
    if not is_global_admin:
        try:
            send_new_user_notification(name, email)
        except Exception as exc:
            # Don't fail registration if email notification fails
            logger.warning("Failed to send new user notification for %s: %s", email, exc)

    return redirect(url_for('auth.login'))


@auth.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('main.index'))


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.admin:
            return f(*args, **kwargs)
        else:
            return redirect(url_for('main.index'))
    return decorated_function


def global_admin_required(f):
    """
    Decorator for routes that require global admin access.
    Only users with is_global_admin=True can access.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.is_global_admin:
            return f(*args, **kwargs)
        else:
            flash('Global admin access required')
            return redirect(url_for('main.index'))
    return decorated_function


def account_owner_required(f):
    """
    Decorator for routes that require account owner access.
    Guest users (those with account_owner_id set) cannot access.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.account_owner_id is not None:
            flash('Account owner access required')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


@auth.route('/passkey_login')
def login_passkey():

    if corbado_enabled:
        project_id = os.environ['PROJECT_ID']
        frontend_uri = os.environ['FRONTEND_URI']

        return render_template('passkey_login.html', project_id=project_id, frontend_uri=frontend_uri)
    else:
        flash('Passkey authentication is not enabled.')
        return redirect(url_for('auth.login'))


@auth.route('/passkey_login_post', methods=['POST'])
@limiter.limit("10 per minute")
def login_passkey_post():

    if not corbado_enabled:
        flash('Passkey authentication is not enabled.')
        return redirect(url_for('auth.login'))

    auth_user = get_authenticated_user_from_cookie()
    if auth_user:
        email_identifiers = sdk.identifiers.list_all_emails_by_user_id(user_id=auth_user.user_id)
        email = email_identifiers[0].value
    else:
        # use more sophisticated error handling in production
        raise Unauthorized()

    user = User.query.filter_by(email=email).first()

    # check if the user actually exists
    if not user:
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login'))

    # check if the user account is active
    if not user.is_active:
        flash('Your account is pending approval. Please contact an administrator.')
        return redirect(url_for('auth.login'))

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=True)
    session['name'] = user.name
    session['email'] = user.email

    return redirect(url_for('main.index'))


def get_authenticated_user_from_cookie() -> UserEntity | None:
    if not corbado_enabled:
        return None

    session_token = request.cookies.get('cbo_session_token')
    if not session_token:
        return None
    try:
        return sdk.sessions.validate_token(session_token)
    except Exception as exc:
        logger.warning("Passkey session token validation failed: %s", exc)
        raise Unauthorized()
