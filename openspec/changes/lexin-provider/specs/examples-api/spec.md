## ADDED Requirements

### Requirement: lexin examples provider
`/examples` SHALL be backed additionally by `lexin`, a dictionary provider: a live call against LEXIN's findwords API (lexin.oslomet.no) returning the example sentences a lexicographer filed under each returned entry, in the order LEXIN returns them, with no ranking. Each candidate SHALL be `{text, sense?}` where `sense` is that entry's definition, omitted when the entry has none; an entry without a definition still contributes its examples. Entries LEXIN returns because they merely contain the query SHALL NOT be filtered out. Identical `(text, sense)` pairs SHALL be collapsed, `limit` SHALL default to 3, and no candidate SHALL carry a translation. Only `lang=nb` is supported; any other `lang` SHALL return no candidates.

A lookup LEXIN refuses (an error body in an otherwise successful HTTP response) SHALL be a provider failure, never an empty `candidates` array.

#### Scenario: Examples carry the entry's definition as sense
- **WHEN** `provider=lexin` is used for `avlyse`
- **THEN** a candidate has `text` `konserten ble avlyst` and `sense` `innstille, stanse, stoppe, skrinlegge`

#### Scenario: Source order is preserved
- **WHEN** `provider=lexin` returns examples from several entries
- **THEN** the candidates appear in LEXIN's response order, not re-ranked

#### Scenario: Upstream refusal is a failure
- **WHEN** LEXIN answers with `{"err": "Access denied", "error_exist": true}`
- **THEN** the lookup fails as a provider error and is not cached as an empty answer
