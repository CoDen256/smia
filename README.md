# smia

*Smia: the forge — where raw material gets worked.*

The **linguistics** service of the [Tun](../tun) ecosystem. One place for every
operation of the shape *input in → enriched out, several providers, chain with
fallback, expensive enough to cache*.

## Endpoints

| endpoint | provider chain |
|---|---|
| `POST /inflect` | Norsk ordbank (local import) — returns **candidates**, never one answer |
| `POST /ipa` | naob.no → open-dict-data ipa-lookup/nb → espeak-ng g2p |
| `POST /tts` | Forvo → deno.dict.cc → cloud TTS → piper. Returns **bytes** |
| `POST /stt` | cloud only (self-hosted whisper dropped as too heavy) |
| `POST /translate` | lifted from hover-translate + DeepL / LibreTranslate |
| `GET /ui` | provider health, cache hit rate, quota, manual try-it |

## Design rules

- **Stateless.** `/tts` returns bytes; it never stores canonically. stabbur does.
- **Depends on nothing.** It is a leaf — hover-translate can call it directly.
- Provider chains are **declarative config**, not code paths.
- Everything cached on `(kind, provider, sha256(input))`.
- Responses always record **which provider answered** — quality varies a lot.

## Status

Not implemented. Design: `../tun/docs/06-smia.md`.
