## ADDED Requirements

### Requirement: lexin translation provider
`/translations` SHALL be backed additionally by `lexin`, a live call against LEXIN's findwords API (lexin.oslomet.no), supporting exactly two pairs: `nb→nb` (LEXIN's plain-Norwegian definition of the entry) and `nb→en` (LEXIN's English dictionary). Any other `(from, to)` pair SHALL fail as an unsupported pair, the same way `dictcc_static` does, and SHALL NOT return an empty result.

For `nb→nb`, each candidate SHALL be one distinct non-empty definition of one entry: `text` is the definition and `context` is the entry's headword followed by its part of speech (`avlyse, verb`), with the part of speech omitted when the source has none. For `nb→en`, each candidate SHALL be one English entry: `text` is the English headword and `context` is its part of speech and English definition (`noun: the end part of an arm`), omitting whichever is absent and omitting `context` when both are. Entries LEXIN returns because they merely contain or inflect to the query SHALL NOT be filtered out; their headword in `context` (`nb→nb`) is what distinguishes them.

A lookup that LEXIN refuses (an error body in an otherwise successful HTTP response) SHALL be a provider failure, never an empty `candidates` array.

#### Scenario: nb→nb returns the learner definition with the headword in context
- **WHEN** `provider=lexin`, `from=nb`, `to=nb` is used for `avlyse`
- **THEN** a candidate has `text` `innstille, stanse, stoppe, skrinlegge` and `context` `avlyse, verb`

#### Scenario: nb→nb keeps fuzzy matches and labels them by headword
- **WHEN** `provider=lexin`, `from=nb`, `to=nb` is used for a word that LEXIN also matches inside other entries' text
- **THEN** those entries' definitions are returned as candidates, each with its own headword in `context`

#### Scenario: nb→en disambiguates same-headword senses by definition
- **WHEN** `provider=lexin`, `from=nb`, `to=en` is used for `hånd`
- **THEN** the response contains separate candidates with `text` `hand` whose `context` values carry different English definitions

#### Scenario: Unsupported pair
- **WHEN** `provider=lexin` is used with `from=nb`, `to=de`
- **THEN** the request fails as an unsupported pair and no candidates are returned

#### Scenario: Upstream refusal is a failure
- **WHEN** LEXIN answers a lookup with `{"err": "Access denied", "error_exist": true}`
- **THEN** the lookup fails as a provider error and the result is not cached as an empty answer

#### Scenario: Requests are paced
- **WHEN** two uncached `lexin` lookups arrive within the configured minimum interval
- **THEN** the second request to LEXIN is delayed until the interval has elapsed
