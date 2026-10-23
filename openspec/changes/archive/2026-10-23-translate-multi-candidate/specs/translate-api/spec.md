## MODIFIED Requirements

### Requirement: Translation lookup returns multiple candidates
`POST /translations` SHALL accept `{text, from, to, provider}` and return `{provider, candidates: [{text, context?}]}`, calling only the named provider. A provider that distinguishes more than one sense/meaning for the input SHALL return one candidate per distinct sense rather than collapsing them into one string or picking one. Nothing a provider returns is discarded: every sense/candidate the provider's raw response actually contains reaches the caller.

#### Scenario: Single-sense provider response
- **WHEN** the named provider returns only one translation with no sense distinction (e.g. DeepL, or Bing via the `translators` package)
- **THEN** the response's `candidates` array contains exactly one entry

#### Scenario: Multi-sense provider response
- **WHEN** the named provider's raw data distinguishes multiple senses for the input (e.g. Norwegian `igjen` meaning both "again" and "back"/"left")
- **THEN** the response's `candidates` array contains one entry per distinct sense

#### Scenario: Same-sense alternatives are joined, not split
- **WHEN** a provider ties more than one translation to the same sense/context (e.g. "back" and "left" both tagged under the same sense)
- **THEN** those translations are joined into a single candidate's `text` with `/` (e.g. `back/left`), not returned as separate candidates

### Requirement: Context field for meaning-specific information
Each candidate's optional `context` field SHALL describe the sense/meaning that candidate's `text` applies to (e.g. a dictionary domain tag, part-of-speech label, or sense gloss), and SHALL be present only when the provider supplies that information for that specific candidate.

#### Scenario: Candidate with contextual meaning data
- **WHEN** a provider ties sense/domain information to a specific group of translations (e.g. Google's part-of-speech-grouped dictionary entries, dict.cc's `[zool.]`-style domain tags)
- **THEN** that candidate's `context` field describes the applicable meaning

#### Scenario: Candidate with no contextual data
- **WHEN** a provider supplies a translation with no accompanying sense/domain information
- **THEN** that candidate omits `context` rather than returning it empty or null
