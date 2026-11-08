## 1. Prerequisite check

- [x] 1.1 Confirm `norwegian-input-normalization` is implemented and `norwegian.py` exposes `tokenize()` and `query_variants()` — this change consumes both and must not ship first.
- [x] 1.2 Measure `nst`'s multi-word coverage against the running database (`SELECT count(*) FROM nst_lexicon WHERE wordform LIKE '% %'`, same for `nst_dialect`). Record the number in design.md's Open Questions — if it is large, the phrase branch matters more for the best-quality provider than the other four providers suggested.

## 2. The /ipa route

- [x] 2.1 Create `routes/ipa.py` with its own `POST /ipa` handler, replacing `app.py`'s `register_lookup_routes(app, "ipa", _extract_ipa_input)`. Keep the generic `GET /ipa/{id}` registration unchanged (design D8). Do not modify `routes/generic.py` — no other kind may be affected.
- [x] 2.2 Validate the body as before (`text` and `lang` required → 400 on absence) and resolve the provider once for the whole request, so every subsequent lookup uses that one provider (design D5).
- [x] 2.3 Whole-phrase attempt: apply `query_variants(text)` to the full input and `run_lookup` each variant until one returns non-empty candidates (design D7). On success return `{provider, mode: "phrase", candidates}` with the `Location` header for the **caller's own** input.
- [x] 2.4 Let `ProviderLookupError` propagate as a 502 without attempting a split (design D6) — a broken provider must look broken.
- [x] 2.5 Short-circuit single-token input: if `tokenize(text)` yields one token or fewer, return `mode: "phrase"` with whatever the phrase attempt produced (including `candidates: []`). Never split a single word — this is what preserves existing-caller compatibility.

## 3. The per-word split

- [x] 3.1 On a phrase miss with 2+ tokens, `tokenize(text)` and call `run_lookup(db, "ipa", provider, {text: <token>, lang})` per token — through the ordinary runner, so each token gets its own `LookupCache` row and resource id (design D4).
- [x] 3.2 Build `tokens` as one entry per token in input order, each `{text, candidates}`. A token with no entry gets `candidates: []` and stays in the array at its position (design D3).
- [x] 3.3 Compute `joined` iff **every** token has exactly one candidate: space-separated transcriptions in input order. Omit the key entirely otherwise — not `null`, not `""` (design D2).
- [x] 3.4 Store the assembled `per_word` payload under the phrase input's own resource id so `GET /ipa/{id}` and the `Location` header satisfy the `lookup-cache` contract. One request creates N+1 rows.
- [x] 3.5 Propagate `forceRefresh` to every token lookup as well as the phrase lookup (design D4).

## 4. Route tests — phrase branch

- [x] 4.1 `tests/test_ipa_multiword.py`: a single-word request returns `mode: "phrase"` with the same `candidates` payload as before this change, and **no** `tokens` key.
- [x] 4.2 A single word with no entry returns `mode: "phrase"`, `candidates: []` — and asserts no token lookups were performed.
- [x] 4.3 A real multi-word entry returns `mode: "phrase"` and performs no split. Use `ipadict` with `av og til`, one of the 199 confirmed multi-word entries in `providers/open-dict/nb.txt`.
- [x] 4.4 A provider raising `ProviderLookupError` on the phrase attempt yields 502 and performs no token lookups.
- [x] 4.5 `{text: "en kalv"}` resolves via the phrase branch to `kalv`'s transcription — not a per-word breakdown containing the article (design D7).

## 5. Route tests — split branch

- [x] 5.1 A two-word phrase with both words known returns `mode: "per_word"` with two token entries in input order.
- [x] 5.2 A phrase with one unknown word returns that token with `candidates: []`, in position, and a 200 rather than an error.
- [x] 5.3 A phrase with no known words returns every token with `candidates: []` and a 200.
- [x] 5.4 `joined` present when every token has exactly one candidate; absent when any token has 0; absent when any token has 2+. Assert the key is **missing**, not null.
- [x] 5.5 Against a multi-dialect provider (`nst`), each token's `candidates` carries one entry per variety and `joined` is consequently absent.
- [x] 5.6 Tokenizer rules reach the response: a hyphenated compound is one token; digit-only tokens produce no token entry; `seg` in `anstrenge seg` is looked up and present.
- [x] 5.7 A gap is not filled by another provider: with two providers configured and only the unnamed one holding a token, that token stays empty and the other provider is not called (design D5).

## 6. Cache behaviour tests

- [x] 6.1 After a phrase request, each token's input is independently retrievable — a direct `POST /ipa` for that single word is served from cache without invoking the provider.
- [x] 6.2 The `Location` header and resource id from a `per_word` response identify the caller's phrase input; `GET` on that id returns the assembled `per_word` payload.
- [x] 6.3 `forceRefresh` on a phrase re-invokes the provider for every token, not just the phrase.
- [x] 6.4 Confirm N+1 cache rows exist after one N-token phrase request.

## 7. Verification

- [x] 7.1 Run the full suite against a real throwaway Postgres container; confirm no regression in the existing `/ipa` tests.
- [x] 7.2 Live-check `god morgen` against each of the five providers, recording which take the phrase branch and which split — confirms the phrase-vs-split decision against real data rather than fixtures.
- [x] 7.3 Confirm `/inflections`, `/translations`, `/tts` and `/stt` responses are byte-identical — `routes/generic.py` must be untouched.
- [x] 7.4 Note in the change record that `/ipa`'s `health` counters are now token-denominated (design D4), so the `/health` and `/ui` numbers are not comparable across this change.
- [x] 7.5 Confirm a pre-change cached `/ipa` row (no `mode` key) is still served correctly by `GET /ipa/{id}`.

## 8. Downstream hand-off (not implemented here)

- [x] 8.1 Record in the change record that stabbur's enrichment panel renders a flat `candidates` array and will show nothing for a `mode: "per_word"` response until updated — same visible outcome as today's empty list, so not a regression, but it is the follow-up work that makes this usable from the UI.
- [x] 8.2 Verify `tun/docs/06-smia.md`'s `/ipa` row still describes the contract correctly, and update its Out column to mention `mode`/`tokens` if not.
