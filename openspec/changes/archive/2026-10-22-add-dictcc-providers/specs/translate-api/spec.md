## MODIFIED Requirements

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
