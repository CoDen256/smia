## Context

`smia-service-foundation` and `add-dictcc-providers` implemented every adapter against each provider's raw HTTP surface via `requests`, including providers (Hugging Face, DeepL) that publish an official, actively maintained Python client. That was reasonable while the priority was proving the endpoints end-to-end; now that the provider set is stabilizing and `add-elevenlabs-provider` is about to add a third SDK-backed provider, it's worth converging on "use the vendor's maintained client when one legitimately exists" as policy, not leave it inconsistent.

## Goals / Non-Goals

**Goals:**
- Identify, per existing adapter, whether a legitimate, actively maintained client library exists for the exact endpoint it calls — official-vendor or reputable community, either counts, provided it doesn't cost data fidelity the service needs.
- Swap to that library where one exists and is worth it, with no change to the adapter's `lookup()` contract or the `ProviderLookupError` failure contract.
- Document, for adapters that stay on raw HTTP, why — so a future contributor doesn't "helpfully" reach for google-cloud-translate or azure-cognitiveservices (different products than what these adapters actually call), or swap Google to a wrapper library that silently loses its sense/dictionary structure.

**Non-Goals:**
- Response shapes, caching, and per-provider error semantics for the providers that keep or gain a library are identical before and after. (`/translations`' provider *set* does shrink by one, `libretranslate` — a deliberate scope decision made during this change's exploration, not an accidental side effect.)
- Not re-litigating which providers are configured per kind beyond that one removal — otherwise that's `smia-service-foundation`'s and `add-dictcc-providers`' job, already settled.

## Decisions

### D-L1: Hugging Face → `huggingface_hub`
**Decision**: replace `hf_whisper.py`'s raw `requests.post` against `router.huggingface.co` with `huggingface_hub.InferenceClient.automatic_speech_recognition(...)`.

**Why**: `huggingface_hub` is Hugging Face's own maintained Python package, is the documented way to call Inference, and already handles the base64/raw-bytes request-shape branching this adapter currently hand-rolls.

**Alternatives considered**: staying on raw `requests` — rejected, no reason to hand-maintain what the vendor maintains for free.

### D-L2: DeepL → `deepl` package
**Decision**: replace `deepl.py`'s raw `requests.post` against `api-free.deepl.com` with the official `deepl` package's `Translator.translate_text(...)`.

**Why**: same reasoning as D-L1 — official, maintained, handles the free-vs-pro host selection and auth-key header internally.

### D-L3: Google stays on raw HTTP, deliberately
**Decision**: `google_translate` and `dictcc_api`/`dictcc_static` stay on raw `requests`.

**Why**: Google Cloud Translate's official SDK is for a *paid, documented, different* product (`translate.googleapis.com/translate_a/single` is not what that SDK talks to). A community alternative does exist — `translators` (UlionTse), actively maintained — but it was explicitly rejected for Google after checking what it actually returns: one plain string per call, discarding the `dict[]` part-of-speech/sense structure `google_translate.py` currently parses directly from Google's raw response. `translate-multi-candidate` depends on that structure to tell Norwegian `igjen`'s "again" sense from its "back"/"left" sense. Swapping to `translators` for Google would trade away data fidelity for a library — explored and declined, not defaulted to. dict.cc has no published client at all for either its public site or its mobile-app backend, so no alternative exists there either.

### D-L4: Bing → `translators` package
**Decision**: `bing_translate` swaps to the `translators` package's Bing engine.

**Why**: unlike Google, today's `bing_translate.py` already extracts only one plain translated string — there is no structured data to lose by swapping. It's also a reliability fix: this adapter's own docstring records that Microsoft's undocumented `edge.microsoft.com/translate/auth` endpoint (which the current hand-rolled token exchange depends on) returned 404 when live-tested, i.e. it may already be broken. `translators` is actively maintained (release within the last several months, 2.7k+ GitHub stars) and handles Bing's access path as someone else's maintenance burden instead of this repo's. License is GPL-3.0 — raised and explicitly accepted by the user as a non-issue for this private, non-distributed deployment.

### D-L5: Drop LibreTranslate entirely
**Decision**: remove the `libretranslate` provider from `/translations` altogether — not "stay on raw HTTP," but delete the adapter, its registration, and its spot in the provider set.

**Why**: two independent reasons converged. (1) No legitimate maintained client exists — `libretranslatepy` hasn't been updated since April 2024. (2) The provider itself was already proven unreliable in practice before this exploration even started: `libretranslate.py`'s own docstring records that public community-run mirrors were found down or blocking during implementation, and the official hosted instance (`libretranslate.com`) now requires a paid API key, undermining the entire reason it was in the provider set (a free, simple, self-hostable fallback). Given no good client and a flaky-to-paid provider, the user's call was to stop carrying it rather than keep it on raw HTTP out of inertia.

## Risks / Trade-offs

- **[Risk]** An SDK's error types differ in shape from `requests.RequestException`/`ValueError`, so the `except` clauses mapping failures to `ProviderLookupError` need to change per SDK, not be a mechanical find-replace. → **Mitigation**: existing tests assert on the adapter's returned dict and on `ProviderLookupError` being raised on failure, not on `requests` internals — they should catch any behavioral drift from an incomplete exception mapping.
- **[Risk]** `huggingface_hub`'s `InferenceClient` may not support the exact base64-with-language-parameter request shape `shadow.js`'s original code used (`generate_kwargs.language`). → **Mitigation**: confirmed via research that `automatic_speech_recognition()` accepts an `extra_body` dict of provider-specific parameters — `{"generate_kwargs": {"language": ..., "task": "transcribe"}}` should pass straight through; verify against a live call during implementation since this wasn't confirmed against the actual HF Inference response, only documented client behavior.
- **[Risk]** Swapping Bing to `translators` makes its behavior depend on a third party's maintenance of a GPL-3.0 scraping library, rather than this repo's own code. → **Mitigation**: accepted — license is a non-issue for private use (explicit user decision), and `translators` being actively maintained by a community with 2.7k+ stars is a lower maintenance burden than nursing a hand-rolled edge-auth exchange that's already shown signs of breaking.
- **[Risk]** Dropping `libretranslate` removes a provider other open proposals (`provider-tokens-and-manual-link-fallback`, `translate-multi-candidate`) still reference. → **Mitigation**: both of those proposals are being updated alongside this one to drop their LibreTranslate-specific tasks; sequence this change's archive before (or alongside) theirs so no task references a deleted file.

## Migration Plan

No data migration. Sequencing:
1. Add `huggingface_hub`, `deepl`, and `translators` to `requirements.txt`.
2. Swap `hf_whisper.py`, update its tests to mock the SDK client.
3. Swap `deepl.py`, update its tests to mock the SDK client.
4. Swap `bing_translate.py` to `translators`, update its tests.
5. Delete `adapters/libretranslate.py`, its registration, and its tests; remove it from the `translate-api` provider set (this change's spec delta).
6. Add a short docstring note to `google_translate.py` and `dictcc_api.py`/`dictcc_static.py` recording why no swap applies (D-L3), so this doesn't get re-litigated per-adapter later.

## Open Questions

- Confirm `huggingface_hub`'s `extra_body={"generate_kwargs": {...}}` actually produces the same HF Inference request shape as the current raw-HTTP JSON body, against a live call.
- Confirm `translators`' Bing engine output quality/behavior matches closely enough to not regress `/translations` callers (no structured data was being extracted from Bing before, so this is a quality check, not a shape check).
