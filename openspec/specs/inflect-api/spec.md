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

### Requirement: Citation-form input resolves against every inflections provider
`POST /inflections` SHALL resolve a `lang=nb` word supplied in Norwegian citation form — an indefinite article plus noun (`en kalv`, `ei bok`, `et hus`) or the infinitive marker plus verb (`å komme`) — against every configured provider, not only the bare lemma. Each provider SHALL apply the `norwegian-input` capability's query-variant rules and merge the results, deduplicating by that provider's existing `(lemma, pos, paradigm)` identity.

Because the unstripped input remains among the queried variants, a word whose dictionary entry legitimately includes the article SHALL still resolve, and where both the article-bearing entry and the bare entry exist, both SHALL be returned as separate candidates rather than the system choosing between them.

The request and response shapes of `POST /inflections` are unchanged.

#### Scenario: An indefinite noun phrase resolves to the noun's paradigm
- **WHEN** `POST /inflections` is called with `{word: "en kalv", lang: "nb"}` and any configured provider
- **THEN** the response's `candidates` contains the paradigm for `kalv`, rather than being empty

#### Scenario: An infinitive resolves to the verb's paradigm
- **WHEN** `POST /inflections` is called with `{word: "å komme", lang: "nb"}` and any configured provider
- **THEN** the response's `candidates` contains the paradigm for `komme`, rather than being empty

#### Scenario: ordbank resolves citation form
- **WHEN** `provider=ordbank` is used with `{word: "et hus", lang: "nb"}`
- **THEN** the local Norsk Ordbank lookup matches `hus` and returns its `substantiv` paradigm

#### Scenario: kaikki resolves citation form
- **WHEN** `provider=kaikki` is used with `{word: "ei bok", lang: "nb"}`
- **THEN** the kaikki entry for `bok` is matched and its paradigm returned

#### Scenario: dictcc_api crosses variants with its language pairs
- **WHEN** `provider=dictcc_api`, `lang=nb` is used with `{word: "en kalv"}`
- **THEN** each of dict.cc's two Norwegian-touching pairs is queried with both the as-given and the prefix-stripped variant, and the resulting paradigms are merged and deduplicated by `(pos, paradigm)`

#### Scenario: A phrase whose article belongs to the entry is not lost
- **WHEN** a provider has an entry filed under a phrase beginning with an indefinite article (e.g. `"en gang"`) and the caller supplies that phrase
- **THEN** that entry's candidate is present in the response, because the unstripped variant is queried

#### Scenario: Both the phrase entry and the bare-word entry survive
- **WHEN** a provider has distinct entries for both the article-bearing phrase and the bare word
- **THEN** both appear as separate candidates and the system does not pick one

#### Scenario: A capitalised word is not lowercased away
- **WHEN** `POST /inflections` is called with a capitalised word whose provider entry is also capitalised
- **THEN** the as-given variant matches that entry and its candidate is returned

#### Scenario: A single lowercase word behaves exactly as before
- **WHEN** `POST /inflections` is called with a single already-lowercase word
- **THEN** the provider performs the same lookups it performed before this change, and the response is unchanged
