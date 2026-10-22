## MODIFIED Requirements

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
