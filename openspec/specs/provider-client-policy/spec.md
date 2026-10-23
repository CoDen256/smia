## Purpose

Policy for when a provider adapter uses a maintained official client library
versus raw HTTP requests, and how that choice is justified in code. (TBD:
expand with cross-links to provider-catalog once that capability references
this policy explicitly.)

## Requirements

### Requirement: Use a maintained official client library when one legitimately exists
Where a provider publishes and actively maintains an official client library for the exact endpoint an adapter calls, that adapter SHALL use it instead of hand-rolled HTTP requests. This applies to the current `hf_whisper` (Hugging Face) and `deepl` (DeepL) adapters, and to any future adapter for a provider with a legitimate official client (e.g. ElevenLabs).

#### Scenario: Official client exists
- **WHEN** an adapter calls a provider that publishes a maintained official client library for that exact endpoint
- **THEN** the adapter uses that library rather than raw HTTP requests

### Requirement: Raw HTTP is the correct choice when no legitimate client exists
Adapters calling an unofficial, undocumented, reverse-engineered, or scrape-based endpoint SHALL continue using raw HTTP, and SHALL document (in the adapter's module docstring) why no official client applies — distinguishing "no client exists for this exact endpoint" from "a client exists for a different, unrelated product by the same vendor."

#### Scenario: No official client for the actual endpoint
- **WHEN** an adapter calls an endpoint with no vendor-maintained client (e.g. Google Translate's unofficial `translate_a/single`, Bing's undocumented edge-auth exchange, dict.cc's mobile-app backend)
- **THEN** the adapter uses raw HTTP and its docstring records that no legitimate client exists for that specific endpoint

#### Scenario: A client exists but for a different product
- **WHEN** a vendor publishes an official SDK for a different, paid/documented product than the one an adapter actually calls (e.g. Google Cloud Translate vs. the unofficial `translate_a/single` endpoint)
- **THEN** the adapter does not adopt that unrelated SDK, and its docstring records the distinction
