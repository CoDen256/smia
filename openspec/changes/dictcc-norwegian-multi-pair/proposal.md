## Why

`dict.cc` has no monolingual Norwegian dictionary — only bilingual pairs
(NO↔DE, NO↔EN, NO↔...). `adapters/dictcc_api.py`'s `_LANG_SELF_LOOKUP`
hardcodes exactly one pair per self-lookup language (`nb` → `DENO` only),
so `/inflections` and `/tts` for a Norwegian word only ever check the
NO↔DE side of dict.cc's data. A word present in dict.cc's NO↔EN dataset but
not NO↔DE returns nothing today — not because dict.cc lacks the word, but
because the adapter never asks the other pair that would have found it.

## What Changes

- `/inflections` and `/tts` with `provider=dictcc_api` and `lang=nb` query
  **both** Norwegian-touching pairs (`DENO` and `ENNO`) instead of just
  `DENO`, merging the resulting candidates into one response.
- Results are deduplicated (same inflection paradigm content, or same audio
  `sha256`) rather than showing the same table/recording twice when both
  pairs happen to resolve to the same entry — no pair-attribution labeling
  is added to candidates, keeping the response shape unchanged.
- If one pair's request fails outright (network/parse error) while the other
  succeeds, the successful pair's candidates are still returned rather than
  the whole lookup failing — only failing both pairs fails the request.
- `en`/`de` self-lookups are unaffected — each still has exactly one
  dict.cc pair relevant to it (`ENNO`/`DEEN` respectively); this change only
  adds a second pair for `nb`, since Norwegian is the one language genuinely
  split across two bilingual datasets this service cares about.

## Capabilities

### Modified Capabilities
- `inflect-api`: the `dictcc_api` provider's coverage requirement changes —
  it now checks two dict.cc language pairs for a Norwegian lookup, not one.
- `tts-api`: same, for `dictcc_api`'s audio lookup.

## Impact

- `smia` (`adapters/dictcc_api.py`): `_LANG_SELF_LOOKUP` (single pair per
  language) becomes a pair-list map; `DictccApiInflectAdapter.lookup` and
  `DictccApiTtsAdapter.lookup` loop over the pairs for `lang=nb`, merge and
  dedupe results, and tolerate one pair failing as long as the other
  succeeds.
- No API contract changes — `POST /inflections` and `POST /tts` request/
  response shapes are identical; this is purely "the provider tries harder
  before giving up," same spirit as `translate-multi-candidate`'s grouping
  work for the translate side of this same adapter.
- No stabbur changes — stabbur already just calls `provider=dictcc_api` and
  gets back whatever candidates smia returns.
