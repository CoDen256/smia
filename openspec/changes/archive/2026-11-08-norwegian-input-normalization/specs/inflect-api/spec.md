## ADDED Requirements

### Requirement: Citation-form input resolves against every inflections provider
`POST /inflections` SHALL resolve a `lang=nb` word supplied in Norwegian citation form — an indefinite article plus noun (`en kalv`, `ei bok`, `et hus`) or the infinitive marker plus verb (`å komme`) — against every configured provider, not only the bare lemma. Each provider SHALL apply the `norwegian-input` capability's query-variant rules and merge the results, deduplicating by that provider's existing `(lemma, pos, paradigm)` identity.

Because the unstripped input remains among the queried variants, a word whose dictionary entry legitimately includes the article SHALL still resolve, and where both the article-bearing entry and the bare entry exist, both SHALL be returned as separate candidates rather than the system choosing between them.

The request and response shapes of `POST /inflections` are unchanged.

#### Scenario: An indefinite noun phrase resolves to the noun's paradigm
- **WHEN** `POST /inflections` is called with `{word: "en kalv", lang: "nb"}` and any configured provider
- **THEN** the response's `candidates` contains the paradigm for `kalv`, rather than being empty

#### Scenario: An infinitive resolves to the verb's paradigm
- **WHEN** `POST /inflections` is called with `{word: "å komme", lang: "nb"}` and any configured provider
- **THEN** the response's `candidates` contains the paradigm for `komme`, rather than being empty

#### Scenario: ordbank resolves citation form
- **WHEN** `provider=ordbank` is used with `{word: "et hus", lang: "nb"}`
- **THEN** the local Norsk Ordbank lookup matches `hus` and returns its `substantiv` paradigm

#### Scenario: kaikki resolves citation form
- **WHEN** `provider=kaikki` is used with `{word: "ei bok", lang: "nb"}`
- **THEN** the kaikki entry for `bok` is matched and its paradigm returned

#### Scenario: dictcc_api crosses variants with its language pairs
- **WHEN** `provider=dictcc_api`, `lang=nb` is used with `{word: "en kalv"}`
- **THEN** each of dict.cc's two Norwegian-touching pairs is queried with both the as-given and the prefix-stripped variant, and the resulting paradigms are merged and deduplicated by `(pos, paradigm)`

#### Scenario: A phrase whose article belongs to the entry is not lost
- **WHEN** a provider has an entry filed under a phrase beginning with an indefinite article (e.g. `"en gang"`) and the caller supplies that phrase
- **THEN** that entry's candidate is present in the response, because the unstripped variant is queried

#### Scenario: Both the phrase entry and the bare-word entry survive
- **WHEN** a provider has distinct entries for both the article-bearing phrase and the bare word
- **THEN** both appear as separate candidates and the system does not pick one

#### Scenario: A capitalised word is not lowercased away
- **WHEN** `POST /inflections` is called with a capitalised word whose provider entry is also capitalised
- **THEN** the as-given variant matches that entry and its candidate is returned

#### Scenario: A single lowercase word behaves exactly as before
- **WHEN** `POST /inflections` is called with a single already-lowercase word
- **THEN** the provider performs the same lookups it performed before this change, and the response is unchanged
