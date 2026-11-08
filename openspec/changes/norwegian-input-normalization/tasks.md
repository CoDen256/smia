## 1. The shared module

- [ ] 1.1 Create `norwegian.py` at the repo root (beside `cache.py`/`registry.py`, not under `adapters/` — design D6), with a module docstring stating that it is the service's query-preparation layer and that preparation is additive by contract.
- [ ] 1.2 Implement `strip_article_prefix(text) -> str | None`: returns the remainder when the input has 2+ whitespace tokens and the first token case-insensitively equals one of `en`/`ei`/`et`/`å`, else `None`. At most one prefix stripped (design D2).
- [ ] 1.3 Implement `query_variants(text) -> list[str]`: the cross product of as-given/stripped × as-given/lowercased, flattened original-first and deduplicated preserving first occurrence (design D1/D3). A single lowercase word must yield a one-element list.
- [ ] 1.4 Implement `tokenize(text) -> list[str]` per design D8: whitespace split; strip leading/trailing `.` `,` `!` `?` `:` `;` quotes and parentheses; keep hyphenated compounds whole; drop digit-only tokens; drop empties; keep `seg`. Does **not** apply the prefix rule.
- [ ] 1.5 Move `_strip_infinitive_marker`, `_normalize_dictcc_phrase` and `_display_dictcc_phrase` out of `adapters/dictcc_api.py` into `norwegian.py` (design D7), moving the bodies verbatim and leaving the dict.cc-specific annotation regex `[\{\[][^}\]]*[\}\]]` behind in the adapter. Re-express the shared "strip the å" step in terms of 1.2 so there is one definition.

## 2. Module tests

- [ ] 2.1 `tests/test_norwegian.py`: `query_variants` returns `["kalv"]` for a single lowercase word (the no-op case every adapter loop degenerates to).
- [ ] 2.2 Each gender's article and the infinitive marker produce the expected two-variant list: `"en kalv"`, `"ei bok"`, `"et hus"`, `"å komme"`.
- [ ] 2.3 Bare `"å"` and bare `"en"` return one-element lists — the two-token minimum that protects them as standalone Norwegian nouns.
- [ ] 2.4 `"en å"` strips exactly once, yielding `["en å", "å"]`.
- [ ] 2.5 `"god morgen"` (first token not a recognised prefix) returns one element.
- [ ] 2.6 Casing: `"Kalv"` → `["Kalv", "kalv"]`; `"En Kalv"` → `["En Kalv", "en kalv", "Kalv", "kalv"]` in that exact order; the as-given form is always first.
- [ ] 2.7 `tokenize` cases: `"god morgen"`, `"sju-åtte"` (stays whole), `"klokka 5"` (digit dropped), `"anstrenge seg"` (`seg` kept), `"god morgen!"` (punctuation stripped), `"en kalv"` → `["en", "kalv"]` (prefix rule not applied).

## 3. Local providers

- [ ] 3.1 `adapters/ordbank.py`: replace `WHERE oppslag = :word` (line ~119) with a variant-list predicate (`= ANY(:variants)`) built from `query_variants` — one statement, one round trip (design D5).
- [ ] 3.2 `adapters/ordbank.py`: dedupe merged candidates by `(lemma, pos, paradigm)` (design D4), so two variants hitting the same lemma collapse.
- [ ] 3.3 `adapters/kaikki.py`: apply the same variant predicate to both arms of its query — the `e.word = :word` headword match and the `forms[]` containment arm (line ~128-131) — then dedupe by `(lemma, pos, paradigm)`.
- [ ] 3.4 `adapters/dictcc_static.py`: apply the variant predicate to the `term1_clean`/`term2_clean` match, dedupe by its existing `(pos, tags)` grouping key. Only when the Norwegian side is the queried (`from`) side.

## 4. dict.cc live adapter

- [ ] 4.1 `DictccApiInflectAdapter.lookup`: turn the existing per-pair loop into a loop over `(lp, dir, variant)` triples, crossing `_LANG_SELF_LOOKUP_PAIRS[lang]` with `query_variants(word)`. Preserve the existing per-triple `ProviderLookupError` catch and the "raise only if every triple failed" rule (design D4).
- [ ] 4.2 `DictccApiInflectAdapter.lookup`: keep the existing `(pos, paradigm)` dedupe identity — it already handles variant collisions with no change beyond the wider loop.
- [ ] 4.3 `DictccApiTtsAdapter.lookup`: same triple loop; keep the `sha256` dedupe and the per-triple failure tolerance.
- [ ] 4.4 `DictccApiTranslateAdapter.lookup`: cross `query_variants(text)` with the single `_PAIRS` entry for the requested `(from, to)`, but **only when `from` is `nb`** (spec: no English/German article stripping). Merge into the existing `(entry_type, source)` grouping so each variant's matched source phrase keeps its own `context`.
- [ ] 4.5 Confirm the `context` field still reports the source phrase dict.cc actually matched, including when the match came from a stripped variant — the spec requires the caller can see which form answered.

## 5. dict.cc adapter tests

- [ ] 5.1 `tests/test_dictcc_api.py`: `{word: "en kalv", lang: "nb"}` issues 4 requests (2 pairs × 2 variants) and returns `kalv`'s paradigm.
- [ ] 5.2 A single lowercase `nb` word still issues exactly 2 requests — proof the no-op variant case did not regress the request count.
- [ ] 5.3 `en`/`de` self-lookups still issue exactly 1 request each and apply no variant fan-out.
- [ ] 5.4 Both variants resolving to the same paradigm collapse to one candidate; resolving to different paradigms yields two.
- [ ] 5.5 One triple failing while another succeeds still returns candidates; every triple failing raises.
- [ ] 5.6 `{text: "å komme", from: "nb", to: "de"}` returns `komme`'s translations, with `context` naming the phrase dict.cc matched.
- [ ] 5.7 A `from=en` or `from=de` translate request applies no variant fan-out (one request), per the spec's no-English/German-stripping rule.

## 6. Local provider tests

- [ ] 6.1 `tests/` for ordbank: `{word: "et hus", lang: "nb"}` returns `hus`'s `substantiv` paradigm.
- [ ] 6.2 For kaikki: `{word: "ei bok", lang: "nb"}` returns `bok`'s paradigm, and the `forms[]` containment arm still resolves an inflected query.
- [ ] 6.3 For dictcc_static: `{text: "et hus", from: "nb", to: "en"}` returns the translations filed under `hus`.
- [ ] 6.4 A capitalised word whose entry is capitalised still resolves — guards the D3 "case folding is additive" rule against the 2,101 capitalised headwords counted across the local lexicons.
- [ ] 6.5 Confirm each local provider still issues one SQL statement per lookup, not one per variant (design D5).

## 7. Verification

- [ ] 7.1 Run the full suite against a real throwaway Postgres container; confirm no regression, with particular attention to the 23 existing `test_dictcc_api.py` tests that cover the helpers moved in 1.5.
- [ ] 7.2 Confirm no cache-key change: a request for `"kalv"` before and after this change resolves to the same resource id, and `"en kalv"` resolves to a different one (spec: preparation does not affect cache identity).
- [ ] 7.3 Live-check against the real dict.cc API that `"en kalv"` and `"å komme"` now return candidates where they previously returned none.
- [ ] 7.4 Confirm `/ipa` and `/stt` behaviour is byte-identical — neither is wired in this change.
