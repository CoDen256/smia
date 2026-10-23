## Purpose

`POST /stt` transcribes audio to text via a cloud-only provider, following the `lookup-cache` contract. Absorbs phonexa's Shadowing STT config. Self-hosting whisper was judged too heavy for the deployment box (D17), so the interface is cloud-only but left open for future providers.

## Requirements

### Requirement: Cloud-only speech-to-text with required provider
`POST /stt` SHALL accept an audio payload and `{provider}` (required, even though only one provider is configured today — this is an explicit exception to `lookup-cache`'s single-provider-default rule, to keep the contract stable as more providers are added), and SHALL only ever call a cloud-hosted provider. The system SHALL NOT run or depend on a locally-hosted speech recognition model, per the decision that self-hosting whisper is too heavy for the deployment box.

#### Scenario: Provider omitted
- **WHEN** `/stt` is called without a `provider`
- **THEN** the system rejects the request with a 4xx error, even though only one provider is currently configured

#### Scenario: Interface stays open for future providers
- **WHEN** a second cloud (or eventually local) STT provider is registered
- **THEN** `/stt` accepts `provider` to select it, with no change to the request/response contract

### Requirement: Provider set
`/stt` SHALL be backed by two providers: `hf_whisper` (Hugging Face Inference running whisper, ported from `phonexa/js/shadow.js`'s `transcribeViaHuggingFace` logic) and `elevenlabs` (ElevenLabs' speech-to-text endpoint, implemented via the official ElevenLabs SDK). `provider` remains required on every request regardless of how many providers are configured, per this capability's existing required-provider rule.

#### Scenario: hf_whisper selected
- **WHEN** `provider=hf_whisper` is used
- **THEN** the system calls Hugging Face's Inference API and returns its transcription

#### Scenario: elevenlabs selected
- **WHEN** `provider=elevenlabs` is used
- **THEN** the system calls ElevenLabs' speech-to-text endpoint via the official SDK and returns its transcription

### Requirement: Transcription response
`POST /stt` SHALL return at minimum `{provider, text}`. Segment-level timestamps are not required in this change.

#### Scenario: Basic transcription
- **WHEN** the named provider successfully transcribes the submitted audio
- **THEN** the response contains `provider` and `text`

#### Scenario: No speech detected
- **WHEN** the named provider returns an empty transcription
- **THEN** the response contains `provider` and an empty `text`, not an error
