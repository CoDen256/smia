## 1. Registry support

- [x] 1.1 Add an optional `count` keyword to `ProviderRegistry.register()`, stored parallel to `available` (keyed by `(kind, name)`), taking a `(db) -> int` callable.
- [x] 1.2 Add `ProviderRegistry.counts_for(db, kind) -> dict[str, int]`, returning only the providers for that kind that registered a `count` callable, invoked live against the given session.

## 2. Wire up table-backed adapters

- [x] 2.1 `adapters/ordbank.py`: register a count against `ordbank_fullform`.
- [x] 2.2 `adapters/kaikki.py`, `adapters/kaikki_ipa.py`, `adapters/kaikki_tts.py`: each register a count against `kaikki_entry` (shared count function, defined once).
- [x] 2.3 `adapters/nst.py`: register a count against `nst_lexicon`.
- [x] 2.4 `adapters/ipadict.py`: register a count against `ipa_dict_entry`.
- [x] 2.5 `adapters/wikipron.py`: register a count against `wikipron_entry`.
- [x] 2.6 `adapters/dictcc_static.py`: register a count against `dictcc_static_entry`.
- [x] 2.7 Confirm no `count` is registered for `dictcc_api`, `deepl`, `google_translate`, `bing_translate`, `libretranslate`, `elevenlabs`, `hf_whisper`, `ordbokene`, `forvo`, `filmot`.

## 3. API response

- [x] 3.1 `app.py`'s `GET /providers` handler: build a `counts` map (kind -> {provider: count}) alongside the existing per-kind provider-name lists, using `counts_for`.
- [x] 3.2 Add/update a test in `tests/test_routes.py` (or wherever `/providers` is currently tested) asserting a table-backed provider reports a count and a live-call provider reports none.

## 4. UI

- [x] 4.1 `ui/ui.js` `renderCatalog`: read the new `counts` field and render each table-backed provider's count next to its name.
- [x] 4.2 `ui/ui.js`/`ui/ui.css`: grey out (muted styling) any provider row whose count is `0`, while still listing it.
- [ ] 4.3 Manually verify in a browser: an empty-table provider (e.g. before running its import script) shows greyed with `(0)`, and after running the import, a refresh shows the real count un-greyed. **Backend verified (full test suite, 93/93, run against a real throwaway Postgres container) — browser rendering itself not visually checked.**

## 5. Docs

- [x] 5.1 Update `tun/docs/06-smia.md` if it documents `/providers`' response shape, to mention the new `counts` field.
