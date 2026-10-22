## MODIFIED Requirements

### Requirement: Provider set
`/inflections` SHALL be backed by three providers: `ordbank` (the Norsk Ordbank import — primary, matches the paradigm shape directly, full coverage), `kaikki` (the kaikki.org/Wiktionary dump's `forms[]` field, secondary), and `dictcc_api` (dict.cc's mobile-app `inflections_repl` field, secondary, best-effort). Because more than one provider is configured, `provider` is a required request field per the `lookup-cache` contract.

The `kaikki` provider's candidates SHALL exclude any form tagged `imperative` or `passive` — only forms that map onto the paradigm shapes defined in this capability are surfaced.

The `dictcc_api` provider's coverage is best-effort: dict.cc only returns an inflection table for some entries/word classes, unlike `ordbank`'s full paradigm coverage. Where dict.cc does return a table, its slots map directly onto the existing paradigm shapes (e.g. a `NOUN` table's `indefinite.sg | definite.sg | indefinite.pl | definite.pl` maps onto `substantiv {article, sg_indef, sg_def, pl_indef, pl_def}`).

#### Scenario: kaikki candidate excludes imperative/passive forms
- **WHEN** `provider=kaikki` is used for a verb whose `forms[]` includes entries tagged `imperative` or `passive`
- **THEN** those entries are not included in the resulting `paradigm`

#### Scenario: dictcc_api returns a paradigm when dict.cc has an inflection table
- **WHEN** `provider=dictcc_api` is used for a word dict.cc has inflection data for (e.g. a noun)
- **THEN** the response's `candidates` includes a candidate whose `paradigm` is built from dict.cc's inflection table, using the existing per-POS shapes

#### Scenario: dictcc_api has no inflection table for an entry
- **WHEN** `provider=dictcc_api` is used for a word dict.cc has a translation for but no inflection table
- **THEN** the system returns `{provider, candidates: []}` rather than an error
