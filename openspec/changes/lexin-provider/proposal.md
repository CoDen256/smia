## Why

LEXIN (lexin.oslomet.no, OsloMet's dictionary for learners of Norwegian) holds,
per Norwegian entry, a plain-language definition, example sentences, a
pronunciation respelling and — for 20-odd languages including English — a
translated entry. It is a different *kind* of source from what smia has:
`ordbokene` is a scholarly dictionary, `dictcc` is a word-pair list, and none of
them gives a simple learner-level Norwegian explanation (`nb→nb`) that a
language-learning card actually wants on its back.

One request to LEXIN's JSON API returns all of it, so a single provider can
serve `/translations`, `/ipa` and `/examples` from the same shape.

## What Changes

- **New `lexin` provider on three kinds**, backed by a live call to
  `editorportal.oslomet.no/api/v1/findwords`:
  - `/translations` — `nb→nb` (LEXIN's plain-Norwegian definition) and `nb→en`
    (LEXIN's English dictionary). One candidate per entry/sense, with the part
    of speech and (for `nb→nb`) the headword in `context`. Any other pair is an
    unsupported-pair failure, as `dictcc_static` does today.
  - `/ipa` — LEXIN's pronunciation notation, surfaced as-is under `ipa`, the
    same documented limitation `ordbokene` already has (it is a stress-marked
    respelling like `'a:vly:se`, not IPA). Only entries whose headword or
    inflected forms equal the query contribute (design D5).
  - `/examples` — the example sentences LEXIN files under an entry, in source
    order, with `sense` set to the entry's definition. No translation.
- **Fuzzy matches are kept, not filtered.** LEXIN's search also returns entries
  that merely contain the query (`skinner` → `jernbane`, `skinne`, `skøyte`).
  For `/translations` and `/examples` they are returned and the headword is
  surfaced in `context` / `sense`, so the caller can tell them apart. (`/ipa`
  is the exception, D5.)
- **Rate limiting.** A process-wide minimum interval between calls to LEXIN
  (default 1 s, env-configurable). The lookup cache already makes repeats free;
  the limiter only paces cold misses.
- **Specs:** `translate-api`, `ipa-api` and `examples-api` each gain a
  requirement for the `lexin` provider.

**Out of scope, deliberately:**
- **`/tts`** — LEXIN's audio is Acapela speech synthesis delivered through
  leseWEB (LEXIN's own help text says so). It is not human, and its host serves
  an incomplete TLS chain. Not wired up.
- **`/inflect`** — LEXIN's paradigm tables are Norsk Ordbank data, which smia
  already serves via `ordbank`. No new provider.
- **Languages other than `nb`/`en`** (Arabic, Somali, Ukrainian, … are all one
  `selectLang` value away) and **Nynorsk**. Easy follow-ups, not part of this.
- **German.** LEXIN has no German dictionary.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `translate-api`: provider set gains `lexin`, with `nb→nb` and `nb→en` pairs.
- `ipa-api`: provider set gains `lexin` (respelling notation, matched entries only).
- `examples-api`: provider set gains `lexin` as a dictionary provider.

## Impact

- **New** `adapters/_lexin.py` (HTTP client, rate limiter, row grouping) and
  `adapters/lexin_translate.py`, `adapters/lexin_ipa.py`,
  `adapters/lexin_examples.py`; tests with trimmed real-response fixtures.
- **Edited** `adapters/__init__.py` (three imports).
- **No schema, migration, import script or data files.** No `count=`: it is a
  live API, like `ordbokene`, so `/providers` lists it with no record count.
- **No API shape change**: every candidate uses fields the kind already has.
- **Network dependency.** The API is undocumented and requires an
  `Origin: https://lexin.oslomet.no` header; without it, it answers HTTP 200
  with `{"err":"Access denied"}`. That body must be a provider failure, never a
  cacheable empty result.
- Hard boundaries (CLAUDE.md): smia stays a leaf service; nothing is stored
  beyond the lookup cache; the response records `provider: "lexin"`; the
  provider is declarative registry config.
- Private research use only.
