"""
routes/generic.py — the reusable `POST /<kind>` and `GET /<kind>/{id}`
view-function factories every kind's blueprint plugs into (D-S3). Per-kind
code only supplies: how to pull `{provider, ...input}` out of the request
JSON, and (via the registry) which adapters exist.

No kind calls `register_lookup_routes` yet — real endpoints land with their
first adapter in later tasks. `tests/test_cache.py` exercises this generic
layer directly against a throwaway test kind.
"""

from __future__ import annotations

from flask import jsonify, request

from cache import ProviderLookupError, fetch_by_id, run_lookup
from db.session import session_scope
from registry import ProviderRequiredError, UnknownProviderError


def register_lookup_routes(
    app, kind: str, extract_input, *, force_refresh_param: str = "forceRefresh", register_get: bool = True
):
    """`extract_input(body: dict) -> dict` returns the normalized input dict
    (everything the cache hashes on, i.e. the request body minus `provider`
    and minus `force_refresh_param`). Raise ValueError for a malformed body
    — it's turned into a 400."""

    def _post():
        body = request.get_json(silent=True) or {}
        provider = body.get("provider")
        force_refresh = bool(body.get(force_refresh_param, False))
        try:
            input_dict = extract_input(body)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        with session_scope() as db:
            try:
                payload, rid, _ = run_lookup(db, kind, provider, input_dict, force_refresh=force_refresh)
            except ProviderRequiredError as exc:
                return jsonify({"error": "provider is required", "available": exc.available}), 400
            except UnknownProviderError as exc:
                return jsonify({"error": "unknown provider", "available": exc.available}), 400
            except ProviderLookupError as exc:
                return jsonify({"error": str(exc)}), 502
            response = jsonify(payload)
            response.headers["Location"] = f"/{kind}/{rid}"
            return response, 200

    def _get(rid):
        with session_scope() as db:
            payload = fetch_by_id(db, kind, rid)
        if payload is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(payload), 200

    app.add_url_rule(f"/{kind}", endpoint=f"post_{kind}", view_func=_post, methods=["POST"])
    if register_get:
        app.add_url_rule(f"/{kind}/<rid>", endpoint=f"get_{kind}", view_func=_get, methods=["GET"])
