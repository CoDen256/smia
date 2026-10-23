## Purpose

`POST /translations` looks up a translation for a single named provider, following the `lookup-cache` contract. Absorbs hover-translate's `TranslatorFactory`.

## Requirements

### Requirement: Translation lookup returns multiple candidates
`POST /translations` SHALL accept `{text, from, to, provider}` and return `{provider, candidates: [{text, context?}]}`, calling only the named provider. A provider that distinguishes more than one sense/meaning for the input SHALL return one candidate per distinct sense rather than collapsing them into one string or picking one. Nothing a provider returns is discarded: every sense/candidate the provider's raw response actually contains reaches the caller. The response SHALL NOT include a `lang` field (the caller already specifies `to`) and SHALL NOT include transliteration or source-language transcription fields.

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

### Requirement: Provider set
`/translations` SHALL be backed by: Google Translate (scrape, ported from `TranslatorFactory`, raw HTTP against the documented internal shape — deliberately not swapped to a wrapper library, to preserve the structured sense/dictionary data it parses), Bing (implemented via the `translators` package rather than a custom scrape), DeepL (official API, via the official `deepl` client), `dictcc_api` (dict.cc's mobile-app backend), and `dictcc_static` (a local import of dict.cc's `NO-EN`/`NO-DE`/`DE-EN` vocabulary dumps). LibreTranslate is not part of the provider set — dropped as unreliable in practice (public mirrors down/blocking, the official instance requiring a paid key) with no legitimate maintained client available to make calling it easier.

#### Scenario: Bing via the translators package
- **WHEN** `provider=bing` is used
- **THEN** the system calls the `translators` package's Bing engine rather than a custom edge-auth-token exchange, and returns its translation

#### Scenario: dictcc_api as a translation provider
- **WHEN** `provider=dictcc_api` is used
- **THEN** the system calls dict.cc's `app_translations.php` backend and returns its translation for the pair, including `context` built from the entry's domain/type tags (e.g. `[zool.]`) when present

#### Scenario: dictcc_static as a translation provider
- **WHEN** `provider=dictcc_static` is used for a language pair covered by the imported dumps (`NO-EN`, `NO-DE`, `DE-EN`)
- **THEN** the system returns the matching lemma-pair translation from the local import, with `context` built from the dataset's part-of-speech/domain-tag columns when present

#### Scenario: dictcc_static has no live-network dependency
- **WHEN** `provider=dictcc_static` is used
- **THEN** the system answers entirely from the local import, with no outbound network call to dict.cc

#### Scenario: libretranslate is no longer a valid provider
- **WHEN** `provider=libretranslate` is requested
- **THEN** the system responds the same as for any other unregistered provider name (unknown-provider error listing the currently available providers), not a special "removed" message
