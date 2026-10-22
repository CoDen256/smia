## MODIFIED Requirements

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (real recordings), `dictcc_api` (dict.cc's mobile-app audio backend, real recordings and synthesized voices), kaikki.org (`sounds[].mp3_url`, real recordings), filmot.com (locates a real spoken instance in YouTube captions and slices that audio), and ElevenLabs free tier (synthesis). piper is explicitly excluded from this change.

#### Scenario: No local synthesis fallback
- **WHEN** no configured provider has audio for the requested input
- **THEN** the system returns the provider's failure rather than falling back to a local synthesis engine

#### Scenario: dictcc_api returns both a recording and a synthesized candidate
- **WHEN** `provider=dictcc_api` is used for a word that dict.cc has both a human recording and a synthesized voice for
- **THEN** the response's `candidates` array contains one entry per source, each tagged with a `source` of `human` or `synthetic` (and, for synthetic candidates, the `voice` used)

### Requirement: Audio lookup/synthesis returns multiple candidates
`POST /tts` SHALL accept `{text, lang, provider}` (no `voice` field) and return `{provider, candidates: [{sha256, ...metadata}]}`, calling only the named provider. A provider that has more than one recording/rendering available for the input (e.g. multiple speakers) SHALL return one candidate per recording rather than picking one. Metadata fields (e.g. `gender`, `source`, `voice`) are present when the provider supplies them.

#### Scenario: Synthesized provider
- **WHEN** the named provider is a synthesis engine (e.g. ElevenLabs free tier)
- **THEN** the system generates audio from `text`, stores it, and returns one or more candidates with `sha256` and available voice metadata (e.g. `gender`)

#### Scenario: Recorded-speech provider with multiple speakers
- **WHEN** the named provider has multiple real recordings for the same input (e.g. Forvo, `dictcc_api`)
- **THEN** the response's `candidates` array contains one entry per recording, each with its own `sha256`

#### Scenario: Recorded-speech provider with one match
- **WHEN** the named provider locates exactly one real recording (e.g. a filmot-located YouTube clip)
- **THEN** the response's `candidates` array contains exactly one entry
