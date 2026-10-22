## Purpose

`POST /tts` looks up or synthesizes audio for Norwegian text, following the `lookup-cache` contract. Returns one candidate per available recording/rendering, written into smia's own private content-addressed audio cache (not a canonical store — see ecosystem audio ownership rules).

## Requirements

### Requirement: Audio lookup/synthesis returns multiple candidates
`POST /tts` SHALL accept `{text, lang, provider}` (no `voice` field) and return `{provider, candidates: [{sha256, ...metadata}]}`, calling only the named provider. A provider that has more than one recording/rendering available for the input (e.g. multiple speakers) SHALL return one candidate per recording rather than picking one. Metadata fields (e.g. `gender`) are present when the provider supplies them.

#### Scenario: Synthesized provider
- **WHEN** the named provider is a synthesis engine (e.g. ElevenLabs free tier)
- **THEN** the system generates audio from `text`, stores it, and returns one or more candidates with `sha256` and available voice metadata (e.g. `gender`)

#### Scenario: Recorded-speech provider with multiple speakers
- **WHEN** the named provider has multiple real recordings for the same input (e.g. Forvo, dict.cc)
- **THEN** the response's `candidates` array contains one entry per recording, each with its own `sha256`

#### Scenario: Recorded-speech provider with one match
- **WHEN** the named provider locates exactly one real recording (e.g. a filmot-located YouTube clip)
- **THEN** the response's `candidates` array contains exactly one entry

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (real recordings), dict.cc (real recordings, non-generated), kaikki.org (`sounds[].mp3_url`, real recordings), filmot.com (locates a real spoken instance in YouTube captions and slices that audio), and ElevenLabs free tier (synthesis). piper is explicitly excluded from this change.

#### Scenario: No local synthesis fallback
- **WHEN** no configured provider has audio for the requested input
- **THEN** the system returns the provider's failure rather than falling back to a local synthesis engine

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
