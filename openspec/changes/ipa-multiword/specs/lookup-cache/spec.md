## MODIFIED Requirements

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

## ADDED Requirements

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
