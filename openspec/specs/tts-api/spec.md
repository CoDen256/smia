## Purpose

`POST /tts` looks up or synthesizes audio for Norwegian text, following the `lookup-cache` contract. Returns one candidate per available recording/rendering, written into smia's own private content-addressed audio cache (not a canonical store — see ecosystem audio ownership rules).

## Requirements

### Requirement: Audio lookup/synthesis returns multiple candidates
`POST /tts` SHALL accept `{text, lang, provider}` (no `voice` field) and return `{provider, candidates: [{sha256, ...metadata}]}`, calling only the named provider. A provider that has more than one recording/rendering available for the input (e.g. multiple speakers) SHALL return one candidate per recording rather than picking one. Metadata fields (e.g. `gender`, `source`, `voice`) are present when the provider supplies them.

#### Scenario: Synthesized candidate alongside a recording
- **WHEN** the named provider can both locate a real recording and synthesize a voice for the same input (e.g. `dictcc_api`'s synthetic-voice candidate)
- **THEN** the system generates the synthesized audio, stores it, and returns it as its own candidate with `sha256` and available voice metadata (e.g. `voice`), tagged distinctly from any recorded candidate

#### Scenario: Recorded-speech provider with multiple speakers
- **WHEN** the named provider has multiple real recordings for the same input (e.g. `dictcc_api`)
- **THEN** the response's `candidates` array contains one entry per recording, each with its own `sha256`

#### Scenario: Recorded-speech provider with one match
- **WHEN** the named provider locates exactly one real recording (e.g. kaikki.org's `sounds[].mp3_url`)
- **THEN** the response's `candidates` array contains exactly one entry

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (manual-link fallback — no free tier available, see the manual-link requirement below), `dictcc_api` (dict.cc's mobile-app audio backend, real recordings and synthesized voices), kaikki.org (`sounds[].mp3_url`, real recordings), and filmot.com (manual-link fallback — no free tier available, see the manual-link requirement below). piper is explicitly excluded from this change. ElevenLabs was implemented and live-tested as a synthesis provider in `add-elevenlabs-provider`, then unregistered after live testing found its free tier 402s synthesizing with any voice this adapter can reach — it is not part of the provider set.

#### Scenario: No local synthesis fallback
- **WHEN** no configured provider has audio for the requested input
- **THEN** the system returns the provider's failure rather than falling back to a local synthesis engine

#### Scenario: dictcc_api returns both a recording and a synthesized candidate
- **WHEN** `provider=dictcc_api` is used for a word that dict.cc has both a human recording and a synthesized voice for
- **THEN** the response's `candidates` array contains one entry per source, each tagged with a `source` of `human` or `synthetic` (and, for synthetic candidates, the `voice` used)

### Requirement: Manual-link response for providers with no accessible API
Providers with no free or otherwise accessible API (`forvo`, `filmot`) SHALL NOT be called over HTTP. Instead, `POST /tts` for these providers SHALL return `{provider, candidates: [], url}`, where `url` is a link to that provider's own website with the requested word/phrase and language pre-filled, for the caller to open and check manually. This is not an error — `candidates: []` combined with a present `url` is this adapter type's normal, successful response.

#### Scenario: Forvo manual link
- **WHEN** `provider=forvo` is used with a given `text`/`lang`
- **THEN** the response is `{provider: "forvo", candidates: [], url}`, where `url` opens Forvo's page for that word/language

#### Scenario: filmot manual link
- **WHEN** `provider=filmot` is used with a given `text`/`lang`
- **THEN** the response is `{provider: "filmot", candidates: [], url}`, where `url` opens filmot's caption search pre-filled with that phrase/language

#### Scenario: Manual-link responses are cacheable like any other result
- **WHEN** the same `(forvo|filmot, text, lang)` request repeats
- **THEN** the cached `{candidates: [], url}` response is served, per the `lookup-cache` contract — no repeated URL construction needed, since the URL is deterministic from the input

### Requirement: Audio bytes served by content hash
The system SHALL expose `GET /tts/{sha256}` returning the raw audio bytes for a previously created clip, independent of the `lookup-cache` metadata-only `GET /<kind>/{id}` contract.

#### Scenario: Fetching generated audio
- **WHEN** `GET /tts/{sha256}` is called with a hash returned by a prior `POST /tts`
- **THEN** the system returns the audio bytes with an appropriate audio `Content-Type`

### Requirement: smia's audio cache is private, not canonical
Per the ecosystem's audio ownership rule, smia's `/tts` cache SHALL be treated as a private optimization, not a store of record. Callers (e.g. stabbur) that need durable audio SHALL copy bytes into their own canonical storage rather than relying on smia's cache long-term.

#### Scenario: smia cache eviction does not affect canonical storage
- **WHEN** smia evicts or loses a cached clip
- **THEN** no other service's canonical audio is affected, because canonical copies live elsewhere
