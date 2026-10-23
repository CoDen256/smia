## Purpose

`POST /ipa` looks up phonemic/phonetic pronunciation for Norwegian text, following the `lookup-cache` contract. Returns one candidate per pronunciation variety when a provider has dialect/flavour data, rather than picking one.

## Requirements

### Requirement: Pronunciation lookup returns multiple variety candidates
`POST /ipa` SHALL accept `{text, lang, provider}` (`lang` defaults to `nb` — only Norwegian Bokmål is supported initially) and return `{provider, candidates: [{ipa, variety?}]}`, calling only the named provider per the `lookup-cache` no-fallback rule. Every candidate's transcription is under the single field `ipa`, regardless of whether the source provider calls it a phonemic or phonetic rendering — that distinction isn't surfaced to callers. A provider that has pronunciation data for more than one dialect/flavour SHALL return one candidate per variety rather than picking one.

#### Scenario: Dialect-aware provider
- **WHEN** the named provider has pronunciation data for multiple dialect regions (e.g. the NST lexicon)
- **THEN** the response's `candidates` array contains one entry per dialect, each tagged with its `variety`

#### Scenario: Single-variety provider
- **WHEN** the named provider has only one pronunciation per word (no dialect data)
- **THEN** the response's `candidates` array contains exactly one entry, with a provider-defined default `variety`

### Requirement: Provider set
`/ipa` SHALL be backed by: the NST NOFABET lexicon (local, multi-dialect), the kaikki.org dump (`sounds[].ipa`), the ordbokene.no API (`body.pronunciation`), ipa-dict/nb, and wikipron's bundled data. espeak-ng (grapheme-to-phoneme) is explicitly excluded — every configured provider is a real pronunciation lookup, not a synthesized approximation.

#### Scenario: No g2p fallback
- **WHEN** no configured provider has an entry for the requested `text`
- **THEN** the system returns `{provider, candidates: []}` rather than falling back to a g2p engine
