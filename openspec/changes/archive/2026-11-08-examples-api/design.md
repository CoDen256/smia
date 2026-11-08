## Context

The four providers answer two genuinely different questions, and that split
drives most of this design:

```
 DICTIONARY half                        CORPUS half
 "which examples are filed             "which sentences in a 3M-sentence
  under this lemma?"                     corpus contain this lemma?"

 direct key lookup                      inverted index + form expansion
 0 or a handful of results              up to tens of thousands of results
 hand-written, pedagogically chosen     naturally occurring, unfiltered
 sense-attached                         no sense information
 ranking irrelevant                     ranking is the whole problem
```

Everything below was measured against the real data, not assumed.

### ordbokene (live API)

Probed live. `GET ord.uib.no/bm/article/{id}.json` →
`body.definitions[].elements[]` contains `{"type_": "example", "quote":
{...}}` nodes, nested recursively inside `definition` elements. `quote.content`
carries `$` placeholders filled from `quote.items[].text`. Real output for
`kalv`:

```
"slakte en $"  + usage "kalv"        → "slakte en kalv"
"både kua og kalven står i fjøset"   → verbatim, no placeholder
"ha kalv til middag"
"han er en $ til å sparke fotball"   → "han er en kalv til å sparke fotball"
```

Five examples across four senses, each attached to the sense it illustrates.
`adapters/ordbokene.py` already calls this API for `/ipa`, so the search →
article-id → article-json flow is proven code.

### kaikki (local, needs reimport)

Measured on `providers/kaikii/nb.jsonl`: **2,935 of 79,403** entries (3.7%)
have `senses[].examples[]`. Quality is uneven — many are morphology
fragments rather than sentences:

```
"fable" → {"text": "fable om suksess", "translation": "dream about success"}
"a-"    → {"text": "a- + politisk (\"political\") → apolitisk"}   ← not a sentence
```

`scripts/import_kaikki.py` currently keeps only `forms` and `sounds`, so the
examples are on disk but not in the database.

### tatoeba (local)

18,898 sentences, `id \t lang \t text`. Mean **6.6** words, median 6 —
genuinely learner-grade. But coverage collapses fast: `kalv` family → 4 hits,
`drøvtygger` → 0, `hvalross` → 0, `vindmølle` → 0.

### leipzig (local, three sub-corpora)

| corpus | lines | mean words | median | 5–15 word band | multi-sentence lines |
|---|---|---|---|---|---|
| `nob-no_web_2020` | 1,000,000 | 16.2 | 15 | 51.1% | 0.7% |
| `nob_news_2013` | 1,000,000 | 17.4 | 16 | 45.2% | 1.3% |
| `nob_wikipedia_2014` | 1,000,000 | 17.6 | 16 | 44.8% | 1.7% |

Coverage is excellent — even `drøvtygger` (25 hits) and `hvalross` (11) land.
But **fewer than half** of all sentences are in a card-usable length band, and
the raw hits are frequently unusable: news sentences begin with embedded
timestamps (`"01 mai 2013 10:38 Lettvin blir tungt for mange…"`, 30 words),
wikipedia lines sometimes contain two sentences joined.

## Goals / Non-Goals

**Goals:**
- An `examples` kind that fills stabbur's `context_text` / X-field gap.
- Two or three *good* sentences, not a dump — ranking is part of the contract.
- A corpus lookup that finds inflected occurrences, including the irregular
  forms a Norwegian learner most needs.
- Reuse what the service already has: the `ordbokene` API client pattern, the
  `ordbank_fullform` inflection table, the generic route factory, the
  `lookup-cache` runner.

**Non-Goals:**
- No translations on candidates (operator decision). Tatoeba's sentence-link
  files are therefore not imported.
- No generative provider. Every candidate is text a human wrote.
- No sense disambiguation for corpus providers. A corpus hit carries no sense
  information and none is inferred.
- No cross-provider merging. One provider per request, as always.
- No import of Leipzig's own `inv_w`/`co_s`/`co_n`/`words`/`sources`
  products.
- No `/examples` support for languages other than `nb`. The data is
  Norwegian; `lang` is validated, not generalised.

## Decisions

### D1 — The kind is `examples`, and candidates carry no translation

```jsonc
POST /examples  {"text": "kalv", "lang": "nb", "provider": "leipzig", "limit": 3}

{
  "provider": "leipzig",
  "candidates": [
    {"text": "Ei ku og noen kalver.",                      "source": "web_2020"},
    {"text": "Kalven på bildet er to timer gammel.",        "source": "news_2013"},
    {"text": "Hun vil forsvare kalven med alle midler.",    "source": "wikipedia_2014"}
  ]
}
```

`source` names the sub-source the sentence came from, so provenance survives
(the house rule). `sense` is additionally present for dictionary providers
that attach examples to a definition. Neither is required of a provider that
has nothing meaningful to put there — the same "omit rather than fake it"
convention `variety` and `count` already follow.

Named `examples` rather than `context` because `/translations` candidates
already have a `context` field with an unrelated meaning (pos/domain tags).

### D2 — `leipzig` is ONE provider over three corpora, tagged per candidate

Follows the `nst` precedent exactly: `nst` is one provider whose data spans
five dialect areas, surfaced as one candidate per `variety` rather than as
five provider names. Here, one `leipzig` provider spans three corpora,
surfaced as one `source` per candidate.

Rejected — three providers (`leipzig_web`, `leipzig_news`,
`leipzig_wikipedia`): it would push a choice onto the caller that the caller
has no basis to make, and the ranking rule (D5) is better at picking across
registers than a human guessing which corpus has a good sentence for
`drøvtygger`. One provider also keeps `GET /providers` honest about what is
really one dataset family.

Consequence: a single `leipzig` lookup queries all three corpora. Since they
live in one table with a `corpus` discriminator (D4), that is one SQL
statement, not three.

### D3 — `simple` full-text config, with all morphology via `ordbank_fullform`

The load-bearing decision. Measured on a real `postgres:16`:

```
to_tsvector('norwegian', …)              verdict
─────────────────────────────────────    ──────────────────────────────────
kalv/kalven/kalver/kalvene → 'kalv'      ✓ regular noun morphology works
hus/huset/husene           → 'hus'       ✓
kommer                     → 'komm'      ✓ matches a 'komme' query
bok → 'bok' BUT bøker → 'bøk'            ✗ umlaut plural does not match
  (mann/menn, hånd/hender, fot/føtter alike)
'norwegian'.stop has 176 entries         ✗ FATAL: kom, var, ble, hadde, er
  including the core preterites               are dropped from the index
                                              entirely — no sentence for
                                              være/bli/komme/ha via its
                                              preterite can ever be found
```

So: index `to_tsvector('simple', text)` with a GIN index — no stemming, no
stopword list — and build the query as an OR of every surface form of the
queried lemma, taken from `ordbank_fullform`:

```sql
to_tsquery('simple', 'bok | boka | boken | bøker | bøkene')
```

Verified against the same Postgres: `bøker`, `menn`, `hender`, `føtter`, `kom`
and `var` all match through their expanded query; `kalkun` correctly does not
match a `kalv` query. The one approach that handles both the irregular
morphology and the stopwords.

The expansion query is small — the word's `lemma_id`s from
`ordbank_fullform WHERE oppslag = :word`, then every `oppslag` for those
`lemma_id`s. That is the same table `adapters/ordbank.py` already walks.

Trade-off accepted: a `simple` index is larger than a stemmed one (no lexeme
collapse) and the query is longer. In exchange the index is also
language-neutral and exactly predictable — a form matches iff it is literally
present, which makes wrong results debuggable instead of mysterious.

Fallback when a word is not in ordbank at all (proper nouns, loanwords,
compounds Ordbank does not list): query the surface form alone. A degraded
but correct result, not an error.

### D4 — One `corpus_sentence` table shared by both corpus providers

```
corpus_sentence
  id          serial primary key
  corpus      text not null     -- 'tatoeba' | 'web_2020' | 'news_2013'
                                --            | 'wikipedia_2014'
  ext_id      text              -- the source's own id, for traceability
  text        text not null
  word_count  int not null      -- precomputed; the ranking rule's main input
  tsv         tsvector          -- to_tsvector('simple', text), GIN-indexed
```

One table, not one per provider: both providers ask the identical question
("sentences containing these forms") and differ only in which `corpus` values
they filter to. `tatoeba` filters `corpus = 'tatoeba'`; `leipzig` filters the
other three. A future corpus is a new `corpus` value and an import script,
with no schema change — the same "declarative config, not code paths"
boundary the provider registry already holds.

`word_count` is precomputed at import rather than derived per query, because
it is the dominant ranking input and recomputing it over tens of thousands of
candidate rows per request would be the slowest part of the lookup.

Row count: 3,018,898. Comfortably within what a single Postgres instance
indexes and queries without partitioning.

### D5 — Ranking is specified, because the limit makes it unavoidable

A `komme` query matches 38,130 Leipzig rows and returns 3. Which 3 is the
single thing that determines whether this capability is useful. Validated
against the real corpora — unranked versus ranked, same query:

```
UNRANKED (corpus order), "kalv" in news_2013:
  [19w] Ælvespeilet i Porsgrunn har adoptert disse to kalvene som ble født…
  [29w] Anders Somby jr. har ikke tenkt så mye over hvor store tapene kan…
RANKED, same query, same corpus:
  [ 7w] Kalven på bildet er to timer gammel.
  [ 7w] Nå har elgkua fått en ny kalv.
```

The rule, in descending weight:

1. **Length**, peaking around 8 words and usable in 5–15. This is the
   strongest signal by far — it alone separates the two blocks above.
2. **Looks like a complete sentence**: starts with a capital, ends in
   `.`/`!`/`?`.
3. **Penalise capitalised tokens after the first** — a proxy for
   news-specific named entities, which make a sentence unusable as a generic
   example.
4. **Penalise digits**, which is what strips the embedded-timestamp news
   sentences.
5. **Reject outright**: contains a URL; contains an internal sentence
   boundary (`[.!?]` followed by whitespace and a capital — the 0.7–1.7%
   multi-sentence lines, concentrated in wikipedia).

**Tie-breaking must be explicitly randomised, and this is not a theoretical
concern.** The corpora are roughly alphabetically ordered (news_2013:
only 18.7% of adjacent pairs out of order), so breaking score ties by row id
produced, in direct observation, top-3 sets where every sentence began with
the letter "A" — `"Aj aj…"`, `"Akkurat da…"`, `"Alle beboere…"`, `"Alle hennes…"`,
`"Anders kommer…"`. Ties are therefore broken on a hash of
`(sentence_id, query)`: deterministic, so the cached payload is stable and
reproducible, but with no alphabetical bias.

Ranking applies only to the corpus providers. Dictionary providers return
their handful of examples in source order — they were chosen by a lexicographer
and reordering them by sentence length would be worse, not better.

### D6 — `limit` defaults to 3 and is part of the cache key

`limit` is an optional request field, default 3, clamped to 1–10. It travels
in the input dict, so it participates in `sha256(input)` — a `limit=3` and a
`limit=10` request for the same word are distinct cache resources holding
different payloads. Correct rather than merely convenient: the payload really
does differ, and the alternative (cache a wide result, truncate on read)
would make `GET /examples/{id}` return something different from what the
`POST` returned.

### D7 — ordbokene reuses the existing `/ipa` client flow, and resolves `$` placeholders

`adapters/ordbokene_examples.py` performs the same two-step call
`adapters/ordbokene.py` already does (`/api/articles?w=…` → `/{dict}/article/
{id}.json`), then walks `body.definitions[]` **recursively** — `example`
nodes are nested inside `definition` elements, which can themselves nest.

Placeholder resolution: `quote.content`'s `$` markers are substituted in
order from `quote.items[].text`. A quote with no `$` is used verbatim. If the
placeholder and item counts disagree, the example is skipped rather than
emitted with a literal `$` in it.

`sense` is populated from the enclosing definition's `explanation.content`
when present, giving the operator the one thing no corpus provider can offer:
which meaning this example illustrates.

Live call per lookup, cached afterwards by the `lookup-cache` layer. A future
one-shot crawl into a local table is possible but deliberately not done here —
it would need ~150k article fetches and the API is fast enough per word.

### D8 — kaikki needs a reimport, and filters non-sentence examples

`scripts/import_kaikki.py` gains `senses[].examples[]`, stored as a new
`kaikki_entry.examples` jsonb column (not a separate table — same reasoning
as the existing `forms`/`sounds` columns, per `KaikkiEntry`'s own docstring).

Because 2,935 entries' examples include morphology fragments (`"a- + politisk
→ apolitisk"`), the adapter drops any example whose text contains `→`, `+`
between spaces, or no whitespace at all. Filtering at query time, not import
time, unlike the `imperative`/`passive` form filter — the raw examples may be
useful to a later reader, and the heuristic is likely to need tuning.

kaikki's examples sometimes carry a `translation`/`english` key. It is
**ignored**, per the no-translation decision.

### D9 — The generic route factory is sufficient

Unlike `/ipa` (which needs two-stage phrase-then-split logic) and `/stt`
(multipart body), `/examples` is an ordinary single-call lookup. It registers
through `routes/generic.py`'s `register_lookup_routes` with an
`_extract_examples_input` that validates `text`/`lang` and clamps `limit`. No
new route module.

## Risks / Trade-offs

- **[Risk] The ranking heuristic is tuned on three words** (`kalv`, `bok`,
  `komme`) across three corpora. It may behave worse on word classes not
  probed — adjectives, adverbs, function words. → Mitigated by making the
  rule's components individually specified and testable, so each signal can
  be adjusted without redesigning the capability. The verification tasks
  include a broader sweep before the weights are considered settled.

- **[Risk] A `simple` index is larger than a stemmed one** across 3,018,898
  rows, and the GIN build is the slow part of the import. → Accepted; it is
  the only option that handles stopwords and umlaut plurals (D3). The index
  is built once, offline, by the import script.

- **[Risk] Corpus examples are domain-skewed.** The `kalv` hits are almost
  entirely animal husbandry; news hits skew to politics and sport. → Accepted
  and partly mitigated by D2's three-corpus blend: web, news and encyclopedia
  registers compete within one ranked list, so a word with a bad news profile
  can still be answered from the web corpus.

- **[Risk] A corpus sentence may be unsuitable** — crude, violent, or
  otherwise not something to put on a flashcard. The `kalv` sample already
  surfaced `"Bare få dager gamle blir kalvene sparket, dratt i ørene og
  løftet etter halen"`. → Not mitigated by this design, and deliberately
  flagged rather than papered over: the candidates are a suggestion list an
  operator picks from in stabbur's panel, exactly like every other kind's
  candidates, and nothing auto-fills a note. A content filter is possible
  later but would be guesswork to specify now.

- **[Risk] Three Leipzig corpora predate 2021** (web 2020, news 2013, wiki
  2014). → Irrelevant for this use: example sentences for vocabulary learning
  do not stale.

- **[Trade-off] ordbokene is a live call** and the only provider that can
  fail for network reasons. → Accepted; it is already the case for `/ipa`'s
  `ordbokene`, the failure is a normal `ProviderLookupError`, and three local
  providers are available as alternatives.

- **[Risk] Leipzig licence terms are per-corpus** and some Leipzig corpora
  are non-commercial-only. → To be read off the download pages and recorded
  in `providers/sources` during implementation. Does not affect personal use,
  but should be written down rather than assumed.

## Migration Plan

New kind, new tables, new adapters — nothing existing changes shape. The one
migration-visible item is the `kaikki_entry.examples` column plus a kaikki
reimport; the existing `kaikki` providers for `/inflections` and `/ipa` read
`forms`/`sounds` and are unaffected by the added column.

Order:
1. alembic migration: `corpus_sentence` + `kaikki_entry.examples`.
2. Import scripts; build the GIN index after bulk insert, not before.
3. Adapters + registry + route.
4. `providers/sources`: record the three Leipzig corpus URLs, the Tatoeba
   export URL, and each one's licence.

Rollback: drop the new tables and the `examples` kind registration. No other
kind is touched, so `/inflections`, `/ipa`, `/tts`, `/translations` and `/stt`
cannot regress.

Independent of `ipa-multiword`; shares no code with it. Does **not** depend on
`norwegian-input-normalization`, though a later follow-up could let
`/examples` accept `"en kalv"` through the same `query_variants` facility.

## Open Questions

- Should a corpus candidate report *which* inflected form matched (e.g.
  `matched: "kalvene"`)? Useful for an operator judging relevance; costs a
  little query complexity. Left out of the initial contract.
- Is the ordbokene `sense` string worth surfacing when the other three
  providers can never populate it? Specified as optional, so it can be
  dropped without a contract change if the panel does not use it.
- Should `/examples` accept a phrase and fall back to a per-word search the
  way `/ipa` will? A corpus hit for an exact multi-word phrase is plausible
  (`"av og til"`), but a per-word split makes no sense for an example
  sentence. Deferred until there is a real expression-note use case.
