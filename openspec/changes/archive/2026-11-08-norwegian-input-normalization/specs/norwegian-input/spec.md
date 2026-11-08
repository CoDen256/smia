## ADDED Requirements

### Requirement: Query preparation produces variants, never a rewritten query
The system SHALL provide one shared Norwegian query-preparation facility that, given a caller-supplied word or phrase, returns an **ordered list of query variants** rather than a single rewritten string. The caller's original string SHALL always be the first variant. Variants SHALL be deduplicated, preserving first occurrence order.

No provider SHALL replace a caller's query with a prepared form. A provider that consumes this facility SHALL query every variant and merge the results, so that no lookup which succeeds against the caller's literal string can be made to fail by query preparation.

Ordering SHALL be most-faithful-to-the-caller first: the as-given string, then case-folded and/or prefix-stripped derivations.

#### Scenario: A single lowercase word yields one variant
- **WHEN** the facility is given `"kalv"`
- **THEN** it returns exactly `["kalv"]`, so a consuming provider performs the same single lookup it performs today

#### Scenario: The caller's original is always queried
- **WHEN** the facility is given any input that produces more than one variant
- **THEN** the first variant is the caller's string unchanged

#### Scenario: Variants are deduplicated
- **WHEN** two preparation steps would produce the same string (e.g. an already-lowercase input that is also case-folded)
- **THEN** that string appears exactly once in the returned list

### Requirement: Norwegian article and infinitive prefixes are stripped into an additional variant
The facility SHALL add a prefix-stripped variant when, and only when, **both** of the following hold:

- the input has two or more whitespace-separated tokens, and
- the first token, compared case-insensitively, is one of `en`, `ei`, `et`, or `å`.

At most one prefix SHALL be stripped per input. The unstripped input SHALL remain in the variant list.

The two-token minimum is normative, not an optimisation: both `å` (a small river) and `en` (juniper) are standalone Norwegian nouns, and a bare one-token input SHALL therefore be left alone.

`en`/`ei`/`et` are indefinite articles and `å` is the infinitive marker; they are covered by one rule because the surface operation is identical, not because they share a part of speech.

#### Scenario: An indefinite noun phrase gains a bare-noun variant
- **WHEN** the facility is given `"en kalv"`
- **THEN** it returns `["en kalv", "kalv"]`

#### Scenario: Each Norwegian gender's article is recognised
- **WHEN** the facility is given `"ei bok"` or `"et hus"`
- **THEN** it returns `["ei bok", "bok"]` and `["et hus", "hus"]` respectively

#### Scenario: An infinitive gains a bare-verb variant
- **WHEN** the facility is given `"å komme"`
- **THEN** it returns `["å komme", "komme"]`

#### Scenario: A bare article or marker is not stripped
- **WHEN** the facility is given `"å"` or `"en"`
- **THEN** it returns exactly `["å"]` / `["en"]`, because each is itself a Norwegian noun and there is no following token

#### Scenario: Only one prefix is stripped
- **WHEN** the facility is given `"en å"`
- **THEN** it returns `["en å", "å"]` and does not continue stripping

#### Scenario: A phrase whose first token is not a recognised prefix is unchanged
- **WHEN** the facility is given `"god morgen"`
- **THEN** it returns exactly `["god morgen"]`

#### Scenario: Part of speech is not consulted
- **WHEN** the facility is given any qualifying input
- **THEN** the stripped variant is produced from the surface form alone, without requiring or inferring a part of speech — no request contract in this service carries one

### Requirement: Case folding is additive and never replaces the caller's casing
The facility SHALL add a lowercased variant when it differs from the input, and SHALL NOT substitute it for the input. Case folding and prefix stripping SHALL compose, producing the cross product of both operations with the as-given form first in each dimension.

This is normative because the configured lexicons genuinely contain capitalised headwords — proper nouns and abbreviations — so a lookup that only ever queried a lowercased form would fail for entries that resolve today.

#### Scenario: A capitalised word keeps its original casing first
- **WHEN** the facility is given `"Kalv"`
- **THEN** it returns `["Kalv", "kalv"]`, in that order

#### Scenario: Case folding and prefix stripping compose
- **WHEN** the facility is given `"En Kalv"`
- **THEN** it returns `["En Kalv", "en kalv", "Kalv", "kalv"]`

#### Scenario: A capitalised headword still resolves
- **WHEN** a provider is asked for a word whose lexicon entry is capitalised (e.g. a place name) and the caller supplied that capitalisation
- **THEN** the as-given variant matches the entry, and the lowercased variant's failure to match does not suppress it

### Requirement: Phrase tokenization rules
The facility SHALL provide a tokenizer that splits a Norwegian phrase into lookup tokens, for use by endpoints that decompose a phrase into its words. The rules are:

- Split on whitespace.
- Strip leading and trailing punctuation from each token (at minimum `.` `,` `!` `?` `:` `;` and quotation marks and parentheses).
- Hyphens SHALL NOT be split points — a hyphenated compound is one token.
- Digit-only tokens SHALL be dropped.
- Tokens that are empty after punctuation stripping SHALL be dropped.
- The reflexive pronoun `seg` SHALL be treated as an ordinary token and kept; it is a legitimate standalone lookup.

The tokenizer SHALL NOT apply the article/infinitive prefix rule itself. Composing tokenization with prefix stripping is the consuming endpoint's decision.

#### Scenario: A two-word phrase splits into its words
- **WHEN** the tokenizer is given `"god morgen"`
- **THEN** it returns `["god", "morgen"]`

#### Scenario: A hyphenated compound stays whole
- **WHEN** the tokenizer is given `"sju-åtte"`
- **THEN** it returns `["sju-åtte"]`, not `["sju", "åtte"]`

#### Scenario: Digits are dropped
- **WHEN** the tokenizer is given `"klokka 5"`
- **THEN** it returns `["klokka"]`

#### Scenario: The reflexive is kept
- **WHEN** the tokenizer is given `"anstrenge seg"`
- **THEN** it returns `["anstrenge", "seg"]`

#### Scenario: Trailing punctuation is stripped
- **WHEN** the tokenizer is given `"god morgen!"`
- **THEN** it returns `["god", "morgen"]`

#### Scenario: Tokenization does not strip prefixes
- **WHEN** the tokenizer is given `"en kalv"`
- **THEN** it returns `["en", "kalv"]` — the prefix rule is a separate, caller-chosen step

### Requirement: Providers merge across variants using their own result identity
A provider consuming the variant list SHALL deduplicate merged results using that provider's established notion of result identity, and SHALL NOT introduce a separate fuzzy-matching or similarity step. Results from different variants that are genuinely different entries SHALL all survive as separate candidates, consistent with this service's rule that a provider returns candidates rather than picking one answer.

For a provider whose lookup already fans out over several datasets, the variant list SHALL cross that fan-out, and the provider's existing partial-failure rule SHALL carry over unchanged: one failing combination contributes no candidates, and the lookup fails only if every combination fails.

#### Scenario: Variants resolving to the same entry collapse
- **WHEN** both the as-given and the prefix-stripped variant resolve to the same entry at a provider
- **THEN** that entry appears once in `candidates`, not twice

#### Scenario: Variants resolving to different entries both survive
- **WHEN** a provider has an entry for `"en gang"` and a different entry for `"gang"`
- **THEN** both appear as separate candidates and the system does not choose between them

#### Scenario: Variant fan-out crosses dataset fan-out
- **WHEN** a provider that already queries several datasets per lookup is given a two-variant input
- **THEN** it queries each (dataset, variant) combination

#### Scenario: One variant's failure does not fail the lookup
- **WHEN** one (dataset, variant) combination fails with a provider error while another succeeds
- **THEN** the successful combination's candidates are returned rather than the whole lookup failing

#### Scenario: All combinations failing fails the lookup
- **WHEN** every (dataset, variant) combination fails with a provider error
- **THEN** the lookup raises a provider error, as it does today for a single failing lookup

### Requirement: Query preparation does not affect cache identity
Query preparation SHALL happen below the lookup cache, leaving the cache key as the hash of the caller's raw input. Two requests differing only in a prefix or in casing SHALL therefore remain distinct cache entries with distinct resource ids, even when they resolve to identical payloads.

This keeps the caller's actual request recoverable from its resource id, consistent with the service's rule that every response records what was asked and which provider answered.

#### Scenario: Citation form and bare lemma are distinct resources
- **WHEN** a caller requests `"en kalv"` and another requests `"kalv"` for the same kind and provider
- **THEN** the two receive different resource ids, each resolvable via `GET /<kind>/{id}`, even though their payloads match

#### Scenario: Preparation is invisible to the request contract
- **WHEN** query preparation is applied for any kind
- **THEN** the request and response shapes for that kind are unchanged
