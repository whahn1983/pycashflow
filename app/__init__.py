from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import secrets
import os
from flask_migrate import Migrate
from dotenv import load_dotenv


# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()
migrate = Migrate()


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
    secret = secrets.token_urlsafe(16)

    app.config['SECRET_KEY'] = secret
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data/db.sqlite')

    db.init_app(app)
    migrate.init_app(app, db)

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

    with app.app_context():
        db.create_all()

    return app
