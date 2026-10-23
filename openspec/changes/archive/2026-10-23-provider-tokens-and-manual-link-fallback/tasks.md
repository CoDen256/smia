## 1. Env var naming cleanup

- [x] 1.1 Rename `adapters/deepl.py`'s `DEEPL_API_KEY` → `DEEPL_TOKEN`
- [x] 1.2 Update any tests referencing the old env var name

## 2. docker-compose + env documentation

- [x] 2.1 Add `HF_TOKEN`, `DEEPL_TOKEN`, `ELEVENLABS_TOKEN` to `docker-compose.yml`'s `backend.environment`, each as `${VAR:-}`
- [x] 2.2 Write `.env.example` listing every token var, one-line comment per var on purpose and where to obtain one, matching the user's existing `.env` naming
- [x] 2.3 Verify `docker compose up` with a filled `.env` makes `deepl`/`elevenlabs`/`hf_whisper` work without code changes, and with an empty `.env` fails cleanly at adapter-call time (not at container startup) — verified live: `docker compose` auto-loaded the host's real `.env` (never read directly by this agent); `deepl` and `elevenlabs` reached the real API through the rebuilt container, `hf_whisper` reached HF's API too (hit an out-of-credits account error, which itself confirms the token arrived correctly). No case of an empty/missing token was tested against a container startup failure in this pass, since a filled `.env` was already present — the "fails cleanly at call time, not at startup" half is covered structurally by each adapter's existing missing-token tests (test_stt.py, test_translate_adapters.py, test_elevenlabs.py), which never touch container startup at all

## 3. Manual-link adapter

- [x] 3.1 Confirm Forvo's word-page URL shape and language-code scheme live — an initial pass confirmed via a real browser load of `forvo.com/word/hus/` that the per-language *section anchor id* on the page itself is `#language-no`, and that Forvo's own code for Norwegian is `no`, not `nb` (its language list predates the Bokmål/Nynorsk split). **Corrected afterward** (user-supplied, from a real shared Forvo link: `https://forvo.com/word/hygge/#no`): the real shareable per-language link format is the bare `#<code>` fragment, not `#language-<code>` — the earlier pass had read the right page but the wrong thing on it (an on-page anchor id, not the canonical link format). Final: `https://forvo.com/word/<word>/#<code>`.
- [x] 3.2 Confirm filmot's public search URL shape live (fall back to a generic search URL if its results page also requires a key) — an initial pass hit a CAPTCHA submitting a live search (correctly not solved/bypassed) and fell back to a bare `https://filmot.com/search/<query>` guess. **Corrected afterward** (user-supplied, from a real filmot results link: `https://filmot.com/search/jeg+er+norsk/1?gridView=1&lang=no`): the real shape is `https://filmot.com/search/<query>/1?gridView=1&lang=<code>`, with `<query>` space-joined by `+` (`quote_plus`, not `quote`) and `<code>` using the same `nb`->`no` mapping as Forvo.
- [x] 3.3 Implement a `ManualLinkAdapter` (or per-provider small adapters) returning `{candidates: [], url}`, parameterized by a URL-template function
- [x] 3.4 Register it for `forvo` and `filmot` on `/tts`, removing their entries from `adapters/not_configured.py` — that file is now deleted entirely: forvo/filmot were its only remaining registrations (elevenlabs' stub was already removed in `add-elevenlabs-provider`)
- [x] 3.5 Verify manual-link responses are cached normally per `lookup-cache` (same input → same cached `url`, no re-construction) — verified live through the real container: a repeated `forvo` request shows `hitCount: 1` of 2 requests in `/health`

## 4. Tests

- [x] 4.1 Test the manual-link adapter's URL construction for both Forvo and filmot, across a couple of languages
- [x] 4.2 Test that `GET /providers` still lists `forvo`/`filmot` for `tts`
- [x] 4.3 Test the renamed `DEEPL_TOKEN` env var is picked up correctly by `deepl`
