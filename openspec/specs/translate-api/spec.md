## Purpose

`POST /translations` looks up a translation for a single named provider, following the `lookup-cache` contract. Absorbs hover-translate's `TranslatorFactory`.

## Requirements

### Requirement: Translation lookup for a single named provider
`POST /translations` SHALL accept `{text, from, to, provider}` and return `{provider, text}` at minimum, calling only the named provider. The response SHALL NOT include a `lang` field (the caller already specifies `to`) and SHALL NOT include transliteration or source-language transcription fields.

#### Scenario: Minimal provider response
- **WHEN** the named provider returns only translated text (e.g. DeepL, LibreTranslate)
- **THEN** the response contains exactly `provider` and `text`

### Requirement: Context field for meaning-specific information
Providers that return sense/meaning-specific information alongside the translation (e.g. dictionary-style entries disambiguating which meaning was translated) SHALL have that information surfaced as an optional `context` field, present only when the provider supplies it.

#### Scenario: Provider with contextual meaning data
- **WHEN** the named provider returns meaning-specific entries alongside the translation (e.g. the scraped Google Translate endpoint, or dict.cc)
- **THEN** the response includes a `context` field describing the applicable meaning(s), in addition to `provider, text`

#### Scenario: Plain provider response
- **WHEN** the named provider does not supply meaning-specific data
- **THEN** the `context` field is omitted rather than returned empty or null

### Requirement: Provider set
`/translations` SHALL be backed by: Google Translate (scrape, ported from `TranslatorFactory`), Bing (scrape, ported from `TranslatorFactory`), DeepL (official API), LibreTranslate (API), `dictcc_api` (dict.cc's mobile-app backend), and `dictcc_static` (a local import of dict.cc's `NO-EN`/`NO-DE`/`DE-EN` vocabulary dumps).

#### Scenario: dictcc_api as a translation provider
- **WHEN** `provider=dictcc_api` is used
- **THEN** the system calls dict.cc's `app_translations.php` backend and returns its translation for the pair, including `context` built from the entry's domain/type tags (e.g. `[zool.]`) when present

#### Scenario: dictcc_static as a translation provider
- **WHEN** `provider=dictcc_static` is used for a language pair covered by the imported dumps (`NO-EN`, `NO-DE`, `DE-EN`)
- **THEN** the system returns the matching lemma-pair translation from the local import, with `context` built from the dataset's part-of-speech/domain-tag columns when present

#### Scenario: dictcc_static has no live-network dependency
- **WHEN** `provider=dictcc_static` is used
- **THEN** the system answers entirely from the local import, with no outbound network call to dict.cc
