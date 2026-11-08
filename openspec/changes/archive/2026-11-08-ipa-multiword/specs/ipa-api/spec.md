## MODIFIED Requirements

### Requirement: Pronunciation lookup returns multiple variety candidates
`POST /ipa` SHALL accept `{text, lang, provider}` (`lang` defaults to `nb` — only Norwegian Bokmål is supported initially) and return a response carrying a `mode` field discriminating how the transcription was obtained, calling only the named provider per the `lookup-cache` no-fallback rule. Every candidate's transcription is under the single field `ipa`, regardless of whether the source provider calls it a phonemic or phonetic rendering — that distinction isn't surfaced to callers. A provider that has pronunciation data for more than one dialect/flavour SHALL return one candidate per **distinct transcription**, not one per variety: candidates that share an identical `ipa` value SHALL be merged into a single candidate, rather than appearing as separate, duplicate-sounding rows.

Merging works as follows: when two or more candidates share the same `ipa` and at least one carries a `variety`, they collapse into one candidate whose `variety` is every one of their varieties joined with `/`, in first-seen order. When candidates share the same `ipa` and none carries a `variety`, they simply dedupe to one candidate with no `variety` key.

For a single-word request, and for a multi-word request the named provider has a whole-phrase entry for, the response SHALL be `{provider, mode: "phrase", candidates: [{ipa, variety?}]}` — the `candidates` shape this capability has always returned, with `mode` added.

For a multi-word request the named provider has no whole-phrase entry for, the response SHALL be `{provider, mode: "per_word", tokens: [{text, candidates: [{ipa, variety?}]}], joined?}`, as specified in the multi-word requirements below.

#### Scenario: Dialect-aware provider
- **WHEN** the named provider has pronunciation data for multiple dialect regions (e.g. the NST lexicon)
- **THEN** the response's `candidates` array contains one entry per *distinct* transcription, each tagged with a `variety` naming every dialect that shares it (joined with `/` when more than one)

#### Scenario: Identical transcriptions across varieties merge
- **WHEN** two or more of a provider's dialect varieties produce byte-identical `ipa` transcriptions for the same word
- **THEN** those varieties collapse into a single candidate whose `variety` lists all of them joined with `/`, rather than appearing as separate candidates with the same `ipa`

#### Scenario: Duplicate candidates with no variety dedupe
- **WHEN** a provider's lookup yields two or more candidates sharing the same `ipa` and none of them carries a `variety`
- **THEN** the response's `candidates` array contains that `ipa` exactly once, with no `variety` key

#### Scenario: Single-variety provider
- **WHEN** the named provider has only one pronunciation per word (no dialect data)
- **THEN** the response's `candidates` array contains exactly one entry, with a provider-defined default `variety`

#### Scenario: Single-word request is unchanged apart from `mode`
- **WHEN** `POST /ipa` is called with a single-word `text`
- **THEN** the response is `mode: "phrase"` with the same `candidates` array this capability returned before multi-word support, and no `tokens` key

#### Scenario: Single word with no entry still returns an empty candidate list
- **WHEN** `POST /ipa` is called with a single word the named provider has no entry for
- **THEN** the response is `{provider, mode: "phrase", candidates: []}` and the system does not attempt a per-word split

### Requirement: Provider set
`/ipa` SHALL be backed by: the NST NOFABET lexicon (local, multi-dialect), the kaikki.org dump (`sounds[].ipa`), the ordbokene.no API (`body.pronunciation`), ipa-dict/nb, and wikipron's bundled data. espeak-ng (grapheme-to-phoneme) is explicitly excluded — every configured provider is a real pronunciation lookup, not a synthesized approximation.

Every provider's adapter matches a single wordform. Multi-word support is implemented above the provider layer (whole-phrase attempt, then per-token lookup), so no provider is required to handle phrases, and a provider that happens to hold multi-word entries is served by the whole-phrase attempt without special-casing.

#### Scenario: No g2p fallback
- **WHEN** no configured provider has an entry for the requested `text`
- **THEN** the system returns `{provider, candidates: []}` rather than falling back to a g2p engine

#### Scenario: Multi-word support requires no adapter change
- **WHEN** a new `/ipa` provider is added with a single-wordform lookup
- **THEN** it gains whole-phrase and per-word behaviour without implementing either, because both live above the adapter layer

## ADDED Requirements

### Requirement: Multi-word input is tried as a phrase before being split
`POST /ipa` SHALL attempt the caller's whole `text` against the named provider first, and SHALL return `mode: "phrase"` when that provider has an entry for it. Only when the whole-phrase attempt yields no candidates SHALL the system tokenize the input and look each token up against the same provider.

A provider *error* (network, parse, or other provider failure) during the whole-phrase attempt SHALL NOT trigger a split. The error SHALL be returned to the caller as it is for any other lookup, so a broken provider looks broken rather than silently degrading into a different response shape.

The whole-phrase attempt SHALL apply the `norwegian-input` capability's query variants to the full input before tokenizing anything, so that an input differing from a provider's entry only by a leading `en`/`ei`/`et`/`å` resolves as a phrase rather than being split.

#### Scenario: Provider has the phrase
- **WHEN** `POST /ipa` is called with a multi-word `text` the named provider holds as a single entry (e.g. `av og til` in ipa-dict/nb)
- **THEN** the response is `mode: "phrase"` with that entry's transcription in `candidates`, and no split is performed

#### Scenario: Provider lacks the phrase
- **WHEN** `POST /ipa` is called with a multi-word `text` the named provider has no whole-phrase entry for
- **THEN** the system tokenizes the input and returns `mode: "per_word"`

#### Scenario: Provider error does not cause a split
- **WHEN** the named provider raises an error during the whole-phrase attempt
- **THEN** the system returns that failure to the caller and does not attempt a per-word lookup

#### Scenario: A citation-form phrase resolves as a phrase, not a split
- **WHEN** `POST /ipa` is called with `{text: "en kalv"}` and the named provider has an entry for `kalv`
- **THEN** the response is `mode: "phrase"` carrying `kalv`'s transcription, rather than a per-word breakdown containing a transcription for the article

### Requirement: Per-word responses report one token entry per token, including gaps
A `mode: "per_word"` response SHALL contain a `tokens` array with exactly one entry per token produced by the `norwegian-input` capability's tokenizer, in input order. Each entry SHALL carry `text` (the token as looked up) and `candidates` (that token's transcription candidates, in the same shape as a phrase response's candidates).

A token the provider has no entry for SHALL be present with `candidates: []`. It SHALL NOT be omitted from the array, and SHALL NOT cause the request to fail — consistent with this capability's existing rule that a missing entry is an empty result, not an error.

Tokenization SHALL follow the `norwegian-input` rules: hyphenated compounds stay whole, digit-only tokens are dropped before lookup, and `seg` is kept as a legitimate standalone token.

#### Scenario: Every token resolves
- **WHEN** a two-word phrase is split and the provider has an entry for both words
- **THEN** `tokens` has two entries, each with a non-empty `candidates` array

#### Scenario: A token has no entry
- **WHEN** a phrase is split and the provider has no entry for one of its words
- **THEN** that token is present in `tokens` with `candidates: []`, in its input position, and the request succeeds

#### Scenario: No token has an entry
- **WHEN** a phrase is split and the provider has no entry for any of its words
- **THEN** the response is `mode: "per_word"` with every token carrying `candidates: []`, rather than an error

#### Scenario: Dialect candidates survive per token
- **WHEN** a phrase is split against a multi-dialect provider (e.g. the NST lexicon)
- **THEN** each token's `candidates` array carries one entry per *distinct* transcription, merged across varieties exactly as a single-word lookup would

#### Scenario: A hyphenated compound is one token
- **WHEN** a phrase containing a hyphenated compound is split
- **THEN** the compound appears as a single token, not as its hyphen-separated parts

#### Scenario: Digits are not looked up
- **WHEN** a phrase containing a digit-only token is split
- **THEN** no token entry is produced for the digits

#### Scenario: The reflexive is looked up on its own
- **WHEN** `{text: "anstrenge seg"}` is split
- **THEN** `tokens` contains an entry for `seg` with whatever candidates the provider has for it

### Requirement: The assembled `joined` string is present only when it requires no choice
A `mode: "per_word"` response SHALL include a `joined` string, being each token's single candidate transcription concatenated in input order separated by single spaces, **if and only if** every token in `tokens` resolved to exactly one candidate.

If any token has zero candidates, or any token has two or more candidates, `joined` SHALL be absent from the response entirely — not null, not an empty string. Its absence is the signal that assembling a phrase transcription requires a choice the system will not make on the caller's behalf.

`joined` SHALL NOT be presented as the phrase's actual pronunciation. It is an assembly of citation forms; the `mode: "per_word"` discriminator on the same response is what records that. This is the single permitted exception to this capability's rule that every returned transcription is a real lookup, and it is bounded by the no-choice condition above — a provider's own multi-word entry, returned under `mode: "phrase"`, remains the only way this capability reports a real phrase transcription.

#### Scenario: Unambiguous assembly
- **WHEN** a phrase is split and every token resolved to exactly one candidate
- **THEN** the response includes `joined` with those transcriptions space-separated in input order

#### Scenario: An ambiguous token suppresses the assembly
- **WHEN** a phrase is split and any token resolved to two or more candidates
- **THEN** `joined` is absent from the response, and the caller is left to choose from each token's candidates

#### Scenario: A missing token suppresses the assembly
- **WHEN** a phrase is split and any token resolved to zero candidates
- **THEN** `joined` is absent from the response

#### Scenario: No winner is ever picked
- **WHEN** `joined` is present
- **THEN** there was exactly one possible assembly, and the system selected among nothing

### Requirement: The split stays within the named provider
Every token lookup in a `mode: "per_word"` response SHALL use the single provider resolved for the request. The system SHALL NOT consult a different provider for a token the named provider lacks, SHALL NOT merge candidates from several providers into one token, and SHALL report exactly one `provider` on the response as it does for every other lookup.

#### Scenario: A gap is not filled by another provider
- **WHEN** a phrase is split and the named provider has no entry for one token, while another configured provider does
- **THEN** that token's `candidates` is empty and the other provider is not called

#### Scenario: One provider on the response
- **WHEN** a `mode: "per_word"` response is returned
- **THEN** it carries a single top-level `provider` naming the provider every token was looked up against
