## 1. Service skeleton

- [x] 1.1 Scaffold the Python service (Flask-style, matching phonexa's pattern) with its own Postgres database and `alembic` migrations setup
- [x] 1.2 Implement shared-bearer-token auth middleware, token from env config
- [x] 1.3 Set up project structure for provider adapters (one module per provider) and a provider registry keyed by kind

## 2. Lookup-cache core

- [x] 2.1 Design and migrate the cache table: `(kind, provider, input_hash)` unique key, `payload` jsonb, `created_at`
- [x] 2.2 Implement canonical input hashing (`sha256(kind, provider, normalized_input)`)
- [x] 2.3 Implement the shared runner: cache lookup → on miss, invoke the named provider adapter → store → return
- [x] 2.4 Implement the "provider required unless kind has exactly one configured" validation rule
- [x] 2.5 Implement generic `GET /<kind>/{id}` fetch-by-id (cache-only, no provider invocation, 404 on miss)
- [x] 2.6 Write tests for idempotent POST, cache-miss-on-different-provider, and no-fallback-on-failure behavior

## 3. `/inflections`

- [x] 3.1 Write the Norsk Ordbank import job: parse `fullformsliste.txt`, `lemma.txt`, `paradigme.txt`, `boying.txt` from `providers/nbno/` into Postgres tables
- [x] 3.2 Implement the reverse lookup: surface form (`OPPSLAG`) → grouped candidates across `LEMMA_ID`/`PARADIGME_ID`
- [x] 3.3 Implement paradigm shape mapping (`BOY_GRUPPE`/`BOY_NUMMER` → `substantiv`/`adjektiv`/`verb`/`adverb` shapes from design.md), including the adverb `komparativ`/`superlativ` split (present only for the "adjektiv, adverbtype" paradigm group, absent for plain invariable `adverb`-group paradigms)
- [x] 3.4 Implement the `ordbank` provider adapter and wire `POST /inflections` + `GET /inflections/{id}`
- [x] 3.5 Verify an ambiguous word (e.g. `skinner`) returns multiple candidates end-to-end
- [x] 3.6 Import the kaikki.org dump's `forms[]` field as a queryable table, filtering out `imperative`/`passive`-tagged entries
- [x] 3.7 Implement the `kaikki` provider adapter, mapping surviving `forms[]` tags onto the paradigm shapes from 3.3
- [x] 3.8 Confirm `provider` is now a required field (two providers configured) and update validation accordingly

## 4. `/ipa`

- [x] 4.1 Import the NST NOFABET lexicon (`providers/nbno/nb_uttale_tillegg/original_nst_lexicon_nofabet.csv`) and port the bundled NOFABET→IPA conversion table (`conversion.py`)
- [x] 4.2 Import the dialect CSVs (`nb_uttale_leksika.zip`) and map each dialect code onto a `variety` value; wire multi-candidate dialect lookups
- [x] 4.3 Import the kaikki.org dump's `sounds[].ipa` field as a queryable table
- [x] 4.4 Implement the ordbokene.no API adapter (`body.pronunciation`)
- [x] 4.5 Implement the ipa-dict/nb and wikipron thin-fallback adapters
- [x] 4.6 Wire `POST /ipa` + `GET /ipa/{id}`, returning `candidates[]` (one per variety) across all configured providers — no espeak-ng, no g2p fallback

## 5. `/tts`

- [ ] 5.1 Implement smia's private content-addressed audio cache (distinct from stabbur's canonical blob store)
- [ ] 5.2 Implement the Forvo adapter, returning one candidate per available recording
- [ ] 5.3 Probe dict.cc's audio access (scrape or API) and implement it as a real-recording `/tts` provider
- [ ] 5.4 Import the kaikki.org dump's `sounds[].mp3_url` field as a queryable/fetchable source
- [ ] 5.5 Probe filmot.com's actual v1 API (endpoints, auth, response shape) and implement the adapter: search captions for the phrase, slice the matched clip
- [ ] 5.6 Probe ElevenLabs' free-tier API and implement the synthesis adapter, surfacing voice metadata (e.g. `gender`) per candidate
- [ ] 5.7 Wire `POST /tts` + `GET /tts/{sha256}` (raw bytes), returning `candidates[]` across all configured providers — no piper

## 6. `/translations`

- [ ] 6.1 Port `TranslatorFactory`/`google.ts` scrape logic into a Python adapter
- [ ] 6.2 Port `bing.ts` scrape logic into a Python adapter
- [ ] 6.3 Implement the DeepL free-tier API adapter
- [ ] 6.4 Implement the LibreTranslate API adapter
- [ ] 6.5 Probe dict.cc's translation data (scrape) and implement it as a `/translations` provider, surfacing meaning-specific entries as `context`
- [ ] 6.6 Wire `POST /translations` + `GET /translations/{id}` — response is `{provider, text, context?}` only, no `lang`/`transliteration`/`transcription`

## 7. `/stt`

- [ ] 7.1 Port `transcribeViaHuggingFace` logic from `phonexa/js/shadow.js` into a Python adapter (`hf_whisper`)
- [ ] 7.2 Wire `POST /stt` (multipart audio body) + `GET /stt/{id}`, with `provider` validated as required even though only one is configured

## 8. Provider catalog & `/ui`

- [ ] 8.1 Implement `GET /providers` (static catalog per kind from registered adapters)
- [ ] 8.2 Implement `GET /health` (per-provider last-success/last-failure/quota tracking)
- [ ] 8.3 Build the `/ui` page: provider health display, cache hit-rate stats, manual try-it (bypasses cache) against any registered provider
- [ ] 8.4 Wire `/ui` into the shared cross-service nav shell per D46

## 9. Documentation follow-up

- [ ] 9.1 Update `tun/docs/06-smia.md`'s endpoint table to reflect the no-fallback/single-provider model and finalized provider lists
- [ ] 9.2 Resolve `tun/docs/09-open-questions.md` Q10 with a pointer to this change's ordbank schema work
- [ ] 9.3 Add a new decision row to `tun/docs/07-decisions.md` recording the no-fallback-chain design (supersedes the chain-with-fallback framing implied by D34)
