## 1. Env var naming cleanup

- [ ] 1.1 Rename `adapters/deepl.py`'s `DEEPL_API_KEY` → `DEEPL_TOKEN`
- [ ] 1.2 Update any tests referencing the old env var name

## 2. docker-compose + env documentation

- [ ] 2.1 Add `HF_TOKEN`, `DEEPL_TOKEN`, `ELEVENLABS_TOKEN` to `docker-compose.yml`'s `backend.environment`, each as `${VAR:-}`
- [ ] 2.2 Write `.env.example` listing every token var, one-line comment per var on purpose and where to obtain one, matching the user's existing `.env` naming
- [ ] 2.3 Verify `docker compose up` with a filled `.env` makes `deepl`/`elevenlabs`/`hf_whisper` work without code changes, and with an empty `.env` fails cleanly at adapter-call time (not at container startup)

## 3. Manual-link adapter

- [ ] 3.1 Confirm Forvo's word-page URL shape and language-code scheme live
- [ ] 3.2 Confirm filmot's public search URL shape live (fall back to a generic search URL if its results page also requires a key)
- [ ] 3.3 Implement a `ManualLinkAdapter` (or per-provider small adapters) returning `{candidates: [], url}`, parameterized by a URL-template function
- [ ] 3.4 Register it for `forvo` and `filmot` on `/tts`, removing their entries from `adapters/not_configured.py`
- [ ] 3.5 Verify manual-link responses are cached normally per `lookup-cache` (same input → same cached `url`, no re-construction)

## 4. Tests

- [ ] 4.1 Test the manual-link adapter's URL construction for both Forvo and filmot, across a couple of languages
- [ ] 4.2 Test that `GET /providers` still lists `forvo`/`filmot` for `tts`
- [ ] 4.3 Test the renamed `DEEPL_TOKEN` env var is picked up correctly by `deepl`
