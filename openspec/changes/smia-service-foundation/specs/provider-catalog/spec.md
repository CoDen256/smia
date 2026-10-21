## ADDED Requirements

### Requirement: Provider catalog is discoverable
The system SHALL expose `GET /providers` returning, for every kind (`inflect`, `ipa`, `tts`, `translate`, `stt`), the list of currently configured provider names. This is the source callers (hover-translate, stabbur, `/ui`) use to build a provider picker — the catalog is declarative config, not a computed ranking.

#### Scenario: Catalog reflects configuration
- **WHEN** `GET /providers` is called
- **THEN** the response lists every provider currently registered per kind, with no implied order or preference

### Requirement: Provider health is observable
The system SHALL expose `GET /health` returning, per provider, its last-success timestamp, last-failure timestamp (if any), and any known quota/rate-limit state. This SHALL NOT influence which provider a request uses — it is informational only, for `/ui` and for callers deciding where to route a request.

#### Scenario: Healthy provider
- **WHEN** a provider has recently answered successfully
- **THEN** `/health` reflects a recent last-success timestamp for it

#### Scenario: Flaky/scrape-based provider
- **WHEN** a provider (e.g. a scrape-based source) has been failing
- **THEN** `/health` reflects its last-failure timestamp without smia automatically routing around it

### Requirement: Manual try-it bypasses cache
`/ui` SHALL be able to invoke any registered provider directly for a manual test, bypassing the cache so a stale or missing cache entry does not hide whether the provider itself is currently working.

#### Scenario: Forced fresh call
- **WHEN** an operator uses `/ui`'s manual try-it against a provider that already has a cached answer for the same input
- **THEN** the system calls the provider again rather than returning the cached result, and updates the cache with the fresh result
