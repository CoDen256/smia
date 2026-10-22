## MODIFIED Requirements

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (real recordings), `dictcc_api` (dict.cc's mobile-app audio backend, real recordings and synthesized voices), kaikki.org (`sounds[].mp3_url`, real recordings), filmot.com (locates a real spoken instance in YouTube captions and slices that audio), and `elevenlabs` (ElevenLabs free tier, synthesis, implemented via the official ElevenLabs SDK). piper is explicitly excluded from this change.

#### Scenario: No local synthesis fallback
- **WHEN** no configured provider has audio for the requested input
- **THEN** the system returns the provider's failure rather than falling back to a local synthesis engine

#### Scenario: dictcc_api returns both a recording and a synthesized candidate
- **WHEN** `provider=dictcc_api` is used for a word that dict.cc has both a human recording and a synthesized voice for
- **THEN** the response's `candidates` array contains one entry per source, each tagged with a `source` of `human` or `synthetic` (and, for synthetic candidates, the `voice` used)

#### Scenario: elevenlabs provider selected
- **WHEN** `provider=elevenlabs` is used
- **THEN** the system calls ElevenLabs' text-to-speech endpoint via the official SDK and returns one or more candidates with `sha256` and available voice metadata (e.g. `gender`, `voice`)
