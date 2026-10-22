## 1. `google_translate`

- [ ] 1.1 Verify Google's live `dict[]` response structure (or a recorded fixture) to confirm one candidate per `dict[]` entry is correct, not an oversimplification
- [ ] 1.2 Rewrite `GoogleTranslateAdapter.lookup()` to return `{candidates: [{text, context?}]}`: one candidate per `dict[]` entry, `text` = that entry's terms joined with `/`, `context` = the entry's POS/sense label
- [ ] 1.3 Handle the case where Google returns no `dict[]` (plain translation only) — one candidate, `text` = the concatenated `sentences[].trans`, no `context`

## 2. `dictcc_api` and `dictcc_static`

- [ ] 2.1 Rewrite `DictccApiTranslateAdapter.lookup()` to iterate all of `translations[]` (not just `[0]`), grouping by `entry_type` and joining same-`entry_type` entries' text with `/`
- [ ] 2.2 Rewrite `dictcc_static`'s translation lookup to return all matching rows for the lemma pair, grouped by its tags column the same way
- [ ] 2.3 Update `tests/test_dictcc_api.py` and `tests/test_dictcc_static.py` for the new grouped-candidates shape

## 3. `deepl`, `bing_translate`

- [ ] 3.1 Wrap `deepl.py`'s single translation in `{candidates: [{text}]}`
- [ ] 3.2 Wrap `bing_translate.py`'s single translation (via `translators`, per `provider-client-libraries`) in `{candidates: [{text}]}` — land this after that change's Bing swap, not before

## 4. Response plumbing

- [ ] 4.1 Confirm the generic `/translations` route/runner (`routes/generic.py`, `cache.py`) needs no change to carry a `candidates[]`-shaped payload (it should already be kind-agnostic, proven by `/ipa`/`/tts`) — fix if any `/translations`-specific flat-shape assumption is found
- [ ] 4.2 Update `tests/test_translate_adapters.py` for every adapter's new `candidates[]` shape
- [ ] 4.3 Update `tests/test_routes.py` if it has any `/translations`-specific flat-shape assertions

## 5. Verify

- [ ] 5.1 Manually verify `POST /translations` for Norwegian `igjen` → `en` returns separate candidates for "again" vs. "back"/"left" (joined), against whichever provider(s) are reachable in this environment
- [ ] 5.2 Run the full test suite
