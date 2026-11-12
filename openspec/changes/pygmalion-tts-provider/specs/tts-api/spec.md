## MODIFIED Requirements

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (manual-link fallback — no free tier available, see the manual-link requirement below), `dictcc_api` (dict.cc's mobile-app audio backend, real recordings and synthesized voices), kaikki.org (`sounds[].mp3_url`, real recordings), `pygmalion` (NTNU Pygmalion/LearnNoW human recordings in several Norwegian dialects, served from a local table), and filmot.com (manual-link fallback — no free tier available, see the manual-link requirement below). piper is explicitly excluded from this change. ElevenLabs was implemented and live-tested as a synthesis provider in `add-elevenlabs-provider`, then unregistered after live testing found its free tier 402s synthesizing with any voice this adapter can reach — it is not part of the provider set.

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

#### Scenario: pygmalion is a listed provider
- **WHEN** `GET /providers` is called after the pygmalion recordings have been imported
- **THEN** the `tts` kind lists `pygmalion` and reports its current recording count, per the `provider-catalog` capability

## ADDED Requirements

### Requirement: Pygmalion dialect recordings
`POST /tts` with `provider=pygmalion` and `lang=nb` SHALL look up the casefolded, whitespace-trimmed `text` as an exact match against the imported Pygmalion recording table, and SHALL return one candidate per recording of that word across all dialects. Each candidate SHALL be `{sha256, source: "human", voice}`, where `voice` is the speaker's dialect area (e.g. `Oslo`, `Bergen`, `Sandnessjøen`). The provider SHALL reuse the existing candidate metadata fields and SHALL NOT introduce any new field. Candidates SHALL be ordered with `Oslo` first, then the remaining dialects alphabetically, then by recording order within a dialect, and SHALL be deduplicated by `sha256`. The provider SHALL NOT apply the `norwegian-input` query-variant fan-out or any inflection or fuzzy matching. A word with no recording SHALL yield `{provider, candidates: []}`, which is a successful response and not an error. A `lang` other than `nb` SHALL yield `candidates: []`.

The audio bytes SHALL be stored in smia's private audio cache and served by `GET /tts/{sha256}`, and the provider's source data SHALL be loaded from the committed Pygmalion manifest at startup only when its table is empty.

#### Scenario: A word with recordings in several dialects
- **WHEN** `POST /tts` is called with `{text: "led", lang: "nb", provider: "pygmalion"}` and the data holds two Oslo recordings and one Bergen recording of `led`
- **THEN** the response's `candidates` contains three entries, each with `source: "human"` and a `sha256`, the two Oslo entries with `voice: "Oslo"` first and the Bergen entry with `voice: "Bergen"` after

#### Scenario: Multiple recordings in one dialect are all returned
- **WHEN** a word has two recordings in the Oslo dialect
- **THEN** both are returned as separate candidates in recording order, rather than one being picked

#### Scenario: The dialect appears under voice and no new field is added
- **WHEN** any candidate is returned by `pygmalion`
- **THEN** its keys are a subset of `sha256`, `source` and `voice`, and the dialect name is the value of `voice`

#### Scenario: Matching ignores case and surrounding whitespace
- **WHEN** `POST /tts` is called with `{text: "  Led ", lang: "nb", provider: "pygmalion"}`
- **THEN** the response contains the same candidates as for `led`

#### Scenario: Phrases match only as exact entries
- **WHEN** `POST /tts` is called with `{text: "la du", lang: "nb", provider: "pygmalion"}` and the data holds that exact phrase
- **THEN** the response contains that phrase's recordings, and `la deg` — which is not in the data — yields `candidates: []`

#### Scenario: Unknown word yields an empty, successful response
- **WHEN** `POST /tts` is called with a word the Pygmalion data does not contain
- **THEN** the response is `{provider: "pygmalion", candidates: []}` with no error

#### Scenario: Non-Norwegian language yields no candidates
- **WHEN** `POST /tts` is called with `provider=pygmalion` and `lang` other than `nb`
- **THEN** the response's `candidates` is empty

#### Scenario: No citation-form fan-out
- **WHEN** `POST /tts` is called with `{text: "en kalv", lang: "nb", provider: "pygmalion"}`
- **THEN** the provider matches the text `en kalv` exactly and does not retry the bare noun `kalv`

#### Scenario: Returned audio is retrievable
- **WHEN** a `sha256` returned by `pygmalion` is requested with `GET /tts/{sha256}`
- **THEN** the system returns the recording's bytes with an `audio/mpeg` `Content-Type`

#### Scenario: Import runs only on an empty table
- **WHEN** smia starts and the Pygmalion table already contains rows
- **THEN** the import is skipped, and when the table is empty the manifest's `status: "ok"` rows are imported

#### Scenario: Import rejects a corrupted file
- **WHEN** a manifest row's file hashes to a value other than the row's recorded `sha256`
- **THEN** that row is skipped and counted, and nothing for it enters the audio cache or the table

#### Scenario: Missing manifest does not stop startup
- **WHEN** the manifest file is absent at startup
- **THEN** startup continues with a warning, and the provider returns empty candidate lists
