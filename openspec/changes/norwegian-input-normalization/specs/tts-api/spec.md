## ADDED Requirements

### Requirement: Citation-form input resolves against the dict.cc audio provider
`POST /tts` SHALL resolve a `lang=nb` input supplied in Norwegian citation form — an indefinite article plus noun (`en kalv`, `ei bok`, `et hus`) or the infinitive marker plus verb (`å komme`) — against the `dictcc_api` provider, not only the bare lemma. The provider SHALL apply the `norwegian-input` capability's query-variant rules, crossing the variant list with the two Norwegian-touching dict.cc pairs it already queries, and SHALL deduplicate the merged audio candidates by `sha256` as it does today.

Because audio candidates are deduplicated by content hash, a recording reachable through more than one (pair, variant) combination SHALL appear exactly once.

The request and response shapes of `POST /tts`, and the behaviour of `GET /tts/{sha256}`, are unchanged.

#### Scenario: An indefinite noun phrase returns the noun's audio
- **WHEN** `POST /tts` is called with `{text: "en kalv", lang: "nb"}` and `provider=dictcc_api`
- **THEN** the response's `candidates` contains the recordings dict.cc has for `kalv`, rather than being empty

#### Scenario: An infinitive returns the verb's audio
- **WHEN** `POST /tts` is called with `{text: "å komme", lang: "nb"}` and `provider=dictcc_api`
- **THEN** the response's `candidates` contains the recordings dict.cc has for `komme`, rather than being empty

#### Scenario: Variants cross the existing pair fan-out
- **WHEN** `provider=dictcc_api`, `lang=nb` is used with a two-variant input
- **THEN** each (pair, variant) combination is queried for its entry id and audio

#### Scenario: The same recording reached twice appears once
- **WHEN** two (pair, variant) combinations resolve to byte-identical audio
- **THEN** the response's `candidates` includes that recording once, identified by its `sha256`

#### Scenario: One combination failing does not fail the lookup
- **WHEN** one (pair, variant) combination's request fails while another succeeds
- **THEN** the successful combination's candidates are returned rather than the whole request failing

#### Scenario: Every combination failing fails the lookup
- **WHEN** every (pair, variant) combination's request fails
- **THEN** the lookup returns the provider's failure, as it does today

#### Scenario: A single lowercase word behaves exactly as before
- **WHEN** `POST /tts` is called with a single already-lowercase Norwegian word
- **THEN** `dictcc_api` makes the same requests it made before this change, and the response is unchanged

#### Scenario: Other audio providers are unaffected
- **WHEN** a provider other than `dictcc_api` is used
- **THEN** it receives the caller's text unchanged, with no variant fan-out
