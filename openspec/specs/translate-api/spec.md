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

### Requirement: Citation-form input resolves against the dict.cc translation providers
`POST /translations` SHALL resolve Norwegian text supplied in citation form — an indefinite article plus noun (`en kalv`, `ei bok`, `et hus`) or the infinitive marker plus verb (`å komme`) — against the `dictcc_api` and `dictcc_static` providers, not only the bare lemma. Both SHALL apply the `norwegian-input` capability's query-variant rules and merge the results, deduplicating by each provider's existing grouping key (`(entry_type, source_phrase)` for `dictcc_api`, `(pos, tags)` for `dictcc_static`).

This requirement applies where Norwegian is the **source** language of the pair. The live machine-translation providers (`google`, `bing`, `deepl`) are unaffected: they translate arbitrary text rather than matching a dictionary headword, so an article-bearing phrase already translates correctly and query preparation would change their input without benefit.

No English or German article stripping is specified. `dictcc_api` serves `en` and `de` as source languages, but only their Norwegian-touching side matters to this service and the equivalent surface rules for those languages are not established here.

The request and response shapes of `POST /translations` are unchanged.

#### Scenario: An indefinite noun phrase translates via dictcc_static
- **WHEN** `POST /translations` is called with `{text: "et hus", from: "nb", to: "en"}` and `provider=dictcc_static`
- **THEN** the response's `candidates` contains the translations filed under `hus`, rather than being empty

#### Scenario: An infinitive translates via dictcc_api
- **WHEN** `POST /translations` is called with `{text: "å komme", from: "nb", to: "de"}` and `provider=dictcc_api`
- **THEN** the response's `candidates` contains the translations filed under `komme`, rather than being empty

#### Scenario: dictcc_static queries all variants in one statement
- **WHEN** `provider=dictcc_static` is used with a two-variant Norwegian input
- **THEN** the local lookup matches any of the variants without issuing one query per variant

#### Scenario: A phrase whose article belongs to the entry is not lost
- **WHEN** dict.cc has an entry filed under an article-bearing phrase (e.g. `"en gang"` = *once*) and the caller supplies that phrase
- **THEN** that entry's candidate is present in the response, because the unstripped variant is queried

#### Scenario: Both the phrase entry and the bare-word entry survive
- **WHEN** dict.cc has distinct entries for both the article-bearing phrase and the bare word
- **THEN** both appear as separate candidates, each carrying its own `context`, and the system does not pick one

#### Scenario: The context field still reflects what actually matched
- **WHEN** a candidate is produced from a prefix-stripped variant
- **THEN** its `context` is built from the source phrase dict.cc actually matched, so the caller can see which form answered

#### Scenario: Machine-translation providers are unaffected
- **WHEN** `provider=google`, `provider=bing` or `provider=deepl` is used with an article-bearing Norwegian phrase
- **THEN** the provider receives the caller's text unchanged, with no variant fan-out

#### Scenario: Norwegian as the target language is unaffected
- **WHEN** Norwegian is the `to` language rather than the `from` language
- **THEN** no Norwegian query preparation is applied, since the queried text is not Norwegian
