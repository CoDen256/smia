## 1. Pair map

- [ ] 1.1 `adapters/dictcc_api.py`: rename `_LANG_SELF_LOOKUP` to `_LANG_SELF_LOOKUP_PAIRS`, change its type from `dict[str, tuple]` to `dict[str, list[tuple]]` — `nb` gets `[("DENO", 2), ("ENNO", 1)]`, `en`/`de` keep single-element lists.

## 2. Inflect adapter

- [ ] 2.1 `DictccApiInflectAdapter.lookup`: loop over `_LANG_SELF_LOOKUP_PAIRS[lang]`, calling `_get_json` + `_parse_inflection_blocks` per pair; catch `ProviderLookupError` per pair rather than letting it propagate immediately (design D2).
- [ ] 2.2 Raise the lookup's own `ProviderLookupError` only if every pair failed; otherwise proceed with whatever pairs succeeded.
- [ ] 2.3 Concatenate candidates in pair order (`DENO` first, then `ENNO`), deduping by `(pos, paradigm)` identity (design D3).

## 3. TTS adapter

- [ ] 3.1 `DictccApiTtsAdapter.lookup`: loop over `_LANG_SELF_LOOKUP_PAIRS[lang]`, each pair doing its own `_get_json` (to find that pair's `entry_id`) + `_fetch_audio` calls for human/synthetic candidates; catch `ProviderLookupError` per pair.
- [ ] 3.2 Raise only if every pair failed; otherwise proceed with whatever pairs succeeded.
- [ ] 3.3 Dedupe candidates by `sha256` before returning (design D3) — skip appending a candidate whose `sha256` is already present from an earlier pair.

## 4. Tests

- [ ] 4.1 `tests/test_dictcc_api.py` (or wherever this adapter is tested): a Norwegian word with data in `ENNO` but not `DENO` returns candidates (inflections and tts).
- [ ] 4.2 Both pairs returning the same paradigm/audio collapses to one candidate.
- [ ] 4.3 One pair raising `ProviderLookupError` (mocked) while the other succeeds still returns the successful pair's candidates.
- [ ] 4.4 Both pairs failing raises, same as today's single-pair-fails behavior.
- [ ] 4.5 `en`/`de` self-lookups are unaffected (still single-pair, same requests as before).

## 5. Verification

- [ ] 5.1 Run the existing dictcc_api test suite to confirm no regression on words already covered by the `DENO` pair alone.
- [ ] 5.2 Manually verify (if a known NO↔EN-only word is identified) against the live API that it now returns candidates where it previously returned none.
