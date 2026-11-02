## Context

`_LANG_SELF_LOOKUP = {"nb": ("DENO", 2), "en": ("ENNO", 1), "de": ("DEEN", 1)}`
is consumed identically by `DictccApiInflectAdapter.lookup` and
`DictccApiTtsAdapter.lookup` — both resolve exactly one `(lp, dir)` pair,
make one `_get_json` call, and build candidates from it. `_PAIRS` (the
`translations` adapter's from/to map) already proves `DENO`/`ENNO` are both
live, confirmed pairs — this isn't new API surface, just asking a second
already-working pair for the same lookups.

## Goals / Non-Goals

**Goals:**
- A Norwegian word present in either dict.cc pair (NO↔DE or NO↔EN) is found
  by `/inflections` and `/tts`, not just the one currently hardcoded.
- Identical results from both pairs collapse into one candidate/recording,
  not a visible duplicate.
- One pair's transient failure doesn't sink a lookup the other pair would
  have answered successfully.

**Non-Goals:**
- No pair-attribution in the response shape (confirmed: dedupe is enough,
  no "via DE"/"via EN" tagging needed).
- No change to `/translations`' `_PAIRS` usage — that already takes an
  explicit `(from, to)` and has no ambiguity to resolve.
- No change to `en`/`de` self-lookups — only `nb` gets a second pair.

## Decisions

### D1 — `_LANG_SELF_LOOKUP` becomes a list of pairs per language
```python
_LANG_SELF_LOOKUP_PAIRS: dict[str, list[tuple[str, int]]] = {
    "nb": [("DENO", 2), ("ENNO", 1)],
    "en": [("ENNO", 1)],
    "de": [("DEEN", 1)],
}
```
Both adapters loop over `_LANG_SELF_LOOKUP_PAIRS[lang]` instead of resolving
a single pair. `en`/`de` keep single-element lists rather than a separate
code path — one loop body handles both "one pair" and "several pairs"
uniformly, so there's no special-casing of `nb`.

### D2 — Per-pair failure is tolerated; only all-pairs-failed raises
Each pair's `_get_json` call is wrapped individually. A `ProviderLookupError`
from one pair is caught and that pair contributes no candidates (logged at
most, not surfaced); the lookup only raises if *every* pair raised. This
mirrors `cache.py`'s `ProviderLookupError` contract at the single-provider
level: dict.cc-as-a-whole should behave like "it tried, and found what it
could," not "one of its two internal datasets hiccuped, so pretend none of
them answered." Rejected alternative: let any pair's exception propagate
immediately — would turn a transient blip on the *less likely to matter*
pair into a full failure for a lookup the *other* pair would have answered
fine.

### D3 — Dedup by result identity, not fuzzy matching
- **Inflections**: a candidate's `(pos, paradigm)` tuple (paradigm compared
  as a frozen/sorted dict) is the identity — two pairs producing the exact
  same shape collapse to one candidate. Different paradigms (even for the
  same lemma — e.g. one pair's table has a gap the other fills) both survive
  as separate candidates, same as today's "never silently merge, let the
  operator see disagreement" philosophy for every other inflections
  provider.
- **TTS**: `sha256` is already smia's own content-addressed identity
  (`audio_cache.store`) — a candidate dict keyed on `sha256` naturally
  dedupes if both pairs resolve to byte-identical audio. No new dedup logic
  needed here beyond checking "have I already added this `sha256`" before
  appending.

### D4 — Candidates are concatenated in a fixed pair order, not interleaved
`DENO` candidates (today's existing behavior) are built and deduped first,
then `ENNO` candidates are appended — not merged entry-by-entry. Keeps the
change low-risk: anyone depending on "the first candidate is what `nb`
already returned today" (nothing currently does, per grep, but still) sees
no behavior change for a word dict.cc's DE-NO pair already covers; `ENNO`
only ever adds candidates, never reorders or replaces what was already
there.

## Risks / Trade-offs

- **[Trade-off]** Two HTTP calls instead of one for every `nb` inflections/
  tts lookup (cache-miss case only — `lookup-cache` still caches the
  combined result under one key, so this cost is paid once per distinct
  input, not per request). Accepted — dict.cc's mobile-app backend has no
  documented rate limit this service has hit, and correctness (finding words
  the single-pair version missed) outweighs one extra request on a cache
  miss.
- **[Risk]** `_parse_inflection_blocks`' positional segment-parsing logic
  (`inflections_repl`'s `;`-delimited segments, see its own docstring) is
  intricate and pair-specific data could in principle expose an edge case
  the DE-NO pair's data never hit. Mitigation: no parsing logic changes here
  at all — `_parse_inflection_blocks` is called once per pair with that
  pair's own response, identically to how it's called today; any new edge
  case is a `_parse_inflection_blocks` bug independent of this change,
  surfaced by new data rather than caused by new code.

## Migration Plan

- Additive/internal only — no request or response shape changes, no new
  environment variables, no new dependencies. Rollback is reverting
  `adapters/dictcc_api.py`.
