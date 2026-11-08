"""
routes/ipa.py — `/ipa`'s own route, replacing the generic `POST /<kind>`
factory (`routes/generic.py`'s `_post` calls `run_lookup` exactly once and
cannot express the two-stage whole-phrase-then-split flow — design D8).
`GET /ipa/{id}` stays the plain cache-read every other kind uses.

Flow (design D4/D7):
  1. Resolve the provider once for the whole request.
  2. Try the caller's `text` as a phrase, trying each of `norwegian-input`'s
     query variants in turn (most-faithful-to-the-caller first) until one
     returns non-empty candidates.
  3. If a variant hit, or the input is a single token, the response is
     `mode: "phrase"` — today's exact shape for a single-word request.
  4. Otherwise `tokenize()` the original input and look each token up
     against the same provider through the ordinary `run_lookup` runner, so
     every token gets its own reusable cache row (lookup-cache's "one
     request may create several cache resources").
  5. The assembled result is cached under the *caller's own* input's
     resource id, independent of whichever sub-lookup answered it.

A `ProviderLookupError` at any stage propagates as a 502 — a broken
provider looks broken rather than silently degrading into a different
response shape (design D6).
"""

from __future__ import annotations

from flask import jsonify, request

from cache import ProviderLookupError, fetch_by_id, input_hash, resource_id, run_lookup
from db.models import LookupCache
from db.session import session_scope
from norwegian import query_variants, tokenize
from registry import ProviderRequiredError, UnknownProviderError, registry


def _post():
    body = request.get_json(silent=True) or {}
    if "text" not in body or "lang" not in body:
        return jsonify({"error": "text and lang are required"}), 400
    text, lang = body["text"], body["lang"]
    requested_provider = body.get("provider")
    force_refresh = bool(body.get("forceRefresh", False))

    with session_scope() as db:
        try:
            provider = registry.resolve_provider("ipa", requested_provider)
        except ProviderRequiredError as exc:
            return jsonify({"error": "provider is required", "available": exc.available}), 400
        except UnknownProviderError as exc:
            return jsonify({"error": "unknown provider", "available": exc.available}), 400

        own_input = {"text": text, "lang": lang}
        ihash = input_hash(own_input)
        rid = resource_id("ipa", provider, ihash)

        if not force_refresh:
            cached = fetch_by_id(db, "ipa", rid)
            if cached is not None:
                response = jsonify(cached)
                response.headers["Location"] = f"/ipa/{rid}"
                return response, 200

        try:
            result = _resolve(db, provider, text, lang, force_refresh)
        except ProviderLookupError as exc:
            return jsonify({"error": str(exc)}), 502

        row = db.get(LookupCache, rid)
        if row is None:
            db.add(LookupCache(id=rid, kind="ipa", provider=provider, input_hash=ihash, payload=result))
        else:
            row.payload = result
        db.commit()

        response = jsonify(result)
        response.headers["Location"] = f"/ipa/{rid}"
        return response, 200


def _resolve(db, provider: str, text: str, lang: str, force_refresh: bool) -> dict:
    # Whole-phrase attempt, crossing the norwegian-input query variants
    # (design D7) — so "en kalv" tries "en kalv" then "kalv" as a phrase
    # before anything is tokenized.
    first_variant_payload = None
    phrase_payload = None
    for i, variant in enumerate(query_variants(text)):
        payload, _rid, _cached = run_lookup(
            db, "ipa", provider, {"text": variant, "lang": lang}, force_refresh=force_refresh
        )
        if i == 0:
            first_variant_payload = payload
        if payload["candidates"]:
            phrase_payload = payload
            break

    if phrase_payload is not None:
        return {"provider": provider, "mode": "phrase", "candidates": phrase_payload["candidates"]}

    tokens = tokenize(text)
    if len(tokens) <= 1:
        # Single-token input never splits (design D6) — report whatever
        # the phrase attempt on the caller's own text produced, including
        # an empty list.
        return {"provider": provider, "mode": "phrase", "candidates": first_variant_payload["candidates"]}

    token_entries = []
    for token in tokens:
        tok_payload, _rid, _cached = run_lookup(
            db, "ipa", provider, {"text": token, "lang": lang}, force_refresh=force_refresh
        )
        token_entries.append({"text": token, "candidates": tok_payload["candidates"]})

    result = {"provider": provider, "mode": "per_word", "tokens": token_entries}
    if all(len(entry["candidates"]) == 1 for entry in token_entries):
        result["joined"] = " ".join(entry["candidates"][0]["ipa"] for entry in token_entries)
    return result


def _get(rid):
    with session_scope() as db:
        payload = fetch_by_id(db, "ipa", rid)
    if payload is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(payload), 200


def register_ipa_routes(app):
    app.add_url_rule("/ipa", endpoint="post_ipa", view_func=_post, methods=["POST"])
    app.add_url_rule("/ipa/<rid>", endpoint="get_ipa", view_func=_get, methods=["GET"])
