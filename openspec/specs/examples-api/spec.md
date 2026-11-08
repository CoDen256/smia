## Purpose

`POST /examples` looks up Norwegian example sentences/phrases for a word, following the `lookup-cache` contract. Fills stabbur's note-editor `context_text`/X-field gap: a short, ranked list of candidates showing a word used in context, with no translation (that's `/translations`' concern). Backed by two dictionary providers (`ordbokene`, `kaikki` — examples filed under a lemma, returned in source order) and two corpus providers (`tatoeba`, `leipzig` — naturally-occurring sentences found via inflected-form expansion and ranked for length/completeness).

## Requirements

### Requirement: Example lookup returns a short ranked candidate list
`POST /examples` SHALL accept `{text, lang, provider, limit?}` (`lang` defaults to `nb`; only Norwegian Bokmål is supported) and return `{provider, candidates: [{text, source?, sense?}]}`, following the `lookup-cache` contract and calling only the named provider.

Each candidate's `text` SHALL be Norwegian example text as the source holds it. A candidate SHALL NOT carry a translation of that text; `/examples` answers "how is this word used in Norwegian", and translation is `/translations`' concern.

`source` SHALL name the sub-source a candidate came from, so a caller can tell which dataset answered. `sense` SHALL carry the meaning a candidate illustrates where the provider attaches its examples to a definition. Either field SHALL be omitted by a provider that has nothing meaningful to report, rather than filled with a placeholder.

`limit` SHALL default to 3 and SHALL be clamped to the range 1–10. It is part of the request's identifying input, so requests differing only in `limit` are distinct cache resources.

A provider with no examples for the requested text SHALL return `{provider, candidates: []}` rather than an error.

#### Scenario: A word with examples
- **WHEN** `POST /examples` is called with `{text: "kalv", lang: "nb"}` and a provider that has examples for it
- **THEN** the response contains at most 3 candidates, each with Norwegian `text`

#### Scenario: Candidates carry no translation
- **WHEN** any provider returns a candidate, including one whose underlying source holds a translation of the example
- **THEN** the candidate contains no translation field, and the source's translation is discarded

#### Scenario: Explicit limit
- **WHEN** `POST /examples` is called with `limit: 10`
- **THEN** at most 10 candidates are returned

#### Scenario: Limit is clamped
- **WHEN** `POST /examples` is called with a `limit` below 1 or above 10
- **THEN** the effective limit is clamped into the 1–10 range rather than rejected

#### Scenario: Limit participates in cache identity
- **WHEN** the same text is requested with `limit: 3` and then with `limit: 10` for the same provider
- **THEN** the two resolve to different resource ids, each retrievable via `GET /examples/{id}` and each returning the payload that its own `POST` returned

#### Scenario: No examples found
- **WHEN** the named provider has no examples for the requested text
- **THEN** the response is `{provider, candidates: []}` and the request succeeds

#### Scenario: Unsupported language
- **WHEN** `POST /examples` is called with a `lang` other than `nb`
- **THEN** the request is rejected with a client error rather than silently answered from Norwegian data

### Requirement: Provider set spans dictionary and corpus sources
`/examples` SHALL be backed by four providers of two distinct kinds:

- **Dictionary providers**, returning examples a lexicographer filed under the lemma: `ordbokene` (a live call against the ordbokene.no article API, reading `example` nodes from each definition) and `kaikki` (the local kaikki.org dump's `senses[].examples[]`).
- **Corpus providers**, returning naturally-occurring sentences that contain the lemma: `tatoeba` (a local import of Tatoeba's Norwegian Bokmål sentence export) and `leipzig` (a local import of the Leipzig Corpora Collection's Norwegian Bokmål corpora).

Because more than one provider is configured, `provider` is a required request field per the `lookup-cache` contract.

No provider SHALL generate example text. Every candidate SHALL be text that exists in the provider's source, consistent with this service's standing rule that providers look things up rather than synthesize.

#### Scenario: Dictionary provider attaches a sense
- **WHEN** `provider=ordbokene` is used for a word whose article has examples under more than one definition
- **THEN** each candidate carries the `sense` of the definition it illustrates

#### Scenario: Corpus provider reports its corpus
- **WHEN** `provider=leipzig` is used
- **THEN** each candidate's `source` names which of that provider's corpora the sentence came from

#### Scenario: No generated examples
- **WHEN** no configured provider has an example for the requested text
- **THEN** the system returns an empty candidate list rather than composing a sentence

### Requirement: The leipzig provider is one provider spanning several corpora
`leipzig` SHALL be a single provider whose data spans its several constituent corpora, returning one candidate per selected sentence tagged with that sentence's `source`, rather than being registered as one provider name per corpus. A single `leipzig` lookup SHALL consider all of its corpora and rank across them together.

This mirrors how a multi-dialect pronunciation provider is registered once and distinguishes its data by a per-candidate tag, rather than as several provider names.

#### Scenario: One provider name
- **WHEN** `GET /providers` is called
- **THEN** `examples` lists `leipzig` once, not one entry per constituent corpus

#### Scenario: Ranking spans corpora
- **WHEN** `provider=leipzig` is used for a word present in more than one of its corpora
- **THEN** the returned candidates may come from different corpora, selected by rank rather than by corpus precedence

### Requirement: Corpus providers match any inflected form of the queried word
A corpus provider SHALL return sentences containing **any** inflected surface form of the queried word, not only the form as typed. Form expansion SHALL be driven by the service's imported Norwegian inflection table, which is authoritative for Norwegian morphology including irregular forms.

The corpus text index SHALL NOT be built with a stemming or stopword-filtering text-search configuration. Both are disqualifying for this capability, as verified against the target database:

- A Norwegian stemmer fails to relate umlaut plurals to their lemma (`bok`/`bøker`, `mann`/`menn`, `hånd`/`hender`, `fot`/`føtter`), so those forms would never be found.
- The Norwegian stopword list removes high-frequency verb forms including `kom`, `var`, `ble`, `hadde` and `er` from the index entirely, which would make it impossible to ever return an example sentence for `komme`, `være`, `bli` or `ha` via its preterite — among the most important words a learner needs.

A word absent from the inflection table SHALL be searched by its surface form alone, returning a narrower result rather than an error.

#### Scenario: Regular inflected forms are matched
- **WHEN** `provider=leipzig` is used with `{text: "kalv"}`
- **THEN** sentences containing `kalven`, `kalver` and `kalvene` are eligible candidates, not only those containing `kalv`

#### Scenario: Irregular plural is matched
- **WHEN** a corpus provider is used with `{text: "bok"}`
- **THEN** sentences containing `bøker` are eligible candidates

#### Scenario: A stopword-listed preterite is matched
- **WHEN** a corpus provider is used with `{text: "komme"}`
- **THEN** sentences containing `kom` are eligible candidates

#### Scenario: An unrelated word is not matched
- **WHEN** a corpus provider is used with `{text: "kalv"}`
- **THEN** a sentence containing only an unrelated similar word (e.g. `kalkun`) is not a candidate

#### Scenario: A word outside the inflection table still answers
- **WHEN** a corpus provider is used with a word the inflection table does not list (e.g. a proper noun or recent loanword)
- **THEN** the lookup matches that surface form alone and returns whatever it finds, rather than failing

### Requirement: Corpus candidates are ranked, and ties are broken without positional bias
Because a corpus query can match tens of thousands of sentences while at most ten are returned, a corpus provider SHALL rank its matches and return the highest-ranked. The ranking SHALL prefer, in descending order of influence:

1. Sentences of a card-usable length, strongly preferring short ones.
2. Sentences that appear syntactically complete — beginning with a capital letter and ending in sentence-final punctuation.
3. Sentences with few capitalised words after the first, which indicate source-specific named entities.
4. Sentences with few or no digits.

A corpus provider SHALL exclude outright any matched sentence that contains a URL, or that contains an internal sentence boundary indicating the line holds more than one sentence.

Ties in rank SHALL be broken deterministically but **without positional bias** — specifically not by source row order. The corpora are approximately alphabetically ordered, so breaking ties by row order produces candidate sets whose sentences all begin with the same letter. Tie-breaking SHALL be a deterministic function of the sentence and the query, so that a repeated request yields the same candidates while exhibiting no alphabetical skew.

Dictionary providers SHALL NOT apply this ranking, returning their examples in source order instead; those examples were selected by a lexicographer and reordering them by length would degrade them.

#### Scenario: Short complete sentences outrank long ones
- **WHEN** a corpus provider matches both a short complete sentence and a long one for the same word
- **THEN** the short one is ranked higher

#### Scenario: Embedded metadata is ranked down
- **WHEN** a matched sentence begins with embedded source metadata such as a date and timestamp
- **THEN** its digit content ranks it below a comparable sentence without digits

#### Scenario: Multi-sentence lines are excluded
- **WHEN** a matched corpus line contains two sentences joined together
- **THEN** it is not returned as a candidate

#### Scenario: URLs are excluded
- **WHEN** a matched corpus line contains a URL
- **THEN** it is not returned as a candidate

#### Scenario: No alphabetical bias in tie-breaking
- **WHEN** a corpus query produces many matches of equal rank
- **THEN** the returned candidates are not all sentences beginning with the same letter

#### Scenario: Ranking is reproducible
- **WHEN** the same query is made twice against the same corpus data
- **THEN** the same candidates are returned in the same order

#### Scenario: Dictionary providers preserve source order
- **WHEN** `provider=ordbokene` or `provider=kaikki` returns several examples
- **THEN** they appear in the order the source lists them, not reordered by length

### Requirement: Dictionary providers resolve source-specific example encodings
`ordbokene` SHALL walk an article's definitions recursively, since example nodes nest inside definition elements, and SHALL resolve the placeholder markers the API uses inside example quotes by substituting the quote's own usage items in order. An example whose placeholder count does not match its available substitutions SHALL be skipped rather than returned with an unresolved placeholder.

`kaikki` SHALL exclude examples that are morphology or derivation illustrations rather than usage examples, since that dump mixes both under the same field.

#### Scenario: Placeholder resolution
- **WHEN** `provider=ordbokene` returns an example whose quote contains a placeholder marker and a corresponding usage item
- **THEN** the candidate's `text` has the placeholder replaced by that item, with no marker character remaining

#### Scenario: Example without a placeholder
- **WHEN** an ordbokene example quote contains no placeholder
- **THEN** its text is returned verbatim

#### Scenario: Unresolvable placeholder is skipped
- **WHEN** an ordbokene example's placeholder count does not match its usage items
- **THEN** that example is omitted rather than returned with a literal marker

#### Scenario: Nested examples are found
- **WHEN** an ordbokene article nests examples inside sub-definitions
- **THEN** those examples are found rather than missed by a shallow scan

#### Scenario: kaikki morphology fragments are excluded
- **WHEN** a kaikki entry's examples include a derivation illustration rather than a sentence
- **THEN** it is not returned as a candidate

#### Scenario: kaikki translations are discarded
- **WHEN** a kaikki example carries a translation field
- **THEN** the candidate contains only the Norwegian text
