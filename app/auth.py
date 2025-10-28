from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User
from app import db
import pandas as pd
import os
from functools import wraps
from werkzeug.exceptions import Unauthorized
from corbado_python_sdk import Config, CorbadoSDK, UserEntity


auth = Blueprint('auth', __name__)


short_session_cookie_name = "cbo_short_session"
# Config has a default values for 'short_session_cookie_name' and 'BACKEND_API'
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
    return render_template('login.html')


@auth.route('/login', methods=['POST'])
def login_post():
    # login code goes here
    email = request.form.get('email')
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    user = User.query.filter_by(email=email).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or not check_password_hash(user.password, password):
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login')) # if the user doesn't exist or password is wrong, reload the page

    # fix for no admin user to make current user an admin
    user_test = User.query.filter_by(admin=True).first()
    if not user_test:
        user.admin = 1
        db.session.commit()

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)
    session['name'] = user.name
    session['email'] = user.email

    return redirect(url_for('main.index'))


@auth.route('/signup')
def signup():
    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    try:
        df = pd.read_sql('SELECT * FROM settings;', engine)

        if df['value'][0] == 1:
            return render_template('login.html')
    except:
        pass

    return render_template('signup.html')


@auth.route('/signup', methods=['POST'])
def signup_post():
    # code to validate and add user to database goes here
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')

    user = User.query.filter_by(email=email).first() # if this returns a user, then the email already exists in database

    if user: # if a user is found, we want to redirect back to signup page so user can try again
        return redirect(url_for('auth.signup'))

    # if no admin user, make new user an admin
    user_test = User.query.filter_by(admin=True).first()
    if not user_test:
        admin = 1
    else:
        admin = 0

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = User(email=email, name=name, password=generate_password_hash(password, method='scrypt'), admin=admin)

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()
    if user:  # if a user is found, we want to redirect back to signup page so user can try again
        flash('Email address already exists')
    return redirect(url_for('auth.login'))


@auth.route('/logout')
@login_required
def logout():
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
    project_id = os.environ['PROJECT_ID']
    frontend_uri = os.environ['FRONTEND_URI']

    return render_template('passkey_login.html', project_id=project_id, frontend_uri=frontend_uri)


@auth.route('/passkey_login_post')
def login_passkey_post():

    auth_user = get_authenticated_user_from_cookie()
    if auth_user:
        email_identifiers = sdk.identifiers.list_all_emails_by_user_id(user_id=auth_user.user_id)
        email = email_identifiers[0].value
    else:
        # use more sophisticated error handling in production
        raise Unauthorized()

    user = User.query.filter_by(email=email).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user:
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login'))  # if the user doesn't exist or password is wrong, reload the page

    # fix for no admin user to make current user an admin
    user_test = User.query.filter_by(admin=True).first()
    if not user_test:
        user.admin = 1
        db.session.commit()

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=True)
    session['name'] = user.name
    session['email'] = user.email

    return redirect(url_for('main.index'))


def get_authenticated_user_from_cookie() -> UserEntity | None:
    session_token = request.cookies.get('cbo_session_token')
    if not session_token:
        return None
    try:
        return sdk.sessions.validate_token(session_token)
    except:
        raise Unauthorized()