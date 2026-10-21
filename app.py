"""
app.py — smia's Flask entrypoint. Registers auth (D-S6), imports every
adapter module so provider registration runs before the first request, and
mounts the provider-catalog routes (`/providers`, `/health`) plus each
kind's lookup routes once that kind has an adapter.

Run: `flask --app app run` (dev) with DATABASE_URL and SMIA_AUTH_TOKEN set.
"""

from __future__ import annotations

from flask import Flask, Response, jsonify
from flask_cors import CORS

import audio_cache
import cache
from auth import register_auth
from db.session import session_scope

app = Flask(__name__)
CORS(app)
register_auth(app)

import adapters  # noqa: F401,E402  (imported for registration side-effects only)
from routes.generic import register_lookup_routes  # noqa: E402


def _extract_inflections_input(body: dict) -> dict:
    if "word" not in body or "lang" not in body:
        raise ValueError("word and lang are required")
    return {"word": body["word"], "lang": body["lang"]}


register_lookup_routes(app, "inflections", _extract_inflections_input)


def _extract_ipa_input(body: dict) -> dict:
    if "text" not in body or "lang" not in body:
        raise ValueError("text and lang are required")
    return {"text": body["text"], "lang": body["lang"]}


register_lookup_routes(app, "ipa", _extract_ipa_input)


def _extract_tts_input(body: dict) -> dict:
    if "text" not in body or "lang" not in body:
        raise ValueError("text and lang are required")
    return {"text": body["text"], "lang": body["lang"]}


# /tts has its own GET: the tts-api spec's `GET /tts/{sha256}` (raw audio
# bytes, keyed on the *audio's* content hash) shares a path shape with the
# generic lookup-cache `GET /<kind>/{id}` (metadata, keyed on the
# *request's* resource id) — register_get=False skips the generic GET so
# this single handler can serve both: resource-id metadata if it matches a
# cached /tts lookup, else raw bytes if it matches a cached audio clip.
register_lookup_routes(app, "tts", _extract_tts_input, register_get=False)


@app.route("/tts/<key>", methods=["GET"])
def get_tts(key):
    with session_scope() as db:
        payload = cache.fetch_by_id(db, "tts", key)
        if payload is not None:
            return jsonify(payload), 200
        audio = audio_cache.fetch(db, key)
        if audio is not None:
            data, content_type = audio
            return Response(data, mimetype=content_type)
    return jsonify({"error": "not found"}), 404


def _extract_translations_input(body: dict) -> dict:
    if "text" not in body or "from" not in body or "to" not in body:
        raise ValueError("text, from, and to are required")
    return {"text": body["text"], "from": body["from"], "to": body["to"]}


register_lookup_routes(app, "translations", _extract_translations_input)


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
