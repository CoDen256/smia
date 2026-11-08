## Why

stabbur's note model has a `context_text` field — "surrounding sentence(s)/
paragraph" — and it is the **X field** on both of the deck's text card types:

```
| word       | N: word + table | E: en/de | X: context sentence   |
| expression | N: phrase       | E: en/de | X: context (optional) |
```

For a note promoted from a capture, that text comes from the page the word
was selected on. For a note typed in by hand there is no surrounding text at
all, and nothing in the ecosystem can supply one. smia already answers every
other enrichment question the note editor asks (`/ipa`, `/translations`,
`/inflections`, `/tts`, wired through stabbur's enrichment panel per D118) —
this is the one empty field with no provider behind it.

## What Changes

- **New kind `examples`**: `POST /examples` taking `{text, lang, provider,
  limit?}` and returning `{provider, candidates: [{text, source?, sense?}]}`,
  following the `lookup-cache` contract like every other kind.
- Named `examples`, **not** `context` — `/translations` candidates already
  carry a field called `context` meaning the matched entry's part-of-speech
  and domain tags (`"[zool.]"`, `"noun {m}"`). A kind called `context`
  returning something unrelated next to that field would be a permanent
  source of confusion. `examples` also matches the plural-noun convention of
  `inflections`/`translations`.
- **No translation field.** Candidates are Norwegian text only.
- **At most 3 candidates by default** (optional `limit`, 1–10), which makes
  candidate *ranking* a first-class part of this capability rather than an
  afterthought — the Leipzig corpora return tens of thousands of hits for a
  common word and 3 must be chosen well.
- **Four providers**, split across two fundamentally different lookup
  mechanics:

  ```
  DICTIONARY — "examples filed under this lemma"
    ordbokene   live API, already called by /ipa; hand-written, sense-attached
    kaikki      local jsonb, needs a reimport to retain senses[].examples[]

  CORPUS — "sentences containing any inflected form of this lemma"
    tatoeba     18,898 local sentences, learner-grade
    leipzig     3,000,000 local sentences across three sub-corpora
  ```
- **A new `simple`-configuration full-text index plus ordbank-driven form
  expansion** for the corpus providers. This is the load-bearing technical
  decision and it is not the obvious one — see Impact below.
- `GET /providers` gains the new kind, with record counts for the three local
  providers.

## Capabilities

### New Capabilities
- `examples-api`: the `POST /examples` contract — request and response
  shapes, the no-translation rule, the candidate limit, the four providers
  and what each is good for, how corpus providers resolve inflected forms,
  and the ranking rule that decides which few sentences are returned.

### Modified Capabilities
- `provider-catalog`: `GET /providers` enumerates a sixth kind, and reports
  record counts for `tatoeba`, `leipzig` and `kaikki` on it.

## Impact

### Data, as downloaded and verified

| File | Lines | Used |
|---|---|---|
| `providers/tatoeba/nob_sentences.tsv.bz2` | 18,898 | `id \t lang \t text` |
| `providers/leipzig/nob-no_web_2020_1M.tar.gz` | 1,000,000 | only `*-sentences.txt` |
| `providers/leipzig/nob_news_2013_1M.tar.gz` | 1,000,000 | only `*-sentences.txt` |
| `providers/leipzig/nob_wikipedia_2014_1M.tar.gz` | 1,000,000 | only `*-sentences.txt` |

Each Leipzig archive also contains `-inv_w.txt` (249–270 MB), `-co_s.txt`,
`-co_n.txt`, `-words.txt`, `-sources.txt`, `-inv_so.txt` and an
`-import.sql`. **None of those are imported** — they are Leipzig's own
co-occurrence and inverted-index products, which this change replaces with a
Postgres index. Importing only `-sentences.txt` keeps ~1.9 GB of the 2.2 GB
unpacked footprint out of the database.

### The indexing decision

Measured against a real `postgres:16`, the obvious approach —
`to_tsvector('norwegian', …)` — is **wrong for this use case** in two ways:

```
Postgres 'norwegian' config:
  ✓ kalv / kalven / kalver / kalvene   → all stem to 'kalv'
  ✗ bok → 'bok'  but  bøker → 'bøk'    umlaut plurals DON'T match
    (same for mann/menn, hånd/hender, fot/føtter)
  ✗ 176-entry stopword list includes kom, var, ble, hadde, er
    → no example sentence for være, bli, komme or ha via its preterite
      can EVER be found. These are the most important verbs a learner has.
```

So the change indexes with `to_tsvector('simple', …)` (no stemming, no
stopwords) and does **all** morphology through `ordbank_fullform`, the
official Norwegian inflection table smia already imports. Verified: every
probe passes, including `kom` and `var`, and a near-miss (`kalkun` for a
`kalv` query) correctly does not match.

Form expansion is also the single largest coverage lever, measured on the
real corpora:

| query | bare form | with ordbank forms |
|---|---|---|
| `komme` | 8,983 | **38,130** (4.2×) |
| `kalv` | 32 | **115** (3.6×) |
| `hus` | 1,612 | **3,344** (2.1×) |

### Code

- **New** `adapters/ordbokene_examples.py`, `adapters/kaikki_examples.py`,
  `adapters/tatoeba.py`, `adapters/leipzig.py` — plus the second-adapter-on-
  one-source precedent this follows (`kaikki.py` / `kaikki_ipa.py`,
  `ordbokene.py` for `/ipa`).
- **New** `scripts/import_tatoeba.py`, `scripts/import_leipzig.py`; a
  reimport of `scripts/import_kaikki.py` to retain `senses[].examples[]`
  (currently discarded — `kaikki_entry` keeps only `forms` and `sounds`).
- **New** tables + alembic migration: `corpus_sentence` (shared by both
  corpus providers, with a `corpus` discriminator and a GIN index) and a
  `kaikki_entry.examples` column.
- `registry.py`: `KINDS` gains `"examples"`.
- `app.py`: one `register_lookup_routes(app, "examples", …)` call — the
  generic factory is sufficient, unlike `/ipa`.
- `adapters/__init__.py`: four new imports.
- `ui/`: the manual try-it panel gains the new kind.

### Not in this change

- Downstream, stabbur's `ENRICHABLE_KINDS` tuple and a `context_text`
  section in its enrichment panel. smia is a leaf service (D16) and does not
  wait on it.
- No generative/LLM provider. All four providers return text a human wrote;
  consistent with `ipa-api`'s standing rule that providers look things up
  rather than synthesize them.
- No translation of examples, per the operator's decision — which also means
  Tatoeba's `*_links.tsv` sentence-pair files are not needed at all.
