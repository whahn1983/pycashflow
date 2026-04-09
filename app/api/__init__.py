"""API v1 Blueprint for PyCashFlow.

Registered in ``app/__init__.py`` with ``url_prefix="/api/v1"``.
All routes in this blueprint are CSRF-exempt and use Bearer token auth.

Adding new route modules
------------------------
1. Create ``app/api/routes/<domain>.py`` and decorate routes with ``@api``.
2. Import the module at the bottom of this file so Flask registers the routes.
"""

from flask import Blueprint

api = Blueprint("api", __name__)

# Register error handlers on the api blueprint (also handles app-wide /api/ 404s)
from .errors import register_error_handlers  # noqa: E402
register_error_handlers(api)

# Import route modules — side-effect: routes are registered on ``api``
from .routes import auth  # noqa: E402, F401
from .routes import data  # noqa: E402, F401
