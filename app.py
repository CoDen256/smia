"""
app.py — smia's Flask entrypoint. Registers auth (D-S6), imports every
adapter module so provider registration runs before the first request, and
mounts the provider-catalog routes (`/providers`, `/health`) plus each
kind's lookup routes once that kind has an adapter.

Run: `flask --app app run` (dev) with DATABASE_URL and SMIA_AUTH_TOKEN set.
"""

from __future__ import annotations

import base64
import hashlib

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

import audio_cache
import cache
from auth import register_auth
from db.session import session_scope

app = Flask(__name__)
CORS(app)
app.json.ensure_ascii = False  # IPA/Norwegian characters as literal UTF-8, not \uXXXX escapes
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


@app.route("/stt", methods=["POST"])
def post_stt():
    from cache import ProviderLookupError, run_lookup
    from registry import ProviderRequiredError, UnknownProviderError, registry

    # /stt's request body is multipart audio, not JSON (tasks.md 7.2) — a
    # genuinely different shape from every other kind, so this bypasses
    # routes/generic.py's JSON-body _post entirely. `provider` is required
    # per request regardless of how many providers are configured (D17 /
    # proposal's explicit "{provider} (always required, even with one
    # provider configured)" — `/stt` deliberately opts out of the
    # lookup-cache's usual "optional when exactly one" default), checked
    # here before registry.resolve_provider ever gets a chance to default it.
    audio_file = request.files.get("audio")
    if audio_file is None:
        return jsonify({"error": "audio file is required (multipart field 'audio')"}), 400
    provider = request.form.get("provider")
    if not provider:
        return jsonify({"error": "provider is required", "available": registry.providers_for("stt")}), 400
    lang = request.form.get("lang")

    audio_bytes = audio_file.read()
    input_dict = {
        "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(),
        "audio_b64": base64.b64encode(audio_bytes).decode("ascii"),
        "lang": lang,
    }

    with session_scope() as db:
        try:
            payload, rid, _ = run_lookup(db, "stt", provider, input_dict)
        except ProviderRequiredError as exc:
            return jsonify({"error": "provider is required", "available": exc.available}), 400
        except UnknownProviderError as exc:
            return jsonify({"error": "unknown provider", "available": exc.available}), 400
        except ProviderLookupError as exc:
            return jsonify({"error": str(exc)}), 502
        response = jsonify(payload)
        response.headers["Location"] = f"/stt/{rid}"
        return response, 200


@app.route("/stt/<rid>", methods=["GET"])
def get_stt(rid):
    with session_scope() as db:
        payload = cache.fetch_by_id(db, "stt", rid)
    if payload is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(payload), 200


@app.route("/health", methods=["GET"])
def get_health():
    import health as health_module

    with session_scope() as db:
        return jsonify(health_module.get_all(db))


@app.route("/ui", methods=["GET"])
@app.route("/ui/", methods=["GET"])
def ui_index():
    return send_from_directory("ui", "index.html")


@app.route("/ui/<path:filename>", methods=["GET"])
def ui_asset(filename):
    return send_from_directory("ui", filename)


@app.route("/providers", methods=["GET"])
def providers():
    from registry import KINDS, registry

    return jsonify({kind: registry.providers_for(kind) for kind in KINDS})


if __name__ == "__main__":
    import os as _os

    debug = _os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=5055, debug=debug)
