## 1. Hugging Face → `huggingface_hub`

- [x] 1.1 Add `huggingface_hub` to `requirements.txt`
- [x] 1.2 Rewrite `adapters/hf_whisper.py`'s `lookup()` to call `InferenceClient(token=...).automatic_speech_recognition(...)` (or the appropriate client method), preserving the existing raw-bytes vs. base64-with-language request-shape distinction if the client requires it
- [x] 1.3 Map the client's exception types to `ProviderLookupError`, preserving the existing "model is loading" friendly message behavior
- [x] 1.4 Update `tests/test_stt.py` to mock the SDK client instead of `requests`, keeping existing assertions on the adapter's returned dict

## 2. DeepL → `deepl` package

- [x] 2.1 Add `deepl` to `requirements.txt`
- [x] 2.2 Rewrite `adapters/deepl.py`'s `lookup()` to call `deepl.Translator(api_key).translate_text(...)` — found live: the client rejects bare `"EN"`/`"PT"` as `target_lang` (deprecated by DeepL), so the adapter now maps those to `"EN-US"`/`"PT-PT"`; `source_lang` has no such restriction
- [x] 2.3 Map the client's exception types to `ProviderLookupError`
- [x] 2.4 Update `tests/test_translate_adapters.py`'s DeepL cases to mock the SDK client instead of `requests`

## 3. Bing → `translators` package

- [x] 3.1 Add `translators` to `requirements.txt`
- [x] 3.2 Rewrite `adapters/bing_translate.py`'s `lookup()` to call `translators.translate_text(text, translator="bing", from_language=..., to_language=...)`, deleting the hand-rolled edge-auth-token exchange entirely
- [x] 3.3 Map `translators`' exceptions to `ProviderLookupError`
- [x] 3.4 Update `tests/test_translate_adapters.py`'s Bing cases to mock `translators.translate_text` instead of the two-step `requests` auth+translate flow

## 4. Drop `libretranslate`

- [x] 4.1 Delete `adapters/libretranslate.py`
- [x] 4.2 Remove its import/registration from `adapters/__init__.py`
- [x] 4.3 Delete its tests from `tests/test_translate_adapters.py` (or wherever they live)
- [x] 4.4 Confirm `GET /providers` no longer lists `libretranslate` for `translations`, and that requesting `provider=libretranslate` now returns the standard unknown-provider error

## 5. Document the no-swap adapters

- [x] 5.1 Add a short docstring note to `adapters/google_translate.py` recording why no swap applies — not "no library exists" (one does: `translators`), but "using it would lose the `dict[]` sense structure `translate-multi-candidate` depends on"
- [x] 5.2 Add a short docstring note to `adapters/dictcc_api.py` and `adapters/dictcc_static.py` recording why no swap applies (no published client for either surface)

## 6. Verify

- [x] 6.1 Run the full test suite; confirm no behavior change in any adapter's returned dict shape or error contract besides the `libretranslate` removal
- [x] 6.2 Manually verify `adapters/bing_translate.py` via `translators` against a live call, now that the old hand-rolled path was confirmed broken (404 on the edge-auth endpoint) — confirmed working through the real Docker container (3+ consecutive successful translations); found and fixed two deployment issues along the way: the container needed Node.js installed for Bing's JS signing logic (added to `Dockerfile`), and one isolated `OSError(90, 'Message too long')` right after a container restart that didn't recur — documented as a known transient flake in the adapter's docstring, not a code bug
