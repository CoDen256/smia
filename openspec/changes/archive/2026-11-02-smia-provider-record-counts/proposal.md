## Why

`GET /providers` lists a provider as "configured" purely from credential/config
presence (the `available` callable passed to `registry.register()`), never
from whether its backing data actually has rows. Several providers are backed
by local import tables (`ordbank`, `kaikki`, `nst`, `ipadict`, `wikipron`,
`dictcc_static`) that are empty whenever the corresponding `scripts/import_*`
job hasn't been run yet — those providers show up in the catalog exactly like
a fully-populated one, and every lookup against them then just silently fails
with "no entry found." The operator has no way to tell, from `/ui` or from
any API response, which configured providers actually have data behind them
versus which are configured-but-empty.

## What Changes

- `GET /providers` gains a per-provider record count for every provider whose
  answers are backed by a local table — `ordbank`, `kaikki` (and its IPA/TTS
  variants), `nst`, `ipadict`, `wikipron`, `dictcc_static`. Live/API-backed
  and manual-link providers (`dictcc_api`, `deepl`, `google_translate`,
  `bing_translate`, `libretranslate`, `elevenlabs`, `hf_whisper`,
  `ordbokene`, `forvo`, `filmot`) have no meaningful row count and carry no
  count field (omitted, not zero).
- `/ui`'s provider catalog table (`ui/ui.js` `renderCatalog`, `ui/index.html`)
  shows each table-backed provider's count next to its name and visually
  de-emphasizes (greys out) any provider whose count is `0` — it still lists
  the provider (an operator seeing it vanish could mistake that for "removed"
  rather than "not yet imported"), just makes the emptiness obvious at a
  glance instead of indistinguishable from a populated provider.

## Capabilities

### Modified Capabilities
- `provider-catalog`: `GET /providers` SHALL additionally report a record
  count for table-backed providers, so callers (and `/ui` itself) can
  distinguish a configured-but-empty provider from a populated one.

## Impact

- `registry.py`: `register()`/`providers_for()` need a way to carry an
  optional "count" source per `(kind, provider)`, alongside the existing
  `available` callable.
- Each table-backed adapter module (`adapters/ordbank.py`, `kaikki.py`,
  `kaikki_ipa.py`, `kaikki_tts.py`, `nst.py`, `ipadict.py`, `wikipron.py`,
  `dictcc_static.py`) registers its count source (a row-count query against
  its own table(s)) at the same `registry.register()` call site that already
  wires up `available`.
- `app.py`'s `GET /providers` handler: response shape gains counts.
- `ui/ui.js` (`renderCatalog`) and `ui/ui.css`: render + grey-out styling for
  zero-count providers.
- `openspec/specs/provider-catalog/spec.md`: new requirement.
- Out of scope: stabbur's enrichment panel (`stabbur/smia_client.py`,
  `stabbur/ui/ui.js`) is a separate consumer of this same `/providers`
  response; it is unaffected by an additive field and is handled, if at all,
  by a separate stabbur-side change.
