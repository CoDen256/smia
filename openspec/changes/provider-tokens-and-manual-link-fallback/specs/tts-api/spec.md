## MODIFIED Requirements

### Requirement: Provider set
`/tts` SHALL be backed by: Forvo (manual-link fallback — no free tier available, see the manual-link requirement below), `dictcc_api` (dict.cc's mobile-app audio backend, real recordings and synthesized voices), kaikki.org (`sounds[].mp3_url`, real recordings), filmot.com (manual-link fallback — no free tier available, see the manual-link requirement below), and ElevenLabs free tier (synthesis). piper is explicitly excluded from this change.

#### Scenario: No local synthesis fallback
- **WHEN** no configured provider has audio for the requested input
- **THEN** the system returns the provider's failure rather than falling back to a local synthesis engine

#### Scenario: dictcc_api returns both a recording and a synthesized candidate
- **WHEN** `provider=dictcc_api` is used for a word that dict.cc has both a human recording and a synthesized voice for
- **THEN** the response's `candidates` array contains one entry per source, each tagged with a `source` of `human` or `synthetic` (and, for synthetic candidates, the `voice` used)

### Requirement: Manual-link response for providers with no accessible API
Providers with no free or otherwise accessible API (`forvo`, `filmot`) SHALL NOT be called over HTTP. Instead, `POST /tts` for these providers SHALL return `{provider, candidates: [], url}`, where `url` is a link to that provider's own website with the requested word/phrase and language pre-filled, for the caller to open and check manually. This is not an error — `candidates: []` combined with a present `url` is this adapter type's normal, successful response.

#### Scenario: Forvo manual link
- **WHEN** `provider=forvo` is used with a given `text`/`lang`
- **THEN** the response is `{provider: "forvo", candidates: [], url}`, where `url` opens Forvo's page for that word/language

#### Scenario: filmot manual link
- **WHEN** `provider=filmot` is used with a given `text`/`lang`
- **THEN** the response is `{provider: "filmot", candidates: [], url}`, where `url` opens filmot's caption search pre-filled with that phrase/language

#### Scenario: Manual-link responses are cacheable like any other result
- **WHEN** the same `(forvo|filmot, text, lang)` request repeats
- **THEN** the cached `{candidates: [], url}` response is served, per the `lookup-cache` contract — no repeated URL construction needed, since the URL is deterministic from the input
