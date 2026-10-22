"""
auth.py — shared-bearer-token auth middleware (D-S6).

One long-lived token, env-configured, checked on every request. No per-client
identity, no scopes — matches D01's ecosystem-wide pattern. Adding per-client
tokens later is additive (the check stays "is this token valid"), so this
isn't a shape that needs rework when hover-translate/stabbur arrive as callers.
"""

from __future__ import annotations

import os

from flask import jsonify, request

AUTH_TOKEN_ENV = "SMIA_AUTH_TOKEN"


def register_auth(app):
    @app.before_request
    def _require_bearer_token():
        # /ui's static HTML/CSS/JS must load unauthenticated — that's where
        # an operator pastes the token in the first place (D46's
        # database-exploration UI, chicken-and-egg otherwise). The data
        # those pages fetch (/providers, /health, and every lookup
        # endpoint) still goes through this check normally.
        if request.path == "/ui" or request.path.startswith("/ui/"):
            return None

        token = os.environ.get(AUTH_TOKEN_ENV)
        header = request.headers.get("Authorization", "")
        provided = header[len("Bearer "):] if header.startswith("Bearer ") else None

        # An unset token and a wrong token both resolve to 401, not two
        # different statuses — a caller can never distinguish "no token
        # configured" from "wrong token" anyway (nothing it sends would
        # work either way), and a 500 here previously leaked the server's
        # misconfiguration to any unauthenticated caller instead of just
        # looking like every other rejected request.
        if not token or provided != token:
            return jsonify({"error": "unauthorized"}), 401
