## Context

Existing machinery this builds on:

- `adapters/ordbokene.py` and `adapters/ordbokene_examples.py` — the live-API
  precedent: `requests.get(..., timeout=…)`, `RequestException` →
  `ProviderLookupError`, registered with no `count=`. Separate modules per kind
  over one source (the `kaikki.py` / `kaikki_ipa.py` precedent).
- `adapters/dictcc_static.py` — the `(from, to)` pair-dispatch pattern and an
  `UnsupportedPairError(ProviderLookupError)` for pairs a provider lacks.
- `cache.ProviderLookupError` — a failure the runner does not cache and does
  not retry on another provider.
- `registry.register(kind, name, adapter)` — registration *is* the config.

What the LEXIN API actually returns (probed 2026-11-12):

```
GET https://editorportal.oslomet.no/api/v1/findwords
    ?searchWord=<w>&lang=bokmål&selectLang=<bokmål|engelsk|…>&page=1&includeEngLang=0
    header  Origin: https://lexin.oslomet.no        (required; Referer alone fails)

{ result: [ [ {id, sub_id, type, text, …}, … ] ],   # flat rows
  resArray, ordbankList, partOfSpeachInfo, lang, tablename, exactMatchFound }
```

`result[0]` is a flat list of rows. Rows of one entry share an `id` but are
**not contiguous** (an entry's `*-lem` can appear after other entries' rows).
`type` is `<prefix>-<field>`:

```
prefix   selectLang=bokmål   selectLang=engelsk
         N-  /  E-           B-
field    lem  headword       (English headword; no Norwegian text in the rows)
         kat  part of speech
         def  definition     (Norwegian for N-/E-, English for B-)
         eks  example        (repeats)
         mor  inflection string, e.g. "å avlyse avlyser avlyste har avlyst"
         utt  pronunciation respelling, e.g. "'a:vly:se"
         sms/idi/kom/grm/…   compounds, idioms, comments, grammar notes (ignored)
```

`N-` vs `E-` was not fully decoded; both appear on one entry and carry the same
fields, so the adapter reads them interchangeably.

## Goals / Non-Goals

**Goals:**
- `provider=lexin` answers `/translations` (`nb→nb`, `nb→en`), `/ipa` and
  `/examples` from one request shape, with existing candidate fields only.
- Never mistake an upstream refusal for "no results".
- Be a polite client: paced, with a timeout, one request per lookup.

**Non-Goals:**
- `/tts`, `/inflect` (see proposal), other target languages, Nynorsk, paging
  beyond `page=1`, the `ordbankList` paradigm data, images (`*-div`).
- Joining the `nb→en` response to Norwegian headwords (see D4).
- Filtering fuzzy matches for `/translations` and `/examples`.

## Decisions

### D1: One shared client, three thin adapters

`adapters/_lexin.py` owns the request, the rate limiter, the `Access denied`
check and the grouping of rows into entries; each kind's module only maps
entries to its candidate shape.

```
 lookup ─▶ _lexin.find(word, select_lang)
              │  rate-limit → GET (Origin hdr, timeout) → check err body
              ▼
           [ Entry{id, prefix, lemma, pos, defs[], examples[], morph, utt[]} ]
              │
   ┌──────────┼──────────────┐
 translate    ipa          examples
```

The leading underscore marks it as not an adapter (nothing registers from it).

### D2: Send `Origin`, treat `err` bodies as failures

Requests carry `Origin: https://lexin.oslomet.no` and a generic User-Agent. The
API signals a refused request as **HTTP 200** `{"err": "...", "error_exist":
true}`. `_lexin.find` raises `ProviderLookupError` when `error_exist` is true or
`result` is missing. Treating that as `[]` would be negative-cached by the
lookup cache and hide a block for the cache lifetime.

### D3: Group by `id`, not by position

Entries are built with a dict keyed on `id`, in first-seen order, because an
entry's rows are interleaved with others'. The headword is the `*-lem` row with
compound markers removed (`ut~gå` → `utgå`; the `~` is a syllable/compound hint
in the source, not part of the word). Empty `text` values are dropped
(`E-def ''` is common).

### D4: `nb→en` uses one call and the English headword

`selectLang=engelsk` returns only `B-` rows: English headword (`B-lem`), part of
speech, definition, examples — keyed by the same `id` as the Norwegian entry but
with no Norwegian text in them. A join with a second `nb→nb` call would recover
which Norwegian sense each English entry belongs to, at double the traffic.

Chosen: **one call, no join.** Each English entry becomes one candidate:

```
nb→en  hånd  →  {"text": "hand", "context": "noun: the end part of an arm"}
                {"text": "hand", "context": "noun: the pointer of a clock or another meter"}
                {"text": "hand", "context": "noun: help"}
                {"text": "hind", "context": "noun: a female deer"}
```

The English definition is the sense label, so the `context` already
disambiguates the three `hand`s. Consequences accepted: the Norwegian sense is
not named, and a Norwegian headword LEXIN lacks an English entry for yields no
candidate (`hund` has none — probed). Entries with an empty headword are skipped.

**Alternative considered:** a second `nb→nb` call joined on `id`. Rejected for
now: double traffic against a rate-limited, undocumented API for a label the
English definition already provides. Revisit if callers need the Norwegian sense.

### D5: Fuzzy matches stay, except for `/ipa`

LEXIN also returns entries that merely *contain* the query, and inflection-aware
hits (`skinner` → `skinne`, `jernbane`, `skøyte`). The operator wants these kept.

- **`/translations` `nb→nb`:** candidate `{"text": <definition>, "context":
  "<headword>, <pos>"}`, one per distinct definition per entry. The headword in
  `context` is what makes a fuzzy hit legible (`skinne, verb` vs `skøyte,
  substantiv`).
- **`/examples`:** `{"text": <example>, "sense": <definition>}`, source order,
  default `limit` 3 like `ordbokene`, all entries included.
- **`/ipa`:** only entries where the headword (marker-stripped, casefolded) or
  one of the whitespace-separated tokens of the `mor` string equals the casefolded
  query contribute. `/ipa` candidates are `{ipa, variety?}` and carry no
  headword, so a pronunciation for `jernbane` returned for the query `skinner`
  would simply be a wrong answer. This is the one place the "keep fuzzy" rule is
  narrowed; it is cheap to widen later.

Duplicates (identical `ipa`, or identical text/sense) are collapsed in
first-seen order.

### D6: Pair table, not code paths, for translations

```
_PAIRS = { ("nb","nb"): "bokmål", ("nb","en"): "engelsk" }   # → selectLang
```

A pair outside the table raises `UnsupportedPairError(ProviderLookupError)`,
exactly as `dictcc_static` does. Adding a language later is one table row.
`/ipa` and `/examples` support `lang == "nb"` only; any other `lang` returns
`{"candidates": []}`.

### D7: Rate limiter is a process-wide minimum interval

A module-level lock and `_last_call` timestamp in `_lexin.py`; before each
request, sleep until `min_interval` has passed since the previous call. Default
**1.0 s**, overridable with `LEXIN_MIN_INTERVAL_SECONDS` (read at call time, so
tests and operators can set `0`). The lookup cache already short-circuits
repeats, so this paces only misses. A multi-worker deployment gets one bucket
per process — acceptable for private research use; not a global guarantee.

### D8: Query preparation mirrors the site's own front end

`searchWord` is lowercased, `, ^|;/"` and parentheses become spaces, and the
result is trimmed — what LEXIN's own search box does before it calls the API.
Beyond that the text is sent unchanged: no `query_variants` fan-out and no
inflection handling (that is `/inflect`'s job, and LEXIN does its own matching).

## Risks / Trade-offs

- **Undocumented API** → it can change or tighten without notice. Mitigated by
  D2 (blocks surface as errors), fixtures captured from real responses, and the
  provider being one registry line to remove.
- **Origin header** is a courtesy gate, not authentication. Sending it is what
  the site's own front end does; use is private research only. The limiter (D7)
  keeps load negligible.
- **`nb→en` is loose** (`hund` → `hand/hunt/hundred`, no `dog`) → returned as-is
  per the operator's "keep fuzzy"; callers see English definitions in `context`.
- **`N-`/`E-` semantics undecoded** → both read interchangeably; if a word turns
  up where they differ materially, it is a fixture and a one-line fix.
- **Per-process limiter** → see D7.

## Open Questions

- Does one entry ever carry several `*-def` rows meaning *different* senses?
  D5 emits one candidate per distinct definition, which is right either way,
  but the real-data check in tasks 6.x should confirm no sense is dropped.
