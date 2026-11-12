## 1. Fixtures and groundwork

- [x] 1.1 Capture real responses with `Origin` set into `tests/fixtures/lexin/`: `nb-nb` for `avlyse` and `skinner`, `nb-en` for `hånd`, and the `{"err":"Access denied"}` body (a no-header call). Trim each to the rows the tests need; keep `result`, `resArray`, `exactMatchFound` and drop `ordbankList` bodies.
- [x] 1.2 Re-read `adapters/ordbokene.py`, `adapters/ordbokene_examples.py`, `adapters/dictcc_static.py` (`UnsupportedPairError`), and `tests/test_ordbokene*.py` for conventions and the network-mocking pattern.

## 2. Shared client (`adapters/_lexin.py`)

- [x] 2.1 `prepare_query(text)` per design D8: lowercase; `, ^|;/"` and `()` → space; trim; collapse runs of spaces.
- [x] 2.2 Rate limiter per D7: module-level lock and last-call time; `min_interval` read from `LEXIN_MIN_INTERVAL_SECONDS` at call time (default 1.0; `0` disables sleeping).
- [x] 2.3 `find(word, select_lang)`: `requests.get` to the `findwords` URL with `searchWord, lang=bokmål, page=1, selectLang, includeEngLang=0`, headers `Origin: https://lexin.oslomet.no` and a generic User-Agent, `timeout=10`. `RequestException` → `ProviderLookupError`.
- [x] 2.4 Raise `ProviderLookupError` when the body has `error_exist` true or no `result` (design D2). Never return `[]` for these.
- [x] 2.5 Parse `result[0]` into entries keyed by `id` in first-seen order (D3): split `type` on the first `-` into prefix/field; headword from `*-lem` with `~` removed; collect `kat`, `def`, `eks`, `mor`, `utt`; drop empty text; ignore other fields.
- [x] 2.6 Define `UnsupportedPairError(ProviderLookupError)` here (or import dictcc_static's — pick one and keep it consistent).

## 3. Translations (`adapters/lexin_translate.py`)

- [x] 3.1 `_PAIRS = {("nb","nb"): "bokmål", ("nb","en"): "engelsk"}`; any other `(from, to)` raises `UnsupportedPairError`.
- [x] 3.2 `nb→nb`: per entry, one candidate per distinct non-empty definition: `{"text": def, "context": "<headword>, <pos>"}` (pos omitted when absent). Entries with no definition are skipped.
- [x] 3.3 `nb→en`: per entry with a headword, one candidate `{"text": <headword>, "context": "<pos>: <definition>"}` (just `<pos>` or just the definition when the other is absent; omit `context` when both are). Do not join to a second call (D4).
- [x] 3.4 Collapse exact duplicate candidates, keep first-seen order. No result → `{"candidates": []}`.
- [x] 3.5 Register `registry.register("translations", "lexin", LexinTranslateAdapter())`.

## 4. IPA (`adapters/lexin_ipa.py`)

- [x] 4.1 `lang != "nb"` → `{"candidates": []}`.
- [x] 4.2 Keep only entries whose headword (marker-stripped, casefolded) or any whitespace token of the `mor` string equals the casefolded prepared query (D5). Emit `{"ipa": utt}` for each of their `utt` values, deduplicated in first-seen order. Do not add any field.
- [x] 4.3 Document in the module docstring that `ipa` holds LEXIN's respelling notation, not IPA (as `ordbokene.py` does).
- [x] 4.4 Register `registry.register("ipa", "lexin", LexinIpaAdapter())`.

## 5. Examples (`adapters/lexin_examples.py`)

- [x] 5.1 `lang != "nb"` → `{"candidates": []}`.
- [x] 5.2 For each entry in response order, emit `{"text": example, "sense": <definition>}` per example, `sense` omitted when the entry has no definition (a definition-less entry's examples still count); dedupe on `(text, sense)`; apply `limit` (default 3, as `ordbokene_examples`).
- [x] 5.3 Emit no translation field. Register `registry.register("examples", "lexin", LexinExamplesAdapter())`.
- [x] 5.4 Add the three `from . import lexin_* # noqa: F401` lines to `adapters/__init__.py`.

## 6. Tests (all network mocked with the fixtures)

- [x] 6.1 `prepare_query`: casing, `()`/`|`/`;` handling, trimming.
- [x] 6.2 Client: the `Origin` header is sent; an `Access denied` body raises `ProviderLookupError` and is not an empty result; a `RequestException` is wrapped; rows for one `id` that are non-contiguous end up in one entry; `ut~gå` → `utgå`.
- [x] 6.3 Rate limiter: with `LEXIN_MIN_INTERVAL_SECONDS=0.2`, two back-to-back finds take ≥ 0.2 s (patch the clock/sleep rather than really sleeping); `0` does not sleep.
- [x] 6.4 Translations `nb→nb` on `avlyse`: candidates carry the definitions and `avlyse, verb` context; fuzzy hits (`kansellere`, `utgå`) are present with their own headwords. `nb→en` on `hånd`: three `hand` candidates with distinct `context` and one `hind`. `("nb","de")` and `("en","nb")` raise `UnsupportedPairError`.
- [x] 6.5 IPA on `avlyse` returns `'a:vly:se` and none of the fuzzy-hit entries' notation; on `skinner` returns the `sjine` notation (matched via the `mor` string) but not `jernbane`'s; `lang="en"` → empty; a miss → empty.
- [x] 6.6 Examples on `avlyse`: source order, `sense` is the entry definition, no translation key, `limit` honoured, no definition → no `sense` key.
- [x] 6.7 Registry: `lexin` is listed under `translations`, `ipa` and `examples`, and not under `tts` or `inflections`.
- [ ] 6.8 End-to-end through the app for each of the three routes with `provider=lexin`, the HTTP layer mocked; a refused (`Access denied`) response yields the provider-failure status the existing routes use, and nothing is cached. **Tests written (`tests/test_lexin_routes.py`) but NOT RUN — no project dependencies or Postgres in this environment.**
- [ ] 6.9 Run the full suite and confirm no existing test changed behaviour. **NOT RUN — `pytest`/`sqlalchemy` are not installed here (and installing them was declined). `tests/test_lexin.py` (53 tests) was instead run through a minimal stand-in runner with `cache` stubbed: 53 passed. Run `pytest` on a real environment before archiving.**

## 7. Verify on the real API and document

- [x] 7.1 With the real API (once, politely, default limiter): `avlyse` and `skinner` through all three routes; confirm the live shape still matches the fixtures. Resolve the design Open Question: look for an entry with several distinct `*-def` rows. **Done: live shape matches the fixtures; the five words scanned have no multi-definition entries.**
- [ ] 7.2 Confirm `GET /providers` lists `lexin` under the three kinds with no record count, and that `/ui` shows it. **NOT DONE — needs the running app. Registry listing is covered by `test_lexin_is_registered_for_the_three_kinds`.**
- [x] 7.3 Update any provider list in `README.md` and the `/ui` try-it dropdowns if they are enumerated by hand rather than read from the registry. **Done: neither enumerates providers by hand; no edit needed.**
