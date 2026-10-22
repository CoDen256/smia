## Context

`/translations` was the one endpoint left with a flat single-answer response after `/ipa` and `/tts` were redesigned (in `smia-service-foundation`) to return `candidates[]` for cases where one provider holds more than one legitimate answer. Inspecting the actual adapters shows this isn't hypothetical: Google's scraped endpoint already returns a `dict[]` structure grouping translations by part-of-speech/sense, and dict.cc's `translations[]` array already holds multiple entries with per-entry `entry_type` tags — both adapters currently throw that structure away (`google_translate.py` concatenates all `dict[]` terms into one blob string; `dictcc_api.py`'s `DictccApiTranslateAdapter` takes `translations[0]` and ignores the rest).

## Goals / Non-Goals

**Goals:**
- `/translations` returns everything a provider's raw response actually distinguishes — no sense/candidate silently dropped.
- Candidates grouped by sense/context; same-sense alternatives joined with `/` rather than appearing as separate candidates.
- Each adapter fixed to match what its provider's data actually supports — not forced into returning multiple candidates when the provider genuinely only returns one.

**Non-Goals:**
- Normalizing context label vocabulary across providers (Google's POS labels, dict.cc's domain tags, and a future provider's labels can all look different — `context` is provider-defined free text, not a controlled vocabulary).
- Bing: `provider-client-libraries` moves this adapter to the `translators` package, which returns one plain string per call — no multi-sense structure to recover here, by design (see that change's D-L4). One candidate is correct and final, not a placeholder pending future work.
- `libretranslate`: not addressed here at all — `provider-client-libraries` removes the provider entirely, so there's no adapter left for this change to touch.

## Decisions

### D-TM1: Grouping key is the provider's own sense/context grouping, not inferred
**Decision**: each adapter groups its provider's raw translations using whatever grouping that provider's data already encodes (Google: `dict[]` entry boundaries; dict.cc: `entry_type` per `translations[]` row), rather than smia trying to infer "same meaning" across translations itself.

**Why**: inferring sense-equivalence across arbitrary translated strings is a hard, unreliable problem (and out of scope for an API layer); every provider in this set already encodes its own grouping, so using it directly is both correct and simple.

### D-TM2: `/` join for same-context alternatives
**Decision**: within one context group, join multiple translation strings with `/` (e.g. `back/left`) into that one candidate's `text`.

**Why**: explicit user direction — "if it is the same context, it should just join translations via /."

### D-TM3: No candidate is manufactured where the provider has none
**Decision**: DeepL's `/translate` and Bing-via-`translators` return exactly one string with no sense structure — their adapters return exactly one candidate, unchanged from today's single-answer behavior (just wrapped in `candidates: [...]` instead of returned flat).

**Why**: "fix the adapters to return multiple candidates" means "stop discarding structure that exists," not "force structure that doesn't." Explicit user position: "even if the format is not well parsable still i want to see it in the translations output and not hide anything" — the fix is about not hiding what's there, not inventing what isn't.

## Risks / Trade-offs

- **[Risk]** Google's exact `dict[]` sub-structure (does one entry ever need splitting into more than one candidate itself, e.g. distinguishing near-synonyms within one POS group?) needs re-checking against a live response, not assumed from the old single-string-concatenation code. → **Mitigation**: verify against a live or recorded Google response during implementation (same approach as `dictcc_api`'s live-confirmed parsing), not guessed from the old code's behavior.
- **[Risk]** Changing `/translations`' response shape again (third time across these changes) could look like churn. → **Mitigation**: this is the last planned shape change for this endpoint — it completes the same `candidates[]` pattern `/ipa`/`/tts` already settled into, rather than introducing a new pattern.

## Migration Plan

No data migration (stateless lookups, cache entries keyed by input+provider will simply be recomputed under the new shape on next call — old cached flat-shape entries age out naturally, not specially migrated). Sequencing:
1. Update `translate-api` spec (this change's delta, synced on archive).
2. Fix `google_translate.py` and `dictcc_api.py`/`dictcc_static.py` (the adapters with real multi-candidate structure to recover).
3. Wrap `deepl.py` and `bing_translate.py` (post-`translators`-swap) in single-candidate arrays.
4. Update `routes` wiring if `run_lookup`/`cache.py` assume a flat shape anywhere for this kind specifically (check; likely kind-agnostic already since `/ipa`/`/tts` proved the `candidates[]` pattern works through the same generic runner).
5. Update all translate-adapter tests.

## Open Questions

- Does Google's `dict[]` ever need sub-splitting within one POS group, or is one candidate per `dict[]` entry always correct?
