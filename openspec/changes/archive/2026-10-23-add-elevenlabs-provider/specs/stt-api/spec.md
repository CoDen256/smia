## MODIFIED Requirements

### Requirement: Provider set
`/stt` SHALL be backed by two providers: `hf_whisper` (Hugging Face Inference running whisper, ported from `phonexa/js/shadow.js`'s `transcribeViaHuggingFace` logic) and `elevenlabs` (ElevenLabs' speech-to-text endpoint, implemented via the official ElevenLabs SDK). `provider` remains required on every request regardless of how many providers are configured, per this capability's existing required-provider rule.

#### Scenario: hf_whisper selected
- **WHEN** `provider=hf_whisper` is used
- **THEN** the system calls Hugging Face's Inference API and returns its transcription

#### Scenario: elevenlabs selected
- **WHEN** `provider=elevenlabs` is used
- **THEN** the system calls ElevenLabs' speech-to-text endpoint via the official SDK and returns its transcription
