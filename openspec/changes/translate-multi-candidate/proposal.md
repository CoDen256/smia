## Why

`/translations` is the only lookup endpoint that still returns a single flat `{provider, text, context?}` instead of a `candidates` array — an inconsistency left over from before `/ipa` and `/tts` were redesigned to acknowledge that one provider can legitimately hold more than one valid answer. Translation is exactly this kind of endpoint: Norwegian `igjen` means "again" in one sense and "back"/"left (behind)" in another, and providers like Google and dict.cc actually return this multi-sense structure — today's adapters throw it away, concatenating or picking the first entry and returning one string. The user wants nothing hidden: every sense/candidate a provider actually returns should reach the caller, grouped by meaning, with same-meaning alternatives joined (`back/left`) rather than silently dropped.

## What Changes

- **BREAKING**: `/translations` response becomes `{provider, candidates: [{text, context?}]}`, matching `/ipa`'s and `/tts`'s `candidates` shape. The flat `{provider, text, context?}` shape is removed.
- Grouping rule: when a provider's raw data ties multiple distinct translations to the same sense/context, those translations join into one candidate's `text` via `/` (e.g. `back/left`); translations under different senses/contexts become separate candidates.
- Fix every translation adapter to extract all the senses/candidates its provider actually returns, instead of picking or concatenating to one:
  - `google_translate`: Google's `dict[]` already groups terms by part-of-speech/sense (`dict[].terms[]`) — each `dict[]` entry becomes a candidate (or multiple candidates if Google's structure distinguishes finer sub-senses), `text` built by joining that entry's terms with `/`, `context` carrying the sense label Google provides.
  - `bing_translate`: per `provider-client-libraries`, this adapter moves to the `translators` package, which (like the current hand-rolled call) returns one translation per call with no sense structure — stays one candidate, correct and expected, not a bug.
  - `deepl`: DeepL's `/translate` returns one translation per call; stays one candidate — this is not a shortcoming to fix, it's what DeepL's API actually returns.
  - `dictcc_api`: currently takes `translations[0]` and discards the rest — fixed to return every entry, grouped by `entry_type` (e.g. `[zool.]`), with same-context entries' `term1`/`term2` joined by `/`.
  - `dictcc_static`: currently returns the first matching row — fixed to return every matching row for the lemma pair, grouped the same way.
- `libretranslate` is out of scope here entirely — `provider-client-libraries` drops that provider from `/translations` altogether, so there's no adapter left to fix.
- No endpoint other than `/translations` is affected.

## Capabilities

### New Capabilities
_None._

### Modified Capabilities
- `translate-api`: response shape changes from flat `{provider, text, context?}` to `{provider, candidates: [{text, context?}]}`; the context-field requirement is rewritten per-candidate instead of per-response.

## Impact

- **Affected files**: `openspec/specs/translate-api/spec.md` (delta), `adapters/google_translate.py`, `adapters/bing_translate.py`, `adapters/deepl.py`, `adapters/dictcc_api.py` (`DictccApiTranslateAdapter`), `adapters/dictcc_static.py`, `tests/test_translate_adapters.py`, `tests/test_dictcc_api.py`, `tests/test_dictcc_static.py`.
- **BREAKING for any caller already integrated against the old flat shape** — none exist yet outside this repo (hover-translate's migration to call smia hasn't happened), so there is no live consumer to coordinate with.
- **Coordinates with `provider-client-libraries`**: that change decides *how* `bing_translate`/`google_translate` call their providers and drops `libretranslate`; this change decides the *response shape* every surviving adapter must produce. Sequence `provider-client-libraries` first (or review both together) so this change's Bing/Google tasks aren't written against an adapter implementation that's about to change underneath them. Otherwise independent of `add-elevenlabs-provider` and `provider-tokens-and-manual-link-fallback`.
