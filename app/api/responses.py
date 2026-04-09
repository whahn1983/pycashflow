"""JSON success response helpers for the API blueprint.

All successful responses share one of these shapes:

    Single resource (200 / 201):
        { "data": { ... } }

    Collection (200):
        { "data": [ ... ], "meta": { "total": N, "limit": N, "offset": N } }

    No content (204):
        <empty body>
"""

from flask import jsonify


def api_ok(data):
    """200 OK — single resource or pre-built payload."""
    return jsonify({"data": data}), 200


def api_created(data):
    """201 Created — newly created resource."""
    return jsonify({"data": data}), 201


def api_no_content():
    """204 No Content — successful mutation with nothing to return."""
    return "", 204


def api_list(items: list, *, total: int | None = None, limit: int | None = None, offset: int | None = None):
    """200 OK — collection with optional pagination metadata.

    Args:
        items:  Serialized list of resources.
        total:  Total count across all pages (omitted when not paginated).
        limit:  Page size requested by the client.
        offset: Page offset requested by the client.
    """
    body: dict = {"data": items}
    if total is not None or limit is not None or offset is not None:
        meta: dict = {}
        if total is not None:
            meta["total"] = total
        if limit is not None:
            meta["limit"] = limit
        if offset is not None:
            meta["offset"] = offset
        body["meta"] = meta
    return jsonify(body), 200
