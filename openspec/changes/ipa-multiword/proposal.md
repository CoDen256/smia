## Why

`POST /ipa` silently returns nothing for any input longer than one word.
Every configured provider matches a single wordform exactly —
`adapters/nst.py`, `adapters/ipadict.py` and `adapters/wikipron.py` all do
`WHERE wordform = :word`, `adapters/kaikki_ipa.py` does `WHERE word = :word`,
and `adapters/ordbokene.py` searches one headword — so a phrase produces
`{provider, candidates: []}`, indistinguishable from a word the provider
genuinely lacks.

That matters because phrases are a first-class thing in this ecosystem, not
an edge case: stabbur's note `type` is `word | expression | …`, and the
`pronunciation` card type puts the **transcription** on the answer side of
the card. An `expression` note can never get a transcription today.

A phrase-first lookup is worth attempting rather than assuming, because some
providers do hold multi-word entries — `providers/open-dict/nb.txt` has 199
of them (`av og til`, `anstrenge seg`, `alkoholfritt øl`) and kaikki has 775
multi-word headwords. But those are the minority (wikipron's Norwegian set
has zero), so the per-word split is the path most requests will take.

## What Changes

- `POST /ipa` SHALL try the **whole phrase first**. If the named provider has
  an entry for it, the response is exactly today's shape.
- On a phrase miss, the input is **tokenized and looked up word by word**
  against the same provider, and the response carries a per-token breakdown
  instead of a flat candidate list.
- The response becomes a **discriminated union** keyed on a new `mode` field:
  `mode: "phrase"` keeps today's `candidates` array; `mode: "per_word"`
  carries a `tokens` array. Single-word requests always take the `phrase`
  branch, so **existing callers see no change**.
- A convenience `joined` string is included **only when every token resolved
  to exactly one candidate**. When any token is ambiguous or missing,
  `joined` is absent — so its absence is itself the signal that the caller
  must choose, and the service never picks a winner on the caller's behalf.
- Words with no entry are reported as a token with an empty `candidates`
  array, not omitted and not an error — a gap is visible, per the operator's
  decision to skip rather than fail.
- Each token is looked up through the ordinary cache runner, so **every word
  becomes its own reusable cache row**: transcribing `god morgen` primes
  `god dag` for free.
- Tokenization follows the `norwegian-input` capability: hyphenated
  compounds stay whole, digit-only tokens are dropped, and `seg` is kept as a
  legitimate standalone token.

## Capabilities

### Modified Capabilities
- `ipa-api`: the response contract gains the `mode` discriminator, the
  `tokens` breakdown and the conditional `joined` field; multi-word input
  becomes a specified behaviour rather than an empty result.
- `lookup-cache`: clarifies that the existing "no fallback or fan-out"
  requirement constrains *provider* fan-out — one request still reaches
  exactly one provider — and that looking the same provider up once per
  token is not a violation. Also records that one request may create
  several cache resources.

## Impact

- **New** `routes/ipa.py`: `/ipa` stops using the generic
  `register_lookup_routes` factory and gets its own POST handler, the same
  way `/stt` and `/tts`'s GET already opt out of generic registration in
  `app.py`. The generic `GET /ipa/{id}` is retained unchanged.
- `app.py`: `register_lookup_routes(app, "ipa", _extract_ipa_input)` is
  replaced by the new route registration.
- **No adapter changes.** All five `/ipa` adapters keep their single-word
  `lookup()` contract; the split lives above them. This is deliberate — one
  implementation covers every current and future `/ipa` provider.
- `health.py` counters: a phrase request records one request per token rather
  than one per request, so `/ipa`'s counts become token-denominated.
  Accepted (design D4) — the counters are explicitly informational and never
  influence routing.
- **Depends on** `norwegian-input-normalization` for `tokenize()`.
- Downstream, not in this change: stabbur's enrichment panel renders a flat
  `candidates` list and will need to handle `mode: "per_word"` before an
  operator can use this from the UI. smia stays a leaf service and is not
  blocked on it.
