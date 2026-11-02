## MODIFIED Requirements

### Requirement: Provider set
`/inflections` SHALL be backed by three providers: `ordbank` (the Norsk Ordbank import — primary, matches the paradigm shape directly, full coverage), `kaikki` (the kaikki.org/Wiktionary dump's `forms[]` field, secondary), and `dictcc_api` (dict.cc's mobile-app `inflections_repl` field, secondary, best-effort). Because more than one provider is configured, `provider` is a required request field per the `lookup-cache` contract.

The `kaikki` provider's candidates SHALL exclude any form tagged `imperative` or `passive` — only forms that map onto the paradigm shapes defined in this capability are surfaced.

The `dictcc_api` provider's coverage is best-effort: dict.cc only returns an inflection table for some entries/word classes, unlike `ordbank`'s full paradigm coverage. Where dict.cc does return a table, its slots map directly onto the existing paradigm shapes (e.g. a `NOUN` table's `indefinite.sg | definite.sg | indefinite.pl | definite.pl` maps onto `substantiv {article, sg_indef, sg_def, pl_indef, pl_def}`). Because dict.cc has no monolingual Norwegian dictionary, a `lang=nb` lookup against `dictcc_api` SHALL check both Norwegian-touching dict.cc pairs (NO↔DE and NO↔EN) and merge their results, rather than only the one pair a word happens to be filed under. Identical paradigms from both pairs SHALL be deduplicated into a single candidate.

#### Scenario: kaikki candidate excludes imperative/passive forms
- **WHEN** `provider=kaikki` is used for a verb whose `forms[]` includes entries tagged `imperative` or `passive`
- **THEN** those entries are not included in the resulting `paradigm`

#### Scenario: dictcc_api returns a paradigm when dict.cc has an inflection table
- **WHEN** `provider=dictcc_api` is used for a word dict.cc has inflection data for (e.g. a noun)
- **THEN** the response's `candidates` includes a candidate whose `paradigm` is built from dict.cc's inflection table, using the existing per-POS shapes

#### Scenario: dictcc_api has no inflection table for an entry
- **WHEN** `provider=dictcc_api` is used for a word dict.cc has a translation for but no inflection table
- **THEN** the system returns `{provider, candidates: []}` rather than an error

#### Scenario: A Norwegian word is only in one of dict.cc's two pairs
- **WHEN** `provider=dictcc_api`, `lang=nb` is used for a word that has an inflection table in dict.cc's NO↔EN data but not its NO↔DE data
- **THEN** the response's `candidates` still includes that word's paradigm, sourced from the NO↔EN pair

#### Scenario: A Norwegian word's paradigm is identical in both pairs
- **WHEN** both of dict.cc's Norwegian-touching pairs return the same paradigm for a word
- **THEN** the response's `candidates` includes that paradigm once, not twice

#### Scenario: One pair fails, the other succeeds
- **WHEN** `provider=dictcc_api`, `lang=nb` is used and one of the two Norwegian-touching pairs' requests fails (network or parse error) while the other succeeds
- **THEN** the response still includes the successful pair's candidates, rather than the whole request failing
