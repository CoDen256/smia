## Purpose

Cross-cutting catalog and health data backing `/ui` and letting callers (hover-translate, stabbur) discover which providers exist per kind. Purely informational — never influences which provider a request actually uses.

## Requirements

### Requirement: Provider catalog is discoverable
The system SHALL expose `GET /providers` returning, for every kind (`inflect`, `ipa`, `tts`, `translate`, `stt`, `examples`), the list of currently configured provider names. This is the source callers (hover-translate, stabbur, `/ui`) use to build a provider picker — the catalog is declarative config, not a computed ranking. For every provider whose answers are backed by a local, importable table, the response SHALL additionally report that provider's current record count, keyed by kind and provider name; providers with no local table (live API calls, manual-link adapters) SHALL omit the count entirely rather than reporting zero or a placeholder.

#### Scenario: Catalog reflects configuration
- **WHEN** `GET /providers` is called
- **THEN** the response lists every provider currently registered per kind, with no implied order or preference

#### Scenario: Table-backed provider reports its record count
- **WHEN** `GET /providers` is called and a provider (e.g. `ordbank`) is backed by an imported table
- **THEN** the response includes that provider's current row count for the relevant kind, computed live rather than from a stale or cached figure

#### Scenario: Live/API-backed provider reports no count
- **WHEN** `GET /providers` is called and a provider (e.g. `deepl`, `forvo`) answers via a live call or a pure URL function with no local table
- **THEN** the response includes no count field for that provider, rather than a zero or null placeholder

#### Scenario: Newly-imported data is reflected without a restart
- **WHEN** an operator runs a `scripts/import_*` job that populates a previously-empty table, then calls `GET /providers` again
- **THEN** the reported count for that provider reflects the newly-imported rows immediately, with no smia restart required

#### Scenario: The examples kind is enumerated
- **WHEN** `GET /providers` is called
- **THEN** the response includes an `examples` entry listing its configured providers

#### Scenario: Corpus-backed example providers report counts
- **WHEN** `GET /providers` is called after the example corpora have been imported
- **THEN** `tatoeba`, `leipzig` and `kaikki` report their current sentence/entry counts under the `examples` kind, while the live-API `ordbokene` provider reports none

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
