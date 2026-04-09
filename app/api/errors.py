"""Standardised JSON error responses for the API blueprint.

All API errors share the shape:

    {
        "error":  "<human-readable message>",
        "code":   "<machine-readable slug>",
        "status": <HTTP status code as integer>
    }

Validation errors additionally include a ``fields`` dict:

    {
        "error":  "Validation failed",
        "code":   "validation_error",
        "status": 422,
        "fields": { "<field_name>": "<reason>", ... }
    }
"""

from flask import jsonify


def api_error(message: str, code: str, status: int, fields: dict | None = None):
    """Return a JSON error response.

    Args:
        message: Human-readable description of the error.
        code:    Machine-readable slug (e.g. ``"not_found"``).
        status:  HTTP status code.
        fields:  Optional dict of per-field validation messages.
    """
    body = {"error": message, "code": code, "status": status}
    if fields is not None:
        body["fields"] = fields
    return jsonify(body), status


# ── Convenience wrappers ──────────────────────────────────────────────────────

def not_found(message: str = "Resource not found"):
    return api_error(message, "not_found", 404)


def unauthorized(message: str = "Authentication required"):
    return api_error(message, "unauthorized", 401)


def forbidden(message: str = "You do not have permission to perform this action"):
    return api_error(message, "forbidden", 403)


def validation_error(fields: dict, message: str = "Validation failed"):
    return api_error(message, "validation_error", 422, fields=fields)


def internal_error(message: str = "An unexpected error occurred"):
    return api_error(message, "internal_error", 500)


# ── Blueprint-level error handlers ───────────────────────────────────────────

def register_error_handlers(blueprint):
    """Attach JSON error handlers to *blueprint*.

    Flask calls these handlers only when the error originates from a route
    registered on *blueprint* (or from an ``abort()`` inside such a route).
    App-wide 404s that don't match any route are handled separately in
    ``app/api/__init__.py`` via ``app.register_error_handler``.
    """

    @blueprint.app_errorhandler(404)
    def handle_404(exc):
        # Only intercept requests that started with /api/ to avoid
        # hijacking HTML 404 pages for the server-rendered app.
        from flask import request
        if request.path.startswith("/api/"):
            return not_found()
        # Let Flask's default handler render the HTML 404 page.
        from werkzeug.exceptions import NotFound
        raise NotFound()

    @blueprint.app_errorhandler(405)
    def handle_405(exc):
        from flask import request
        if request.path.startswith("/api/"):
            return api_error("Method not allowed", "method_not_allowed", 405)
        raise exc
