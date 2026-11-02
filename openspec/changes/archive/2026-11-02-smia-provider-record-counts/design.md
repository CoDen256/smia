## Context

`registry.py`'s `ProviderRegistry.register(kind, name, adapter, *, available=None)`
already has a precedent for "a zero-arg callable, re-checked on every
listing/resolution, that can change a provider's catalog visibility without a
code change or restart" — `available` for credential-gated providers (e.g.
`elevenlabs`, `deepl`). A record count is the same shape of fact for
data-gated providers: the number of rows actually doesn't change the
provider's *availability* (resolve_provider still routes to it; a 0-row
provider just returns "no entry" for everything), it changes whether an
operator should bother trying it.

Table-backed providers and the table(s) each one's count should reflect
(confirmed by reading each adapter):
- `inflections`/`ordbank` → `ordbank_fullform` (the reverse-lookup surface the
  adapter actually queries against; `ordbank_lemma`/`ordbank_paradigme`/
  `ordbank_boying` are joined-in detail, not independently meaningful counts)
- `inflections`/`kaikki`, `ipa`/`kaikki` (`kaikki_ipa.py`), `tts`/`kaikki`
  (`kaikki_tts.py`) → all three share `kaikki_entry` (one import, three
  adapters reading different columns, per `db/models.py`'s `KaikkiEntry`
  docstring) — same count source registered three times, once per
  `(kind, "kaikki")` pair
- `ipa`/`nst` → `nst_lexicon` (the table `adapters/nst.py` actually queries)
- `ipa`/`ipadict` → `ipa_dict_entry`
- `ipa`/`wikipron` → `wikipron_entry`
- `translations`/`dictcc_static` → `dictcc_static_entry`

Everything else (`dictcc_api`, `deepl`, `google_translate`, `bing_translate`,
`libretranslate`, `elevenlabs`, `hf_whisper`, `ordbokene`, `forvo`, `filmot`)
answers from a live call or a pure URL function — there is no table to count,
and no count field is reported for them.

## Goals / Non-Goals

**Goals:**
- `GET /providers` reports a count for every table-backed provider, computed
  live (not cached/stale) so it reflects the current state of an import job.
- `/ui`'s catalog table shows the count and greys out zero-count rows,
  without removing them from the list.
- Adding a count source is as low-friction as adding `available=` already is
  — one extra keyword at the existing `registry.register()` call site.

**Non-Goals:**
- No change to `resolve_provider`/`providers_for`'s availability semantics —
  a 0-count provider is still "available" and still selectable by an
  explicit `provider=` request; this is purely a display signal.
- No caching of the count — these are cheap `SELECT count(*)` queries against
  small, rarely-changing import tables; add caching only if `/providers`
  latency actually becomes a problem.
- No change to stabbur's enrichment panel — it consumes the same
  `GET /providers` but this change doesn't touch it (separate change if/when
  needed).

## Decisions

### D1 — `register()` gains an optional `count` callable, parallel to `available`
```python
registry.register("inflections", "ordbank", OrdbankAdapter(),
                   count=lambda db: db.scalar(select(func.count()).select_from(OrdbankFullform)))
```
Rejected alternative: a separate registry method (`register_count(kind, name,
fn)`) — splits one provider's registration across two call sites for no
benefit; keeping it alongside `available` at the same `registry.register()`
call matches the existing pattern exactly.

The callable takes the active `db` session (counts need a query, unlike
`available`'s plain env-var check) and returns `int | None` — `None` means
"not table-backed, omit the field" (the default when `count` isn't passed).

### D2 — Count is computed per request, not cached on the registry
`providers_for()` already re-checks `available()` on every call; `counts_for()`
(new method) does the same for `count()`. These tables only change when an
operator re-runs an import script, which is rare and manual — a live query
per `/providers` call is simpler than inventing an invalidation story for a
cache that buys almost nothing here.

### D3 — Three `kaikki` registrations share one count function, not three separate ones
`kaikki.py`, `kaikki_ipa.py`, `kaikki_tts.py` each call `registry.register()`
independently (current code, one per kind). Each passes the same
`_kaikki_entry_count` function (defined once, e.g. in `adapters/kaikki.py`
and imported by the other two, or duplicated as a 3-line function in each —
decide at implementation time based on which reads cleaner; either is
correct since it's the same trivial query against the same table).

### D4 — Response shape: `counts` is a sibling map, not inlined into the provider-name list
```json
{
  "inflections": ["kaikki", "ordbank"],
  "ipa": ["kaikki", "nst", "ipadict", "wikipron"],
  ...
}
```
becomes
```json
{
  "inflections": ["kaikki", "ordbank"],
  "ipa": ["kaikki", "nst", "ipadict", "wikipron"],
  ...,
  "counts": {
    "inflections": {"ordbank": 123456, "kaikki": 45000},
    "ipa": {"kaikki": 45000, "nst": 89000, "ipadict": 12000, "wikipron": 3000}
  }
}
```
Rejected alternative: turning each provider-name list entry into an object
(`{"name": "ordbank", "count": 123456}`) — breaks every existing consumer
that does `names.join(", ")` or `.includes(name)` on the plain string list
(smia's own `ui.js`, stabbur's `smia_client.py`/`ui.js`). A sibling `counts`
map is purely additive: old consumers ignore it, `renderCatalog` reads it
when present.

## Risks / Trade-offs

- **[Risk]** A `COUNT(*)` on `ordbank_fullform` (hundreds of thousands of
  rows per `OrdbankFullform`'s docstring) on every `/providers` call adds
  latency. → **Mitigation**: these are simple, index-free full-table counts
  on Postgres tables that only grow via a one-time import; acceptable for an
  operator-facing catalog endpoint that isn't on any hot path. Revisit with
  a cached/materialized count only if this is measured as a real problem.
- **[Trade-off]** Zero-count providers still appear in the catalog response
  and in `/ui` (greyed, not hidden) rather than being filtered out. Accepted:
  hiding a configured provider entirely reads as "this was removed," which
  is actively misleading when it's really "not imported yet" — greying out
  preserves the distinction operators actually need.

## Migration Plan

- Additive only: new `count` parameter (optional, defaults to `None`), new
  `counts` key in the `/providers` response. No existing field changes
  shape or meaning.
- Rollback is reverting the registry/adapter/`app.py`/`ui.js` changes; no
  data migration involved.

## Open Questions

- None outstanding — table/count mapping was confirmed by reading each
  adapter rather than assumed.
