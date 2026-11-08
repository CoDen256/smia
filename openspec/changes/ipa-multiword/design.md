## Context

`/ipa` is registered through the generic factory, exactly like
`/inflections` and `/translations`:

```python
# app.py
register_lookup_routes(app, "ipa", _extract_ipa_input)
```

which gives it one `POST` that calls `run_lookup` once and one
`GET /ipa/{id}`. `run_lookup` resolves the provider, hashes the input,
checks `LookupCache`, calls `adapter.lookup(input_dict)` on a miss, stores,
and returns `(payload, resource_id, was_cached)`.

All five adapters are exact single-wordform lookups:

| Adapter | Query | Multi-word entries in its data |
|---|---|---|
| `nst` | `WHERE wordform = :word` (+ dialect table) | unknown (needs the live DB) |
| `ipadict` | `WHERE wordform = :word` | **199** of ~2.3k |
| `wikipron` | `WHERE wordform = :word` | **0** of 2,883 |
| `kaikki_ipa` | `WHERE word = :word` | 775 of 79,403, mostly proper names |
| `ordbokene` | live `?w=<word>` headword search | single-headword by construction |

So the phrase-first branch is real but narrow, and the split branch carries
most traffic.

Two constraints from existing specs shape the response design:

1. **`ipa-api` rejects synthesized approximations.** Its "Provider set"
   requirement states espeak-ng is excluded because "every configured
   provider is a real pronunciation lookup, not a synthesized
   approximation", and its "No g2p fallback" scenario returns empty rather
   than synthesizing. A space-joined concatenation of per-word citation
   forms *is* a synthesized approximation — measurable against this
   service's own data:

   ```
   ipadict has  "av og til"      →  /ɑʋɔtɪl/
   joining      av + og + til    →  /ɑʋ/ /ɔː/ /tɪl/
   ipadict has  "anstrenge seg"  →  /ˈɑnstɾɛŋəsæi/
   joining      anstrenge + seg  →  /ɑnˈstɾɛŋə/ /sɛɡ/
   ```

   Connected speech reduces vowels, drops boundaries and moves stress. Each
   *token's* transcription is a real lookup; the joined string is not.

2. **`ipa-api` and the service's top-level boundary forbid picking a
   winner.** `nst` returns one candidate per dialect variety, so a 3-word
   phrase where each word has 4 varieties has 64 possible joins. Choosing
   one is exactly what the service exists not to do.

Together these mean a flat joined string cannot be the primary response
shape, and that whatever shape is returned must let the caller tell a real
phrase transcription apart from an assembled one.

## Goals / Non-Goals

**Goals:**
- A multi-word `/ipa` request returns usable transcription data instead of a
  silent empty list.
- A real multi-word entry, where the provider has one, is returned as such
  and is distinguishable from an assembled result.
- Per-token ambiguity survives to the caller; nothing is collapsed by
  guessing.
- Existing single-word callers are unaffected, byte for byte.
- Per-word lookups accumulate in the cache and are reused across phrases.

**Non-Goals:**
- No g2p / espeak fallback. A token with no entry stays empty.
- No cross-provider fan-out. The split queries the *same* named provider per
  token; trying another provider remains a separate caller request.
- No adapter changes. The five adapters keep their single-word contract.
- No phrase-level pronunciation modelling (sandhi, stress re-assignment,
  reduction). Out of scope and not derivable from the available data.
- No change to `/ipa`'s request shape. No new request fields — the split is
  automatic on a phrase miss, not opt-in.
- No multi-word handling for other kinds. `/translations` already handles
  phrases natively, and a phrase has no inflection paradigm.

## Decisions

### D1 — The response is a discriminated union on `mode`

```jsonc
// single word, or a provider that HAS the phrase — today's shape plus `mode`
{
  "provider": "ipadict",
  "mode": "phrase",
  "candidates": [{ "ipa": "/ɑʋɔtɪl/" }]
}

// phrase miss → split
{
  "provider": "nst",
  "mode": "per_word",
  "tokens": [
    { "text": "god",    "candidates": [
        { "ipa": "ɡuː",     "variety": "standard" },
        { "ipa": "ɡoː",     "variety": "southwestern_spoken" }] },
    { "text": "morgen", "candidates": [
        { "ipa": "ˈmɔrɡən", "variety": "standard" }] }
  ]
}
```

`mode` is additive for existing callers: a single-word request always yields
`mode: "phrase"` with the same `candidates` array it returns today, so a
client that ignores unknown fields is unaffected.

Rejected — **always `tokens`**, treating a single word as a one-token phrase:
more internally consistent, but it breaks every existing caller
(stabbur's enrichment panel, hover-translate) for the overwhelmingly common
case, and still needs a flag to distinguish a real phrase entry from an
assembled one, so it buys nothing.

Rejected — **flat joined `candidates` only**: the measured inaccuracy above,
plus it requires picking one variety per word. This was the operator's
explicitly rejected option.

### D2 — `joined` appears only when it requires no choice

`joined` is included **iff** every token resolved to exactly one candidate.
Otherwise it is absent entirely (not `null`, not empty).

```
tokens all have exactly 1 candidate   →  "joined": "ɡuː ˈmɔrɡən"
any token has 0 candidates            →  no `joined` key
any token has 2+ candidates           →  no `joined` key
```

This is the whole reason the field is defensible: when it is present, there
was only one possible assembly and no winner was picked; when a choice
exists, the service declines to make it and the field's absence says so.
Candidates are joined with a single space.

Note what `joined` is *not*: it is not claimed to be the phrase's real
pronunciation. The `mode: "per_word"` marker on the same object is what tells
the caller this is assembled from parts. Recorded here because this is the
one place in the service where a derived, non-looked-up string is returned,
and a future reader should see that the `ipa-api` anti-synthesis requirement
was considered and narrowly scoped, not ignored.

### D3 — Gaps are empty token candidate lists, never omissions or errors

A token with no provider entry is present in `tokens` with
`"candidates": []`. It is not dropped from the array and does not fail the
request. This keeps `tokens` positionally aligned with the tokenizer output,
so the caller can see *which* word is missing, and matches the kind's
existing "empty is a normal answer" stance (`ipa-api`'s "No g2p fallback"
scenario returns `candidates: []` rather than erroring).

Per the operator's decision: if there is no entry for a word, skip it —
meaning it contributes nothing to `joined` eligibility beyond suppressing
it (D2), not that the token disappears.

### D4 — The split runs at the route layer, over `run_lookup`, not inside adapters

```
POST /ipa {text: "god morgen"}
   │
   ├─ run_lookup(db, "ipa", provider, {text: "god morgen", lang})
   │     └─ miss, adapter returns candidates: []  →  phrase branch fails
   │
   ├─ tokenize("god morgen") → ["god", "morgen"]
   │
   ├─ run_lookup(db, "ipa", provider, {text: "god",    lang})   ← own cache row
   ├─ run_lookup(db, "ipa", provider, {text: "morgen", lang})   ← own cache row
   │
   └─ assemble → store the per_word payload under the PHRASE's resource id
```

Chosen over an adapter-level decorator wrapping each registered adapter.

Why: each token goes through the ordinary cache runner, so it gets its own
`LookupCache` row and its own resource id. A learner's deck re-uses the same
words constantly, so this compounds — and a token already cached from an
earlier single-word request costs nothing. A decorator would re-query the
lexicon on every phrase request.

Three consequences to accept explicitly:

- **The phrase result is also stored**, under the phrase input's own resource
  id, so `GET /ipa/{id}` and the `Location` header keep working exactly as
  the `lookup-cache` spec requires. One request therefore creates N+1 cache
  rows. This is new behaviour for the cache and is why `lookup-cache` is
  listed as a modified capability.
- **`health.record_request` fires once per token**, because it lives inside
  `run_lookup`. `/ipa`'s counters become token-denominated. Accepted: the
  `provider-catalog`/`health` contract states these counters are
  informational and never influence routing, so skew costs nothing
  functional. Rejected alternative: hoist the health call out of
  `run_lookup` — that touches the shared runner every kind depends on, to fix
  a cosmetic number.
- **`forceRefresh` propagates to every token lookup**, so a refresh of a
  phrase refreshes its words too. Consistent with the flag's meaning.

### D5 — "No fan-out" is about providers, and this is not a violation

`lookup-cache`'s "No fallback or fan-out" requirement reads: "The system
SHALL call at most one provider per request and SHALL NOT retry a different
provider on failure, timeout, or empty result."

The split calls **one** provider, several times, with different inputs. The
requirement's concern is a caller losing track of which provider answered,
and that is untouched: a single `provider` is resolved once for the whole
request and every token lookup uses it, with the resolved name on the
response as always. The spec text is clarified to say so, because "empty
result" appears in it and a phrase miss is an empty result — a future reader
could reasonably misread the split as the forbidden behaviour.

What would violate it, and is not done: falling back to a different provider
for a token the named provider lacks.

### D6 — The phrase attempt is a real lookup, and a miss is an empty candidate list

The phrase branch "fails" when the provider returns `candidates: []` for the
whole-phrase input. A provider *error* (`ProviderLookupError`) is not a miss
— it propagates as a 502 exactly as today, and no split is attempted. A
provider that is broken should look broken, not silently degrade into a
different answer shape.

Single-token input skips the split entirely: if the one-token phrase lookup
returns empty, the answer is `mode: "phrase"` with `candidates: []`, which
is today's exact behaviour. Splitting a single word would produce a
`per_word` response for a plain word lookup and break D1's compatibility
guarantee.

### D7 — Tokenization composes with, but does not include, prefix stripping

`tokenize()` comes from `norwegian-input` and does not strip `en`/`ei`/`et`/`å`.
`/ipa` applies `query_variants` to the **whole phrase** before the phrase
attempt (so `"en kalv"` tries `"en kalv"` then `"kalv"` as a phrase, and the
latter hits as a single word), and tokenizes only what is left after that.

Consequence, deliberate: `"en kalv"` resolves via the phrase branch as
`kalv`, and never splits into a transcription for the article plus one for
the noun. That was the stated reason for making normalization shared rather
than dict.cc-local.

### D8 — `/ipa` leaves the generic route factory

`routes/generic.py`'s `_post` calls `run_lookup` exactly once and cannot
express the two-stage flow. `/ipa` gets `routes/ipa.py` with its own POST
handler and keeps the generic `GET` via
`register_lookup_routes(..., register_get=True)`-equivalent registration —
the same selective opt-out `app.py` already uses for `/tts`
(`register_get=False`) and `/stt` (fully custom). No change to
`routes/generic.py` itself, so no other kind is affected.

## Risks / Trade-offs

- **[Risk] `joined` gets treated as the phrase's true pronunciation** by a
  downstream caller, since stabbur's `note.transcription` is a bare string
  with no provenance. → Mitigated by D2's strictness (present only when
  unambiguous) and the `mode: "per_word"` marker travelling on the same
  object. Not fully eliminable at this layer — if the field proves to be
  misused in practice, dropping it is a backwards-compatible change, since
  it is already an optional key.

- **[Risk] A token's citation form is misleading in isolation.** `seg` in
  `anstrenge seg` is unstressed and reduced in connected speech; its
  standalone entry is not. → Accepted on the operator's explicit decision
  that `seg` in isolation is acceptable. The per-token shape is honest about
  what it is returning (this word's transcription), which is the mitigation.

- **[Trade-off] N+1 cache rows and N health increments per phrase request.**
  → Accepted per D4; the rows are the feature, and the counters are
  informational.

- **[Risk] Latency on a cache-miss phrase with `ordbokene`**, the one live-API
  provider: a 4-word phrase becomes 1 phrase search + 4 token searches, each
  of which is itself a search call plus a per-article call. → Accepted and
  bounded: `ordbokene.py` already uses a 5s timeout per request, tokens are
  cached individually so the cost is paid once per distinct word, and
  `/ipa` has no interactive latency budget (stabbur's panel is an explicit
  "Suggest" click, and hover-translate's enrichment is already async and
  non-blocking by design).

- **[Risk] Breaking stabbur's enrichment panel**, which renders a flat
  `candidates` array. → A `mode: "per_word"` response has no `candidates`
  key, so the panel would render nothing for a phrase rather than crash —
  the same visible outcome as today's empty list. stabbur is updated
  separately; smia is a leaf service and does not wait on it.

## Migration Plan

Additive to the response shape: `mode` is new on a branch that otherwise
matches today's payload exactly, and `tokens`/`joined` appear only on input
that currently returns an empty list. No request shape change, no new
dependency, no schema migration — `LookupCache` already stores arbitrary
jsonb payloads.

**Ordering:** depends on `norwegian-input-normalization` for `tokenize()`
and `query_variants()`. Must ship after it.

Already-cached `/ipa` rows from before this change have no `mode` key. They
are phrase-branch payloads by construction (single `candidates` array), so a
reader can treat a missing `mode` as `"phrase"`. Rollback is reverting
`routes/ipa.py` and `app.py`; stale `per_word` rows left in the cache would
then be served by `GET /ipa/{id}` until evicted — acceptable, or clear the
`ipa` rows on rollback.

## Open Questions

- Should `tokens[].text` report the token as the tokenizer produced it, or as
  it appeared in the caller's original string (before punctuation
  stripping)? Specified as the former, since that is what was actually
  looked up; revisit if a caller needs to reconstruct the original string
  verbatim.
- `nst`'s multi-word coverage is unmeasured — it needs the running database.
  Worth checking during implementation, because if it turns out to hold many
  multi-word entries, the phrase branch matters more for the
  best-quality provider than the other four suggest.
