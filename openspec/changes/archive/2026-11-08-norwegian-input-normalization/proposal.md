## Why

Nothing in smia prepares a query before it reaches a provider. Every adapter
matches the caller's raw string exactly — `ordbank` does `WHERE oppslag =
:word`, `kaikki` does `WHERE e.word = :word`, `dictcc_api` sends
`s=<word>` verbatim — so a caller sending the natural Norwegian citation
form of a word gets nothing back:

| Request | Today |
|---|---|
| `{word: "en kalv", lang: "nb"}` → `/inflections` | `candidates: []` |
| `{word: "å komme", lang: "nb"}` → `/inflections` | `candidates: []` |
| `{text: "et hus", from: "nb", to: "en"}` → `/translations` | `candidates: []` |

That citation form is not an odd way to ask. It is how Norwegian dictionaries
print headwords, how a learner writes a noun down (gender is carried by the
article, not the noun), and what hover-translate captures when the user
selects a noun phrase in running text. `adapters/dictcc_api.py` already
knows this — it has `_strip_infinitive_marker` and
`_normalize_dictcc_phrase` for reading dict.cc's *answers* — but that
knowledge never touches an outgoing query, and it lives in one adapter
rather than anywhere the other providers can reach.

## What Changes

- **New shared module `norwegian.py`** — the query-preparation layer the
  service is missing. Its primary entry point returns a *list of query
  variants* in priority order, never a single rewritten string:
  ```
  query_variants("en kalv") -> ["en kalv", "kalv"]
  query_variants("å komme") -> ["å komme", "komme"]
  query_variants("Kalv")    -> ["Kalv", "kalv"]
  query_variants("kalv")    -> ["kalv"]
  ```
- **Every Norwegian provider queries all variants and merges the results**,
  deduplicated, rather than querying a rewritten string. The original is
  always tried, so no change can lose an answer that works today.
- `dictcc_api` crosses its variant list with its existing language-pair list
  — a `lang=nb` lookup for `"en kalv"` makes four requests (`DENO`/`ENNO` ×
  `"en kalv"`/`"kalv"`) instead of two, reusing the per-pair
  failure-tolerance and dedupe already built for
  `dictcc-norwegian-multi-pair`.
- `ordbank`, `kaikki` and `dictcc_static` pay no extra round trip — their
  lookups are local SQL, so the variant list becomes a single `IN (...)`
  predicate rather than repeated queries.
- Case folding is **additive only**, never a replacement. Verified against
  the local data: the lexicons genuinely contain capitalized headwords (47
  in `providers/open-dict/nb.txt`, 132 in wikipron's `nob_latn_broad`, 1,922
  of kaikki's 79,403 entries), so lowercasing a query outright would break
  proper-noun lookups that work today.
- **New `tokenize()`** in the same module, specified here but not yet
  consumed — `ipa-multiword` is its first caller.

## Capabilities

### New Capabilities
- `norwegian-input`: how a caller-supplied Norwegian word or phrase is
  prepared before it reaches a provider — the article/infinitive prefixes
  that are stripped, the rule that stripping produces an *additional*
  variant rather than a replacement, the tokenization rules for splitting a
  phrase, and the requirement that every provider merge and deduplicate
  across variants.

### Modified Capabilities
- `inflect-api`: `ordbank`, `kaikki` and `dictcc_api` SHALL resolve a word
  given in citation form (`en kalv`, `å komme`), not only the bare lemma.
- `translate-api`: same, for `dictcc_api` and `dictcc_static`.
- `tts-api`: same, for `dictcc_api`'s audio lookup.

## Impact

- **New** `norwegian.py` at the repo root, alongside `cache.py`/`registry.py`
  — not under `adapters/`, since it is consumed by several adapters and
  (later) by a route.
- `adapters/dictcc_api.py`: all three adapters cross variants with
  `_LANG_SELF_LOOKUP_PAIRS`/`_PAIRS`. The existing
  `_strip_infinitive_marker`/`_normalize_dictcc_phrase` response-side
  helpers move into `norwegian.py` so there is one definition of "strip the
  å" in the codebase.
- `adapters/dictcc_static.py`, `adapters/ordbank.py`, `adapters/kaikki.py`:
  exact-match predicates become variant-list predicates.
- **No API contract change.** Request and response shapes for
  `/inflections`, `/translations` and `/tts` are byte-identical; this is
  purely "the provider asks the right question before giving up," the same
  spirit as `dictcc-norwegian-multi-pair`.
- **No cache-key change.** Normalization stays below `run_lookup`, so the
  cache key remains `sha256` of the caller's raw input — `"en kalv"` and
  `"kalv"` remain two cache rows that now happen to hold the same payload.
  Deliberate: the caller's actual request stays recoverable from the
  resource id.
- `/ipa` and `/stt` are untouched here. `/ipa`'s wiring belongs to
  `ipa-multiword`, which changes that kind's response contract anyway.
- No stabbur or hover-translate changes — both already just post a word and
  read candidates.
