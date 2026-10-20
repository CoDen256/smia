# CLAUDE.md

## smia — part of the Tun ecosystem

The **linguistics** service: `/inflect`, `/ipa`, `/tts`, `/stt`, `/translate`,
plus a `/ui` for provider health and manual try-it.

**Cross-repo design, decisions, pitfalls and the roadmap live in
`/home/coden/dev/tun/docs/` — start at `README.md`, then `07-decisions.md`.**
Full service design: `tun/docs/06-smia.md`.

### Hard boundaries (D16, D45)

- **Depends on nothing.** It is a leaf service. hover-translate calls it
  directly; stabbur calls it; neither is a dependency of smia.
- **Stateless with respect to canonical storage.** `/tts` returns bytes. The
  private cache keyed on `(kind, provider, sha256(input))` is an optimisation,
  not a store of record — stabbur owns canonical audio.
- **`/inflect` returns candidates, never one answer.** Norwegian surface forms
  are ambiguous (`skinner` = verb or noun plural); triage picks.
- Always record **which provider answered**; quality varies a lot (naob is
  phonemic-only and often unavailable, espeak always answers but is mediocre).
- Provider chains are declarative config, not code paths.

## Status

Not implemented.
