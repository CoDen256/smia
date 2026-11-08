## Context

smia's request pipeline has three stages and no place for a fourth:

```
POST /<kind> ──► _extract_*_input()  ──► run_lookup()  ──► adapter.lookup()
                 (validates presence     (hashes input,     (exact match on
                  of required keys       cache get/set)      the raw string)
                  only — no rewriting)
```

Confirmed by reading every Norwegian-facing adapter: `adapters/ordbank.py:119`
is `WHERE oppslag = :word`, `adapters/kaikki.py:128` is `WHERE e.word = :word`
(with a `forms[]` containment arm for inflected queries), `adapters/
dictcc_static.py` matches `term1_clean`/`term2_clean`, and
`adapters/dictcc_api.py` passes `s=<word>` straight through. None of them
touch the string first.

`adapters/dictcc_api.py` is the partial exception and the template for this
work. It already carries three helpers — `_strip_infinitive_marker`,
`_normalize_dictcc_phrase`, `_display_dictcc_phrase` — that know `"å komme"`
and `"komme"` are the same word, and `"kalv {m}"` and `"kalv"` likewise. But
they run only on dict.cc's *responses*, to decide whether a matched source
phrase is worth echoing back as context. The outbound query never sees them.

Two facts from the local data constrain the design:

1. **The lexicons contain capitalized headwords.** 47 entries in
   `providers/open-dict/nb.txt`, 132 in
   `providers/wikipron/nob_latn_broad_filtered.tsv`, and 1,922 of kaikki's
   79,403. A design that lowercases the query before lookup silently breaks
   proper-noun lookups that work today.
2. **The article is sometimes part of the entry.** dict.cc files `"en gang"`
   (= once), `"et par"` (= a couple), `"en del"` (= a fair amount) as
   entries in their own right, and both `"å"` (a small river) and `"en"`
   (juniper) are standalone Norwegian nouns. A design that strips the
   prefix and queries only the remainder destroys these.

Both facts point the same way: normalization must be **additive**.

## Goals / Non-Goals

**Goals:**
- A word given in Norwegian citation form (`en kalv`, `ei bok`, `et hus`,
  `å komme`) resolves against every Norwegian provider, not just the bare
  lemma.
- One definition of "strip the Norwegian article/infinitive prefix" in the
  codebase, reachable by any adapter or route.
- No request that works today can stop working: the caller's original string
  is always among the queried variants.
- Specify `tokenize()` now, so `ipa-multiword` consumes a contract rather
  than inventing one.

**Non-Goals:**
- No POS-conditional behaviour. The ask was phrased as "for verbs and
  substantives", but `/inflections` takes `{word, lang}` and
  `/translations` takes `{text, from, to}` — there is no `pos` anywhere in
  any request contract, and adding one is out of scope. The rule is purely
  surface-level (see D2).
- No English or German article stripping (`a`/`an`/`the`,
  `der`/`die`/`das`). `dictcc_api` does serve `lang=en`/`de`, but this
  service only cares about their Norwegian-touching side, and the
  equivalent surface rules for those languages are not established here.
- No cache-key change. Normalization stays strictly below `run_lookup`.
- No `/ipa` or `/stt` wiring. `/ipa` belongs to `ipa-multiword`.
- No stemming, lemmatization, or fuzzy matching. kaikki's `forms[]`
  containment arm and `ordbank_fullform` already handle inflected queries
  where their data supports it; this change is about prefixes and case, not
  morphology.

## Decisions

### D1 — The contract is `query_variants(text) -> list[str]`, not `normalize(text) -> str`

The module's primary entry point returns an ordered list of strings to try,
with the caller's original always first:

```python
query_variants("en kalv")  # ["en kalv", "kalv"]
query_variants("å komme")  # ["å komme", "komme"]
query_variants("Kalv")     # ["Kalv", "kalv"]
query_variants("En Kalv")  # ["En Kalv", "en kalv", "Kalv", "kalv"]
query_variants("kalv")     # ["kalv"]
```

Order is significant and stable: more-faithful-to-the-caller first. Duplicates
are collapsed, so a single-word lowercase query yields a one-element list and
every call site's loop degenerates to today's single query with no special
case — the same trick `dictcc-norwegian-multi-pair`'s D1 used to avoid
special-casing `nb`.

**Why not `normalize() -> str`:** a function returning one string must decide
whether `"en gang"` means *once* or *a corridor*, and whether `"Kalv"` is a
surname or a sloppily-capitalized noun. It cannot know. Returning variants
moves that decision from the normalizer (which has no information) to the
provider's own data (which does) — if dict.cc has `"en gang"`, that variant
hits; if it only has `"gang"`, the other variant hits; if it has both, dedupe
collapses or keeps them per the existing `(pos, paradigm)` identity rule. This
is the same philosophy as the service's "return candidates, never one answer"
boundary, applied one stage earlier.

### D2 — The prefix rule is surface-level and deliberately narrow

Strip the leading token when **all** of these hold:

- the input has **two or more** whitespace-separated tokens, and
- the first token case-insensitively equals one of `en`, `ei`, `et`, `å`.

The two-token minimum is what protects `"å"` (a small river) and `"en"`
(juniper) as standalone lookups — a bare `"å"` has nothing to strip to.
Only one prefix is ever stripped; `"en å"` yields `["en å", "å"]` and stops.

Rejected: conditioning on an inferred POS, or on whether the remainder looks
like a noun. Both require knowledge the request does not carry, and D1 makes
them unnecessary — a wrong guess costs one extra query, not a wrong answer.

Note the asymmetry worth recording: `en`/`ei`/`et` are *articles* and `å` is
an *infinitive marker*. They are grouped under one rule because the surface
operation is identical, not because they are the same part of speech.

### D3 — Case folding is a separate, additive variant

A lowercase form is appended as its own variant when it differs from the
original, and never replaces it. Given the 2,101 capitalized headwords
counted across the three local lexicons, replacement would be a regression.

Variant generation is therefore the cross product of two independent
operations, original-first in both dimensions:

```
            │ as-given          lowercased
────────────┼──────────────────────────────
as-given    │ "En Kalv"         "en kalv"
stripped    │ "Kalv"            "kalv"
```

flattened to `["En Kalv", "en kalv", "Kalv", "kalv"]` and deduplicated. For
the overwhelmingly common already-lowercase input this collapses to one or
two entries.

### D4 — Merging across variants reuses each adapter's existing dedupe identity

No new dedupe machinery. Each adapter already has — or trivially has — a
notion of result identity, established by `dictcc-norwegian-multi-pair` D3:

| Adapter | Identity for dedupe |
|---|---|
| `dictcc_api` inflect | `(pos, paradigm)` — already implemented |
| `dictcc_api` tts | `sha256` — already implemented, content-addressed |
| `dictcc_api` translate | `(entry_type, source_phrase)` — already its grouping key |
| `ordbank` | `(lemma, pos, paradigm)` |
| `kaikki` | `(lemma, pos, paradigm)` |
| `dictcc_static` | `(pos, tags)` — already its grouping key |

For `dictcc_api` the variant list *crosses* the existing pair list, so the
existing per-pair loop becomes a loop over `(lp, dir, variant)` triples.
Its established failure rule carries over unchanged: a single triple failing
contributes no candidates, and the lookup only raises if **every** triple
failed.

### D5 — Local providers pay no extra round trip; dict.cc does

The variant list means something different depending on whether the provider
is local SQL or a network call:

```
LOCAL (ordbank, kaikki, dictcc_static)    NETWORK (dictcc_api)
────────────────────────────────────      ──────────────────────────────
WHERE oppslag = ANY(:variants)            for lp, dir in pairs:
  ← one query, one round trip                for v in variants:
  ← Postgres dedupes nothing; the               _get_json(s=v, ...)
    adapter's identity rule does          ← up to 2 pairs × 2 variants
                                            = 4 requests on a cache miss
```

Accepted for dict.cc: four requests on a cache miss for a two-token `nb`
query, one or two for the common single-token case. The `lookup-cache` layer
still stores one combined payload per distinct caller input, so the cost is
paid once per distinct input, not per request — the same trade-off accepted
in `dictcc-norwegian-multi-pair`'s Risks section, now one level deeper.

Rejected for local providers: looping the query per variant. `= ANY(:variants)`
is one statement and the tables are already indexed on these columns.

### D6 — The module lives at the repo root, not under `adapters/`

`norwegian.py` sits beside `cache.py`, `registry.py`, `health.py`. It is
consumed by four adapters today and by a route once `ipa-multiword` lands, so
it is service infrastructure, not a provider. Placing it under `adapters/`
would also fight `adapters/__init__.py`, which imports every module in that
package for registration side effects — `norwegian.py` registers nothing.

### D7 — dict.cc's response-side helpers move into the module

`_strip_infinitive_marker`, `_normalize_dictcc_phrase` and
`_display_dictcc_phrase` move from `adapters/dictcc_api.py` into
`norwegian.py`, with the dict.cc-specific annotation regex
(`[\{\[][^}\]]*[\}\]]`, which strips `{m}`/`[fig.]`) staying behind in the
adapter as the dict.cc detail it is. The shared part is "strip the å".

This keeps one definition of the prefix rule, so the outbound query and the
inbound comparison can never drift apart — a real hazard, since
`_normalize_dictcc_phrase` is what decides whether a matched phrase is echoed
back in a candidate's `context` field.

### D8 — `tokenize()` is specified now and consumed later

Defined here so `ipa-multiword` inherits a contract. Rules, per the
operator's decisions:

- Split on whitespace.
- Strip leading/trailing punctuation from each token (`.`, `,`, `!`, `?`,
  `:`, `;`, quotation marks, parentheses).
- **Hyphens are not split points** — `sju-åtte` is one token.
- **Digit-only tokens are dropped.** A numeral has no lexicon entry worth
  returning.
- Reflexive `seg` is an ordinary token and is **kept** — `anstrenge seg`
  tokenizes to `["anstrenge", "seg"]`, and `seg` in isolation is a legitimate
  result.
- Empty tokens (punctuation-only) are dropped.

`tokenize()` deliberately does **not** apply the D2 prefix rule — composing
the two is the caller's choice, and `ipa-multiword` will specify which it
wants where.

## Risks / Trade-offs

- **[Risk] A stripped variant finds a real but wrong word.** `"en gang"` →
  `"gang"` (corridor) returns a genuine entry that is not what the caller
  asked about. → Mitigated, not eliminated: the unstripped variant is always
  queried too, so if dict.cc has `"en gang"` both appear as candidates and
  the caller chooses. This is exactly the ambiguity the service already
  exists to surface — `/inflections` has returned multiple candidates for
  ambiguous input since `smia-service-foundation` (`skinner` = verb or noun
  plural), and nothing here picks a winner.

- **[Trade-off] Up to 4 dict.cc requests per cache-miss lookup** (2 pairs ×
  2 variants), up from 2. → Accepted. Only two-token queries reach 4; the
  common single-token case is unchanged at 2. dict.cc's mobile-app backend
  has no rate limit this service has hit, and the `lookup-cache` pays it once
  per distinct input.

- **[Risk] More candidates per response may read as noise** in stabbur's
  enrichment panel, which lists candidates for the operator to copy from. →
  Accepted and bounded by D4: variants that resolve to identical content
  collapse via each adapter's existing identity rule, so extra candidates
  appear only when the variants genuinely found *different* entries — which
  is information, not noise.

- **[Risk] Moving the three dict.cc helpers (D7) touches working
  response-side logic** that `translate-multi-candidate` tuned carefully. →
  Mitigated by moving them verbatim, leaving the dict.cc annotation regex in
  place, and relying on the existing `tests/test_dictcc_api.py` suite (23
  tests) to catch any drift.

- **[Risk] `tokenize()` ships unconsumed**, so its rules are unverified
  against real data until `ipa-multiword`. → Accepted deliberately: its
  tests are written here against the specified rules, and `ipa-multiword` is
  free to amend the spec if real `/ipa` data contradicts them.

## Migration Plan

Additive and internal. No request or response shape changes, no cache-key
changes, no new environment variables, no new dependencies, no schema
migration. Rollback is reverting `norwegian.py` and the four adapter files.

Deployment order does not matter relative to `ipa-multiword` — that change
depends on this one, not the reverse.

## Open Questions

- Should `dictcc_static`'s `term1_clean`/`term2_clean` columns, which already
  hold an annotation-stripped form, additionally hold a prefix-stripped form
  computed at import time? That would make the variant list a no-op for that
  provider at the cost of a reimport. Deferred — the `= ANY(:variants)`
  approach needs no reimport and the table is not large enough for the index
  cost to matter.
