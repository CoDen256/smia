## 1. dict.cc API adapter (`dictcc_api`)

- [x] 1.1 Confirm the `lp`/`dir` codes for both supported pairs (Norwegian↔English confirmed as `ENNO` in `api.md`; Norwegian↔German needs live confirmation) and build the `{(from, to): (lp, dir)}` mapping table — confirmed live against the real API: `lp=DENO` works for German↔Norwegian (`lp=NODE` does not), `dir=1`/`dir=2` select which side of `lp` the input is on
- [x] 1.2 Implement the `app_translations.php` call (clean-lemma requirement, `appversioncode` handling) and parse `translations[]` into `{provider, text, context?}` for `/translations`
- [x] 1.3 Parse `inflections_repl` into the existing paradigm shapes for `/inflections`; return `candidates: []` when no table is present — handles both the Norwegian 4-slot (indef/def sg/pl) and German 2-slot (sg/pl only) NOUN shapes and the VERB shape, confirmed against live `kalv`/`hus`/`Haus`/`gehen`/`gå` responses; a multi-POS response (e.g. "gehen" as both noun and verb) becomes multiple candidates. `ADJ` is intentionally not parsed (see adapter docstring)
- [x] 1.4 Implement the two-step `/tts` flow: resolve the entry id via 1.2's call, then call `speak.audio.v2.php` for both the human recording and the synthesized voice, tagging each candidate with `source` (`human`/`synthetic`) and `voice` where applicable — verified live, real MP3 bytes returned and cached for both "kalv" (human+synthetic "Liv") and "Haus" (human only, no confirmed German voice name)
- [x] 1.5 Replace the `not_configured.py` stub registration for dict.cc with `dictcc_api` across `/translations`, `/inflections`, `/tts`
- [x] 1.6 Un-stub tasks 5.3 and 6.5 in the archived `smia-service-foundation` change tracking (note completion there, or cross-reference from this change)

## 2. dict.cc static dataset (`dictcc_static`)

- [x] 2.1 Write the import job for `providers/dict/*.txt` (`NO-EN`, `NO-DE`, `DE-EN`) into a local lookup table (`term1, term2, pos, tags`) — also adds `term1_clean`/`term2_clean` columns, found necessary live: the raw dump stores grammar annotations inline (`"Haus {n}"`), so an exact-match query for the bare lemma matched nothing without a normalized column
- [x] 2.2 Implement the `dictcc_static` adapter for `/translations` only: direct lemma-pair lookup → `{provider, text, context?}` using the `tags` column for `context`
- [x] 2.3 Verify the import never exposes the raw dump files or a bulk export via any route, per the dataset's private-use license — the import job also asserts the license header still says "private use" before importing, refusing to proceed otherwise
- [x] 2.4 Register `dictcc_static` as a `/translations` provider alongside `dictcc_api`

## 3. Tests

- [x] 3.1 Test `dictcc_api` translation parsing against a captured example response (from `api.md`)
- [x] 3.2 Test `dictcc_api` inflection parsing (noun paradigm from the `kalv` example) and the no-table case
- [x] 3.3 Test `dictcc_api` `/tts` two-step flow and candidate tagging (human vs synthetic)
- [x] 3.4 Test `dictcc_static` lookup against a small fixture slice of the imported data
- [x] 3.5 Test unsupported-language-pair rejection for both adapters
