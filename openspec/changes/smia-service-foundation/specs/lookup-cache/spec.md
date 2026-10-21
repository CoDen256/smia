## ADDED Requirements

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

#### Scenario: Named provider fails
- **WHEN** the provider named in a request errors, times out, or returns no answer
- **THEN** the system returns that failure to the caller and does not invoke any other provider

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
