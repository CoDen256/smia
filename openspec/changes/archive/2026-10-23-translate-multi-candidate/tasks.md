## 1. `google_translate`

- [x] 1.1 Verify Google's live `dict[]` response structure (or a recorded fixture) to confirm one candidate per `dict[]` entry is correct, not an oversimplification — confirmed live via a real browser `fetch()` (plain `requests`/`curl` hit Google's IP-reputation 429 block): Norwegian "rett" returns three separate `dict[]` entries (noun/"court", adjective/"straight", adverb/"straight"); "lett" and "igjen" each return one entry with multiple `terms` ("easy"/"light", "again"/"over") correctly joined with `/`. One candidate per `dict[]` entry is confirmed correct.
- [x] 1.2 Rewrite `GoogleTranslateAdapter.lookup()` to return `{candidates: [{text, context?}]}`: one candidate per `dict[]` entry, `text` = that entry's terms joined with `/`, `context` = the entry's POS/sense label
- [x] 1.3 Handle the case where Google returns no `dict[]` (plain translation only) — one candidate, `text` = the concatenated `sentences[].trans`, no `context`

## 2. `dictcc_api` and `dictcc_static`

- [x] 2.1 Rewrite `DictccApiTranslateAdapter.lookup()` to iterate all of `translations[]` (not just `[0]`), grouping by `entry_type` and joining same-`entry_type` entries' text with `/`. **Corrected post-completion** (user-reported): live testing against "komme" found `entry_type` alone too coarse — all 18 entries are tagged `entry_type="verb"` but cover a dozen distinct phrasal-verb senses, which this grouping collapsed into one candidate. Regrouped by `(entry_type, source phrase)` instead — see 2.4.
- [x] 2.2 Rewrite `dictcc_static`'s translation lookup to return all matching rows for the lemma pair, grouped by `(pos, tags)` the same way (dict.cc's static dump has no `entry_type` column — `pos`+`tags` together are the equivalent sense boundary)
- [x] 2.3 Update `tests/test_dictcc_api.py` and `tests/test_dictcc_static.py` for the new grouped-candidates shape

## 3. `deepl`, `bing_translate`

- [x] 3.1 Wrap `deepl.py`'s single translation in `{candidates: [{text}]}`
- [x] 3.2 Wrap `bing_translate.py`'s single translation (via `translators`, per `provider-client-libraries`) in `{candidates: [{text}]}` — landed after that change's Bing swap

## 4. Response plumbing

- [x] 4.1 Confirm the generic `/translations` route/runner (`routes/generic.py`, `cache.py`) needs no change to carry a `candidates[]`-shaped payload (it should already be kind-agnostic, proven by `/ipa`/`/tts`) — fix if any `/translations`-specific flat-shape assumption is found. Confirmed: `cache.py`'s `run_lookup()` only merges `{"provider": provider, **result}` and `routes/generic.py` only `jsonify()`s the payload — neither inspects `text`/`candidates` keys. No change needed.
- [x] 4.2 Update `tests/test_translate_adapters.py` for every adapter's new `candidates[]` shape
- [x] 4.3 Update `tests/test_routes.py` if it has any `/translations`-specific flat-shape assertions. Confirmed: no `/translations`-specific assertions exist in this file. No change needed.

## 6. Post-completion fixes (user-reported, after initial archive-readiness)

- [x] 6.1 Regroup `DictccApiTranslateAdapter` by `(entry_type, source phrase)` instead of `entry_type` alone — fixes both the "komme" over-grouping (2.1) and generalizes/subsumes a separate one-off fix for the untyped (`entry_type=""`) "Kom igjen!" -> "Come on!" phrase entry, which needed its matched source phrase surfaced as `context` so it doesn't read as an unexplained mismatch. Live-verified against "komme" (13 separate candidates, each with phrase-specific `context`) and "igjen" (9 candidates, same treatment) through the rebuilt Docker container.
- [x] 6.2 `dictcc_static`: strip the Norwegian verb infinitive marker ("å komme" -> "komme") in `scripts/import_dictcc_static.py`'s `_clean()`, same as `dictcc_api`'s own `_normalize_label` — a bare-infinitive query like "komme" matched nothing, since every Norwegian verb row is stored with the marker. Reimported `providers/dict/*.txt` to apply this to already-stored rows (existing deployments need the same reimport, or a fresh volume).
- [x] 6.3 Updated `tests/test_dictcc_api.py` and `tests/test_dictcc_static.py` for both fixes; full suite re-verified (90/90 passing after 6.1-6.2, including the `/ipa` field-rename work landed in the same follow-up session).

## 5. Verify

- [x] 5.1 Manually verify `POST /translations` for Norwegian `igjen` → `en` returns separate candidates for "again" vs. "back"/"left" (joined), against whichever provider(s) are reachable in this environment. Live-verified against the rebuilt Docker container: `dictcc_api` returns 3 separate candidates (`[adv]` "again/left/on and on/repeatedly/over and over/over and over again", unlabeled "Come on!", `[verb]` "to recognize sb./to recover/..."); `dictcc_static` returns 1 candidate (`adv` "again/left"). Both correctly group same-sense entries with `/` and keep distinct senses as separate candidates. Google/DeepL/Bing not independently re-verified live here (already covered by 1.1 and unit tests — no reachability regression expected since the wrapping is purely additive).
- [x] 5.2 Run the full test suite. 88/88 passed.
