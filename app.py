"""
app.py — smia's Flask entrypoint. Registers auth (D-S6), imports every
adapter module so provider registration runs before the first request, and
mounts the provider-catalog routes (`/providers`, `/health`) plus each
kind's lookup routes once that kind has an adapter.

Run: `flask --app app run` (dev) with DATABASE_URL and SMIA_AUTH_TOKEN set.
"""

from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS

from auth import register_auth

app = Flask(__name__)
CORS(app)
register_auth(app)

import adapters  # noqa: F401,E402  (imported for registration side-effects only)


@app.route("/health", methods=["GET"])
def health():
    # Per-provider last-success/last-failure/quota tracking lands with
    # provider-catalog (task 8.2) — placeholder shape for now.
    return jsonify({})


@app.route("/providers", methods=["GET"])
def providers():
    from registry import KINDS, registry

    return jsonify({kind: registry.providers_for(kind) for kind in KINDS})


if __name__ == "__main__":
    app.run(port=5055, debug=True)
