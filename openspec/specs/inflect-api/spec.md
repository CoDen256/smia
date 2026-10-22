## Purpose

`POST /inflections` looks up Norwegian inflection candidates for a surface form, following the `lookup-cache` contract. Returns candidates, never a single auto-picked answer, because Norwegian surface forms are often genuinely ambiguous.

## Requirements

### Requirement: Inflection lookup returns candidates, never one answer
`POST /inflections` SHALL accept `{word, lang, provider}` (required: more than one provider is configured — see Requirement: Provider set) and return `{provider, candidates: [{lemma, pos, paradigm}]}`. The system SHALL NOT auto-select a single candidate when a surface form maps to more than one lemma/paradigm; all matches are returned for the caller (stabbur's triage UI) to pick from.

#### Scenario: Ambiguous surface form
- **WHEN** `/inflections` is called with a word that maps to multiple distinct `(lemma, pos)` pairs (e.g. Norwegian `skinner`, which is both a verb and a noun plural)
- **THEN** the response's `candidates` array contains one entry per distinct lemma/pos/paradigm combination

#### Scenario: Unambiguous surface form
- **WHEN** `/inflections` is called with a word that maps to exactly one lemma
- **THEN** the response's `candidates` array contains exactly one entry

#### Scenario: Unknown word
- **WHEN** `/inflections` is called with a word not found by the named provider
- **THEN** the system returns `{provider, candidates: []}` (a valid, cacheable negative result, not an error)

### Requirement: Paradigm shape matches stabbur's storage model
Each candidate's `paradigm` field SHALL use the per-part-of-speech shape already expected by stabbur's item storage: `substantiv {article, sg_indef, sg_def, pl_indef, pl_def}`, `adjektiv {positiv, nøytrum, flertall, komparativ, superlativ}`, `verb {infinitiv, presens, preteritum, perfektum}`, `adverb {form, komparativ?, superlativ?}`, and `{}` for parts of speech with no inflection.

`komparativ`/`superlativ` on `adverb` are present only when the source paradigm itself defines degree inflection (Norsk Ordbank's `adjektiv, adverbtype` paradigm group, e.g. `fort`/`fortere`/`fortest`); plain invariable adverbs (Norsk Ordbank's `adverb` paradigm group) omit them.

#### Scenario: Noun candidate shape
- **WHEN** a candidate's `pos` is `substantiv`
- **THEN** its `paradigm` object has exactly the keys `article, sg_indef, sg_def, pl_indef, pl_def`

#### Scenario: Verb candidate shape
- **WHEN** a candidate's `pos` is `verb`
- **THEN** its `paradigm` object has exactly the keys `infinitiv, presens, preteritum, perfektum`

#### Scenario: Degree-inflecting adverb
- **WHEN** a candidate's `pos` is `adverb` and its source paradigm defines degree inflection
- **THEN** its `paradigm` object includes `form`, `komparativ`, and `superlativ`

#### Scenario: Invariable adverb
- **WHEN** a candidate's `pos` is `adverb` and its source paradigm has no degree inflection
- **THEN** its `paradigm` object includes only `form`

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
