## ADDED Requirements

### Requirement: lexin pronunciation provider
`/ipa` SHALL be backed additionally by `lexin`, a live call against LEXIN's findwords API (lexin.oslomet.no), reading each entry's pronunciation field. As with `ordbokene`, the value is LEXIN's own stress-marked respelling (`'a:vly:se`), not IPA symbols, and SHALL be surfaced under `ipa` unchanged.

Because an `/ipa` candidate carries no headword, only entries for the requested word SHALL contribute: an entry whose headword (compound markers removed, casefolded) or any token of whose inflection string equals the casefolded query. Entries LEXIN returns only because they contain the query SHALL NOT contribute their pronunciation. Identical transcriptions SHALL be collapsed in first-seen order, and a candidate SHALL carry no field beyond those this capability already defines. Only `lang=nb` is supported; any other `lang` SHALL return no candidates.

A lookup LEXIN refuses (an error body in an otherwise successful HTTP response) SHALL be a provider failure, never an empty `candidates` array.

#### Scenario: Headword match
- **WHEN** `provider=lexin` is used for `avlyse`
- **THEN** the candidates contain `{"ipa": "'a:vly:se"}`

#### Scenario: Inflected form matches through the inflection string
- **WHEN** `provider=lexin` is used for `skinner`
- **THEN** the candidates contain the pronunciation of the entries whose inflection string contains `skinner`, and not the pronunciation of unrelated entries LEXIN also returned (e.g. `jernbane`)

#### Scenario: Unknown word
- **WHEN** `provider=lexin` is used for a word LEXIN has no entry for
- **THEN** the response is `{provider, candidates: []}` and the request succeeds

#### Scenario: Upstream refusal is a failure
- **WHEN** LEXIN answers with `{"err": "Access denied", "error_exist": true}`
- **THEN** the lookup fails as a provider error and is not cached as an empty answer
