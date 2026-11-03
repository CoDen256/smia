## 1. Pair map

- [x] 1.1 `adapters/dictcc_api.py`: rename `_LANG_SELF_LOOKUP` to `_LANG_SELF_LOOKUP_PAIRS`, change its type from `dict[str, tuple]` to `dict[str, list[tuple]]` — `nb` gets `[("DENO", 2), ("ENNO", 1)]`, `en`/`de` keep single-element lists.

## 2. Inflect adapter

- [x] 2.1 `DictccApiInflectAdapter.lookup`: loop over `_LANG_SELF_LOOKUP_PAIRS[lang]`, calling `_get_json` + `_parse_inflection_blocks` per pair; catch `ProviderLookupError` per pair rather than letting it propagate immediately (design D2).
- [x] 2.2 Raise the lookup's own `ProviderLookupError` only if every pair failed; otherwise proceed with whatever pairs succeeded.
- [x] 2.3 Concatenate candidates in pair order (`DENO` first, then `ENNO`), deduping by `(pos, paradigm)` identity (design D3).

## 3. TTS adapter

- [x] 3.1 `DictccApiTtsAdapter.lookup`: loop over `_LANG_SELF_LOOKUP_PAIRS[lang]`, each pair doing its own `_get_json` (to find that pair's `entry_id`) + `_fetch_audio` calls for human/synthetic candidates; catch `ProviderLookupError` per pair.
- [x] 3.2 Raise only if every pair failed; otherwise proceed with whatever pairs succeeded.
- [x] 3.3 Dedupe candidates by `sha256` before returning (design D3) — skip appending a candidate whose `sha256` is already present from an earlier pair.

## 4. Tests

- [x] 4.1 `tests/test_dictcc_api.py`: a Norwegian word with data in `ENNO` but not `DENO` returns candidates (inflections and tts) — `test_inflect_nb_merges_both_norwegian_pairs`, `test_tts_nb_merges_both_norwegian_pairs`.
- [x] 4.2 Both pairs returning the same paradigm/audio collapses to one candidate — covered by the existing `test_inflect_noun_full_four_slot_shape`/`test_inflect_cell_with_slash_alternates_keeps_both` (both pairs mocked identically, single canned response) and the rewritten `test_tts_two_step_flow_human_and_synthetic` (4 audio fetches, 2 surviving candidates).
- [x] 4.3 One pair raising `ProviderLookupError` (mocked) while the other succeeds still returns the successful pair's candidates — `test_inflect_nb_one_pair_fails_other_succeeds`, `test_tts_nb_one_pair_fails_other_succeeds`.
- [x] 4.4 Both pairs failing raises, same as today's single-pair-fails behavior — `test_inflect_nb_both_pairs_fail_raises`, `test_tts_nb_both_pairs_fail_raises`.
- [x] 4.5 `en`/`de` self-lookups are unaffected (still single-pair, same requests as before) — `test_inflect_en_de_still_query_exactly_one_pair`, `test_tts_en_de_still_query_exactly_one_pair`, plus the pre-existing `de`-lang tests passing unchanged.

## 5. Verification

- [x] 5.1 Run the existing dictcc_api test suite to confirm no regression on words already covered by the `DENO` pair alone. **23/23 in `test_dictcc_api.py`, 101/101 across the full suite, run against a real throwaway Postgres container.**
- [ ] 5.2 Manually verify (if a known NO↔EN-only word is identified) against the live API that it now returns candidates where it previously returned none. **Not done — no specific NO↔EN-only-but-not-NO↔DE word was identified to test against the live API; the mocked multi-pair-merge tests (4.1) exercise the same code path with controlled fixtures instead.**
