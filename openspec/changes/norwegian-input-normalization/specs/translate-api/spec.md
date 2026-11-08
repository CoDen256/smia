## ADDED Requirements

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
