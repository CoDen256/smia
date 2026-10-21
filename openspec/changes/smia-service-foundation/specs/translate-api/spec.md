## ADDED Requirements

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
`/translations` SHALL be backed by: Google Translate (scrape, ported from `TranslatorFactory`), Bing (scrape, ported from `TranslatorFactory`), DeepL (official API), LibreTranslate (API), and dict.cc.

#### Scenario: dict.cc as a translation provider
- **WHEN** `provider=dict.cc` is used
- **THEN** the system returns dict.cc's translation for the pair, including `context` when dict.cc's entry disambiguates meaning
