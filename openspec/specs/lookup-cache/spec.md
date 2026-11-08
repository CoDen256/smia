## Purpose

The shared single-provider execution and content-addressed cache contract every smia lookup endpoint (`/inflections`, `/ipa`, `/tts`, `/translations`, `/stt`) is built on. No endpoint falls back between providers or fans out to several at once — the caller always names exactly one provider, and smia answers from cache or calls that provider once.

## Requirements

### Requirement: Content-addressed cache key
The system SHALL cache every provider lookup result under the key `(kind, provider, sha256(canonicalized input))`, where `kind` is one of `inflect`, `ipa`, `tts`, `translate`, `stt`, and `input` is the request's identifying fields (excluding `provider` itself).

#### Scenario: Identical request hits cache
- **WHEN** a request for a given `(kind, provider, input)` has already been answered and cached
- **THEN** the system returns the cached result without invoking the provider again

#### Scenario: Same input, different provider is a cache miss
- **WHEN** a request repeats an `input` already cached for one provider but names a different provider
- **THEN** the system treats it as a cache miss and invokes the newly-named provider

### Requirement: Exactly one provider per request
The system SHALL require the caller to name exactly one provider per request. If a kind has more than one provider configured, the `provider` field is required and the request is rejected if omitted. If a kind has exactly one provider configured, `provider` is optional and defaults to that provider.

#### Scenario: Provider omitted with multiple candidates configured
- **WHEN** a request for a kind with 2+ configured providers omits the `provider` field
- **THEN** the system rejects the request with a 4xx error naming the available providers

#### Scenario: Provider omitted with exactly one candidate configured
- **WHEN** a request for a kind with exactly one configured provider omits the `provider` field
- **THEN** the system uses that sole provider and proceeds normally

### Requirement: No fallback or fan-out
The system SHALL call at most one provider per request and SHALL NOT retry a different provider on failure, timeout, or empty result. Trying another provider is always a separate, explicit request from the caller.

This requirement constrains **provider** fan-out. One request resolves exactly one provider and every provider invocation it makes uses that provider. It does not forbid an endpoint from invoking its single resolved provider more than once with different inputs where that endpoint's own capability specifies it — for example `/ipa` looking a phrase up and then each of its words up against the same provider, or a provider querying several of its own datasets. What is forbidden in all cases is reaching for a *different* provider because the named one failed, timed out, or returned nothing.

#### Scenario: Named provider fails
- **WHEN** the provider named in a request errors, times out, or returns no answer
- **THEN** the system returns that failure to the caller and does not invoke any other provider

#### Scenario: Empty result does not trigger another provider
- **WHEN** the named provider returns no candidates
- **THEN** the system returns that empty result and does not consult any other provider, even if another configured provider would have answered

#### Scenario: Repeated invocation of the same provider is not fan-out
- **WHEN** an endpoint's capability specifies several lookups against the resolved provider for one request (e.g. `/ipa`'s per-token split)
- **THEN** all of those lookups use the single resolved provider, the response reports that one provider, and the requirement is satisfied

### Requirement: Idempotent creation by content address
A `POST` to a kind's collection SHALL be idempotent: repeating the same `(kind, provider, input)` returns the same resource, identified by `sha256(kind, provider, input)`, whether served from cache or freshly computed.

#### Scenario: Repeated identical POST
- **WHEN** the same request body and provider are POSTed twice
- **THEN** both calls resolve to the same resource id and the second call is served from cache

### Requirement: Fetch cached resource by id
The system SHALL expose `GET /<kind>/{id}` for every kind, returning the cached resource for that id without invoking any provider, and returning 404 if no such id is cached.

#### Scenario: Known id
- **WHEN** `GET /<kind>/{id}` is called with an id that was previously created via `POST`
- **THEN** the system returns the cached resource with no provider call

#### Scenario: Unknown id
- **WHEN** `GET /<kind>/{id}` is called with an id that has never been cached
- **THEN** the system returns 404

### Requirement: Provider provenance recorded
Every cached and returned result SHALL include which provider produced it.

#### Scenario: Response includes provider
- **WHEN** any lookup endpoint returns a result
- **THEN** the response body includes a `provider` field naming the provider that answered

### Requirement: One request may create several cache resources
A request whose endpoint performs several provider lookups SHALL cache each lookup under its own `(kind, provider, sha256(input))` key, and SHALL additionally cache the request's own assembled result under the key derived from the caller's input. Each resulting resource SHALL be independently retrievable via `GET /<kind>/{id}`.

The `Location` header and resource id returned from the `POST` SHALL always be those of the caller's own input, never of an internal sub-lookup.

A sub-lookup's cache entry is an ordinary cache entry: a later request whose input matches it directly SHALL be served from cache without invoking the provider, exactly as for any other cached lookup.

#### Scenario: Sub-lookups become reusable cache entries
- **WHEN** a request is answered by looking up several inputs against the resolved provider
- **THEN** each of those inputs is cached under its own key

#### Scenario: A later direct request reuses a sub-lookup's cache entry
- **WHEN** a subsequent request's input matches an input previously cached as part of another request's sub-lookups
- **THEN** it is served from cache without invoking the provider

#### Scenario: Location names the caller's own resource
- **WHEN** a request that performed several sub-lookups returns
- **THEN** its `Location` header and resource id identify the caller's input, and `GET` on that id returns the assembled result

#### Scenario: Forced refresh propagates to sub-lookups
- **WHEN** a request that performs sub-lookups is made with the force-refresh flag set
- **THEN** each sub-lookup bypasses the cache and re-invokes the provider, as does the assembled result
