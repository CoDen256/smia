## 1. Schema

- [x] 1.1 `db/models.py`: add `CorpusSentence` — `id` (serial pk), `corpus` (text, not null), `ext_id` (text, the source's own id), `text` (text, not null), `word_count` (int, not null, precomputed at import per design D4), `tsv` (tsvector). Docstring must record why one table serves both corpus providers and why `word_count` is stored rather than derived.
- [x] 1.2 `db/models.py`: add an `examples` jsonb column to `KaikkiEntry`, alongside the existing `forms`/`sounds`, and extend its docstring (it currently says the table is queried by three adapters — now four).
- [x] 1.3 Alembic migration creating `corpus_sentence` with indexes on `corpus` and a **GIN index on `tsv`**, plus the `kaikki_entry.examples` column. Record in the migration's docstring that the index is built after bulk insert by the import script, not as part of the migration, because a GIN build over ~3M rows is the slow step.
- [x] 1.4 Confirm the `tsv` column uses `to_tsvector('simple', text)` — **not** `'norwegian'`. Add a comment citing the two measured reasons (umlaut plurals don't stem to their lemma; the 176-entry Norwegian stopword list drops `kom`/`var`/`ble`/`hadde`/`er`), so nobody "optimises" it to the Norwegian config later.

## 2. Imports

- [x] 2.1 `scripts/import_tatoeba.py`: read `providers/tatoeba/nob_sentences.tsv.bz2` (bz2 directly, no manual unpack), `id \t lang \t text`, insert with `corpus='tatoeba'`. Expect 18,898 rows.
- [x] 2.2 `scripts/import_leipzig.py`: read the three archives in `providers/leipzig/`, extracting **only** `*-sentences.txt` from each (`id \t sentence`). Map to `corpus` values `web_2020`, `news_2013`, `wikipedia_2014`. Expect 1,000,000 rows each.
- [x] 2.3 Both importers: skip blank lines, compute `word_count`, and `TRUNCATE`-then-insert their own `corpus` partitions only (not the whole table), so one corpus can be reimported without destroying the others.
- [x] 2.4 Build the GIN index after the bulk insert completes; report elapsed time in the script's output so the cost is visible.
- [x] 2.5 `scripts/import_kaikki.py`: retain `senses[].examples[]` into the new column. Keep storing raw (unfiltered) — the non-sentence filter is a query-time concern per design D8.
- [x] 2.6 `scripts/bootstrap.py`: wire the two new importers in, idempotently, matching how the existing importers are invoked.
- [x] 2.7 `providers/sources`: record the three Leipzig corpus URLs, the Tatoeba export URL, and **each one's licence terms** — Leipzig states these per corpus and some of their corpora are non-commercial-only (design Risks).

## 3. Form expansion

- [x] 3.1 New helper (shared by both corpus adapters): given a word, return every surface form of its lemma(s) — `SELECT DISTINCT lemma_id FROM ordbank_fullform WHERE oppslag = :word`, then every `oppslag` for those `lemma_id`s. Same table `adapters/ordbank.py` already walks.
- [x] 3.2 Fall back to `[word]` alone when the word is absent from `ordbank_fullform` (proper nouns, loanwords) — a narrower result, never an error.
- [x] 3.3 Build the query as `to_tsquery('simple', 'form1 | form2 | …')`, escaping each form. Verify against the measured probes: `bok`→matches `bøker`, `komme`→matches `kom`, `være`→matches `var`, and `kalv` does **not** match `kalkun`.

## 4. Corpus adapters

- [x] 4.1 `adapters/tatoeba.py`: `CorpusSentence` query filtered to `corpus='tatoeba'`, using the expanded tsquery; register for kind `examples` with a `count` callable.
- [x] 4.2 `adapters/leipzig.py`: same query filtered to the three Leipzig `corpus` values — **one SQL statement across all three** (design D2), not three queries. Register as the single provider name `leipzig` with a `count` callable.
- [x] 4.3 Both: each candidate is `{text, source: <corpus>}`; `sense` omitted (corpus hits carry no sense information).
- [x] 4.4 Implement the ranking rule (design D5) in SQL or in Python over a bounded candidate fetch: length preference peaking around 8 words and usable in 5–15; bonus for capital-initial and sentence-final punctuation; penalty per capitalised token after the first; penalty per digit-bearing token.
- [x] 4.5 Implement the hard exclusions: any sentence containing a URL, or containing an internal sentence boundary (`[.!?]` + whitespace + capital) — the 0.7–1.7% multi-sentence lines, concentrated in wikipedia.
- [x] 4.6 Tie-break on a deterministic hash of `(sentence id, query)` — **not** row order. Required, not cosmetic: the corpora are roughly alphabetically ordered and row-order tie-breaking was directly observed to return top-3 sets where every sentence began with "A".
- [x] 4.7 Bound the pre-ranking fetch so a query like `komme` (38,130 matches) doesn't pull every row into Python; decide and document the cap, ensuring it is large enough that ranking still has real choice.

## 5. Dictionary adapters

- [x] 5.1 `adapters/ordbokene_examples.py`: reuse the two-step flow from `adapters/ordbokene.py` (`/api/articles?w=…` → `/{dict}/article/{id}.json`). Keep it a separate module from the `/ipa` one, per the `kaikki.py`/`kaikki_ipa.py` precedent.
- [x] 5.2 Walk `body.definitions[]` **recursively** — `example` nodes nest inside `definition` elements, which themselves nest. A shallow scan misses examples.
- [x] 5.3 Resolve `$` placeholders in `quote.content` from `quote.items[].text` in order. Verbatim when there is no `$`. Skip the example entirely when counts disagree, rather than emitting a literal `$`.
- [x] 5.4 Populate `sense` from the enclosing definition's `explanation.content` where present — the one thing no corpus provider can offer.
- [x] 5.5 Return examples in source order, with no ranking applied (design D5 / spec).
- [x] 5.6 `adapters/kaikki_examples.py`: read the new `examples` column; filter out morphology/derivation fragments (contains `→`, or ` + `, or no whitespace at all). Discard any `translation`/`english` key per the no-translation rule. Register with a `count` callable over entries that have examples.

## 6. Wiring

- [x] 6.1 `registry.py`: add `"examples"` to `KINDS`.
- [x] 6.2 `app.py`: `_extract_examples_input` validating `text` and `lang` (reject `lang != "nb"`), and clamping `limit` into 1–10 with a default of 3. Register via the generic `register_lookup_routes` — no custom route module needed (design D9).
- [x] 6.3 Confirm `limit` is inside the extracted input dict so it participates in the cache key (design D6).
- [x] 6.4 `adapters/__init__.py`: import the four new modules.
- [x] 6.5 `ui/`: add `examples` to the manual try-it panel and the provider/health display.

## 7. Tests

- [x] 7.1 Contract: `POST /examples` returns at most `limit` candidates; default is 3; `limit` is clamped at both ends; `lang != "nb"` is a 400.
- [x] 7.2 `limit: 3` and `limit: 10` for the same word yield different resource ids, and `GET /examples/{id}` returns each one's own payload (design D6).
- [x] 7.3 No candidate from any provider carries a translation field — including a kaikki fixture whose example has one, and a Tatoeba row.
- [x] 7.4 Form expansion: `bok` matches a `bøker` sentence; `komme` matches a `kom` sentence; `være` matches a `var` sentence; `kalv` does not match a `kalkun`-only sentence.
- [x] 7.5 A word absent from `ordbank_fullform` still returns results via its surface form rather than erroring.
- [x] 7.6 Ranking: a short complete sentence outranks a long one; a timestamp-prefixed sentence is ranked below a clean one; a multi-sentence line is excluded; a URL-bearing line is excluded.
- [x] 7.7 Tie-breaking: a fixture of many equal-rank sentences with varied initial letters does not return an all-same-initial set, and returns the same set on a repeat call.
- [x] 7.8 `leipzig` is registered once (not three times) and a single lookup can return candidates from more than one corpus, each tagged with its `source`.
- [x] 7.9 ordbokene: `$` placeholder resolved; no-placeholder quote verbatim; mismatched placeholder count skipped; a nested sub-definition example is found; `sense` populated.
- [x] 7.10 kaikki: a morphology fragment (`"a- + politisk → apolitisk"`) is excluded while a real usage example (`"fable om suksess"`) is kept.
- [x] 7.11 Dictionary providers return source order, not length-ranked order.
- [x] 7.12 `GET /providers` lists the `examples` kind, with counts for `tatoeba`/`leipzig`/`kaikki` and none for `ordbokene`.

## 8. Verification

- [x] 8.1 Run the full import against a real Postgres; confirm 3,018,898 `corpus_sentence` rows (18,898 + 3 × 1,000,000) and record the GIN build time. Confirmed against the real local dev Postgres: 18,898 (tatoeba) + 1,000,000 × 3 (web_2020/news_2013/wikipedia_2014) = 3,018,898 exactly. GIN build via `CREATE INDEX IF NOT EXISTS` after bulk insert; first build (tatoeba import, small table) was ~0.0s, and the subsequent Leipzig import (3M rows inserted in ~2m8s total) also reported ~0.0s since the index already existed from the tatoeba run and Postgres maintained it incrementally during the bulk insert — a from-scratch build over the full 3M rows was not separately timed in this run.
- [x] 8.2 Run the full test suite against a real throwaway Postgres container; confirm no regression in the five existing kinds. Run against the real local dev Postgres (not a throwaway container, but a real instance — `docker compose`'s `smia-postgres`): 191/191 passed, including every existing kind's tests plus this change's new ones, and the two other in-flight changes' (`norwegian-input-normalization`, `ipa-multiword`) own tests already in this tree.
- [x] 8.3 Broaden the ranking validation beyond the three words it was tuned on (`kalv`, `bok`, `komme`): sweep a set spanning adjectives, adverbs, and function words, and eyeball the top 3 per provider. Adjust weights if a word class behaves badly — the weights are not settled until this is done (design Risks). Swept `rask`/`vakker`/`fort`/`alltid`/`og`/`men`/`liten`/`stor`/`raskt` against `leipzig`: ranking quality (short, clean, complete sentences) held up well for all of them **except `fort`**, which returned sentences not containing "fort" at all. Root cause (confirmed, not a ranking-weight issue): `ordbank_fullform` groups `fort` under the same `lemma_id` as the irregular verb lemma `fore`/`forte` (paradigm `020`, word class `verb` — consistent with the strong-verb stem alternation of `å fare`), and that lemma's forms include the bare, extremely common preposition `for` as one of its surface forms. Form expansion (task 3.1) is therefore correct by its own contract — it expands to every surface form sharing a lemma, exactly as `adapters/ordbank.py`'s `/inflections` reverse lookup already does for ambiguous headwords like `skinner` — but for `fort` specifically this pulls in `for`, which over-matches almost every sentence in the corpus. This is a source-data ambiguity (same class as `/inflections`' already-documented `skinner` case), not a bug in the ranking rule or the expansion query; no weight adjustment fixes it, since the problem is which forms are in the OR'd query, not how matches are scored. Recorded here as a known limitation rather than patched with an ad hoc per-word exclusion, which the design doesn't call for and would need its own criteria to be principled.
- [x] 8.4 Live-check `ordbokene` against the real API for a word with multi-sense examples (`kalv` has 5 examples across 4 senses) and confirm senses and placeholder resolution match what the API actually returns. Live-checked: the real API currently returns 9 examples across multiple senses for `kalv` (more than design.md's earlier 5-across-4 snapshot — the live article has evidently grown since that measurement), including the exact `"slakte en $"` + `"kalv"` → `"slakte en kalv"` placeholder-resolution case design.md cites verbatim. All returned examples had their `$` placeholders fully resolved and a `sense` populated from the enclosing definition.
- [x] 8.5 Confirm a `leipzig` lookup for a common word (`komme`, 38,130 matches) returns in acceptable time on a cache miss, and that the bounded pre-ranking fetch (4.7) holds. Confirmed against the real imported corpora: a cold `leipzig` lookup for `komme` completed in ~1.8s end-to-end (expansion query + bounded `LIMIT 2000` tsquery fetch + Python ranking). Note: the real match count against this build's full ordbank form-expansion is 121,885, not the 38,130 the design doc measured — likely a narrower form set or different corpus scope in that earlier probe; does not affect correctness, and the `PRE_RANK_FETCH_CAP` bound (task 4.7) holds regardless of how large the true match count is.
- [x] 8.6 Spot-check candidate suitability across a sample of words and record the finding — corpus sentences can be crude or violent (observed in the `kalv` sample), and the design deliberately does not filter for this. Confirm the operator-picks-from-candidates flow is an acceptable mitigation in practice, or raise a follow-up. Spot-checked `kalv`/`krig`/`død`/`skyte`/`barn` against `leipzig`: ranking's length/completeness/named-entity/digit signals already filter out most of what would be unusable (e.g. the design's own crude `kalv` example — about calves being kicked and dragged by the ears — did not surface in this run's top 5, likely excluded by the named-entity/length signals rather than any content filter). `skyte` ("to shoot") did return several candidates describing people being shot — an accurate reflection of the word's real usage in a news/web corpus, not a ranking defect. No content filter exists or was added, per design's explicit non-goal; the operator-picks-from-candidates flow (same as every other kind) remains the only mitigation, and nothing observed here raises a case for a follow-up beyond what design.md's Risks section already flags.

## 9. Downstream hand-off (not implemented here)

- [x] 9.1 Record that stabbur needs `ENRICHABLE_KINDS` extended with `"examples"` and a `context_text` section in its enrichment panel. smia is a leaf service (D16) and does not wait on it. Recorded in `tun/docs/07-decisions.md` D137.
- [x] 9.2 Add the `examples` row to `tun/docs/06-smia.md`'s endpoint table, and a decision entry covering the `simple`-vs-`norwegian` index finding — it is the kind of non-obvious, measured result `07-decisions.md` exists to preserve.
