## MODIFIED Requirements

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (manual-link fallback — no free tier available, see the manual-link requirement below), `dictcc_api` (dict.cc's mobile-app audio backend, real recordings and synthesized voices), kaikki.org (`sounds[].mp3_url`, real recordings), and filmot.com (manual-link fallback — no free tier available, see the manual-link requirement below). piper is explicitly excluded from this change. ElevenLabs was implemented and live-tested as a synthesis provider in `add-elevenlabs-provider`, then unregistered after live testing found its free tier 402s synthesizing with any voice this adapter can reach — it is not part of the provider set.

Because dict.cc has no monolingual Norwegian dictionary, a `lang=nb` lookup against `dictcc_api` SHALL check both Norwegian-touching dict.cc pairs (NO↔DE and NO↔EN) and merge their audio candidates, rather than only the one pair a word happens to be filed under. Identical recordings (same resulting `sha256`) from both pairs SHALL be deduplicated into a single candidate.

#### Scenario: No local synthesis fallback
- **WHEN** no configured provider has audio for the requested input
- **THEN** the system returns the provider's failure rather than falling back to a local synthesis engine

#### Scenario: dictcc_api returns both a recording and a synthesized candidate
- **WHEN** `provider=dictcc_api` is used for a word that dict.cc has both a human recording and a synthesized voice for
- **THEN** the response's `candidates` array contains one entry per source, each tagged with a `source` of `human` or `synthetic` (and, for synthetic candidates, the `voice` used)

#### Scenario: A Norwegian word's audio is only in one of dict.cc's two pairs
- **WHEN** `provider=dictcc_api`, `lang=nb` is used for a word that has a recording in dict.cc's NO↔EN data but not its NO↔DE data
- **THEN** the response's `candidates` still includes that recording, sourced from the NO↔EN pair

#### Scenario: Both pairs resolve to the same recording
- **WHEN** both of dict.cc's Norwegian-touching pairs resolve to byte-identical audio for a word
- **THEN** the response's `candidates` includes that recording once (by `sha256`), not twice

#### Scenario: One pair fails, the other succeeds
- **WHEN** `provider=dictcc_api`, `lang=nb` is used and one of the two Norwegian-touching pairs' requests fails (network or parse error) while the other succeeds
- **THEN** the response still includes the successful pair's candidates, rather than the whole request failing
