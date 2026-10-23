## Why

Every provider adapter implemented so far (`hf_whisper`, `deepl`, `google_translate`, `bing_translate`, `libretranslate`, `dictcc_api`) talks to its provider via hand-rolled `requests` calls. For providers that publish and maintain an official client library (Hugging Face, DeepL, and the ElevenLabs provider about to be added), hand-rolling means re-solving problems the library already solves correctly — request signing/headers, retry/backoff behavior, typed error responses — and silently drifting from the vendor's supported integration path as their API evolves.

Explored live (with the user) rather than left to task-time guessing: Google's unofficial `translate_a/single` endpoint has no legitimate official client, and the one actively-maintained community alternative (`translators`, by UlionTse) would throw away the structured `dict[]` sense data `google_translate.py` currently parses and `translate-multi-candidate` depends on — so Google stays on raw HTTP, deliberately, not by default. Bing has no such structured data to lose (today's adapter already extracts one plain string), so it moves to `translators` instead of its own hand-rolled edge-auth exchange. LibreTranslate turned out not worth keeping at all once examined: no legitimate maintained client exists for it (`libretranslatepy` is stale since April 2024), and the provider itself has already proven unreliable in practice (its own adapter's docstring records public mirrors being down/blocking and the official instance now requiring a paid key) — rather than keep nursing a flaky provider with no good client option, it's dropped entirely.

## What Changes

- Swap `adapters/hf_whisper.py` to use `huggingface_hub`'s `InferenceClient` instead of raw `requests` calls against `router.huggingface.co`, passing the language parameter via `extra_body={"generate_kwargs": {...}}`.
- Swap `adapters/deepl.py` to use the official `deepl` Python package instead of raw `requests` calls against `api-free.deepl.com`, mapping `QuotaExceededException`/`AuthenticationException`/`ConnectionException` (and the base `DeepLException`) to `ProviderLookupError`.
- The `elevenlabs` adapter being added in `add-elevenlabs-provider` uses the official `elevenlabs` Python SDK from the start (no raw-HTTP version to migrate away from).
- Swap `adapters/bing_translate.py` to use the `translators` package (`translators.translate_text(..., translator="bing")`) instead of its own hand-rolled edge-auth-token exchange — confirmed live that Microsoft moved/retired the undocumented `edge.microsoft.com/translate/auth` endpoint this adapter depends on, so this is also a reliability fix, not just a style swap.
- **Keep `adapters/google_translate.py` on raw HTTP, deliberately.** `translators` supports Google too, but it returns one plain string per call — using it would throw away the structured `dict[]` sense/dictionary data this adapter parses directly from Google's raw response, which `translate-multi-candidate` depends on. No swap here is the considered choice, not an oversight.
- **Drop the `libretranslate` provider entirely**: delete `adapters/libretranslate.py` and its registration, remove it from `/translations`' provider set, remove its tests. No replacement — the provider is judged not worth keeping, not merely "no library available."
- Document, in `dictcc_api.py`/`dictcc_static.py`'s docstrings, why no swap applies (reverse-engineered mobile-app backend / local data import — no client exists for either).
- No request/response contract changes beyond the libretranslate removal — this is otherwise a transport-layer swap. Every existing test in `tests/test_translate_adapters.py` and the HF/DeepL-specific tests must keep passing in intent (mocking each SDK/library instead of `requests`, same assertions on the adapter's returned dict).
- Add `huggingface_hub`, `deepl`, and `translators` to `requirements.txt`.

## Capabilities

### New Capabilities
- `provider-client-policy`: a standing, checkable rule for every current and future adapter — use a legitimate, actively maintained client library when one exists for the exact endpoint being called and doing so doesn't cost needed data fidelity; stay on raw HTTP when no such library exists, or when using one would lose data the service depends on, documented per adapter either way.

### Modified Capabilities
- `translate-api`: provider set drops `libretranslate`; `bing`'s provider set entry notes it is now implemented via the `translators` package rather than a custom scrape.

## Impact

- **Affected files**: `adapters/hf_whisper.py`, `adapters/deepl.py`, `adapters/bing_translate.py`, `adapters/dictcc_api.py`, `adapters/dictcc_static.py`, `requirements.txt`; `adapters/libretranslate.py` and its tests **deleted**; `openspec/specs/translate-api/spec.md` (delta, provider set).
- **No impact** on `lookup-cache`, routes, or any response schema besides the provider-set shrink — `ProviderLookupError` remains the error contract adapters raise on failure, whichever transport they use underneath.
- **Coordinates with** `provider-tokens-and-manual-link-fallback` (which must drop its `LIBRETRANSLATE_TOKEN` wiring — update that proposal too, since the provider it was wiring a token for no longer exists) and `translate-multi-candidate` (which must drop its `libretranslate` wrapping task for the same reason). Otherwise independent of `add-elevenlabs-provider`.
