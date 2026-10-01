# Frame — Analysis Contract

> **SINGLE OWNER** of the LLM output schema, the client-facing API contract, evidence span
> representation, and version-compatibility rules.
>
> No other document, README, or code comment restates these shapes. Link here instead.
> Duplicated contracts drift, and a drifted contract is worse than no contract.

Status: **v0**. Implemented as of build step 12 (`services/api/app/models/analysis.py`,
`services/api/app/analysis/model_output.py`); where this document and the code disagree, that is a
bug to report. Field names may still move before v1. The rules below the
schemas are the part that should not move.

---

## 1. Two schemas, not one

| Schema | Producer | Consumer | Contains |
|---|---|---|---|
| **Model output** (`schema_version`) | Gemini | the API, never a client | signals, candidate evidence, technique claims, model's own reasoning artifacts |
| **Client contract** (`api_version`) | the API | extension / web / iOS | validated result only |

**A client never sees model output.** Not a passthrough field, not a debug key, not "just for now."
The moment raw model prose reaches a client, every guarantee in
[methodology.md](methodology.md) becomes unenforceable.

---

## 2. Model output schema (v0)

Requested via structured output. Illustrative shape:

```jsonc
{
  "content_assessment": {
    "is_political": true,
    "political_issues": ["healthcare policy"],
    "interpretation_risk": "none" | "sarcasm" | "satire" | "fragmentary" | "addresses_analyzer"
  },
  "signals": [
    {
      "category": "policy_framing",        // enum, taxonomy_version
      "direction": "left" | "right" | "neutral",
      "strength": "strong" | "moderate" | "weak",
      "excerpt": "Government must step in to protect vulnerable families.",
      "interpretation": "Presents government intervention as necessary rather than as one option."
    }
  ],
  "propaganda": [
    {
      "technique": "fear_appeal",           // enum
      "excerpt": "...",
      "interpretation": "..."
    }
  ],
  "limitations": ["..."]
}
```

### Rules on this schema

- **No `score` field.** The model does not produce a number. It produces signals; the backend
  produces the score. A model-emitted `-0.73` is an unauditable verdict wearing a decimal point.
- **No `confidence` field.** Confidence is a deterministic backend function
  ([methodology.md §7](methodology.md#7-confidence)).
- **No offsets.** The model cannot count characters. Offsets are derived by span recovery.
- **No author, publication, or ideology fields.** Nothing that could become a Rule 1 or Rule 11
  violation should be representable in the schema. If it can't be expressed, it can't leak.
- `category` and `technique` are **closed enums** bound to `taxonomy_version`. An unknown enum value
  is a schema validation failure, not a passthrough. Their values are methodology §4 / §8, defined
  once in `services/api/app/models/taxonomy.py` and shared by both schemas (`taxonomy_version` 1).
- `interpretation_risk: "addresses_analyzer"` marks content that speaks to the analyzer
  ([threat-model.md §1](threat-model.md#1-prompt-injection)). It scores as `unclear`.
- Every signal and technique **must** carry an `excerpt`. An item without one is dropped before
  validation even runs.

---

## 3. Client API contract (v0)

### Request

```json
{
  "content": "…",
  "source": "chrome",
  "client_version": "0.1.0"
}
```

`content` ≤ 5,000 characters, post-trim. Server re-checks; never trust the client's own limit.

### Response

```jsonc
{
  "api_version": "0",
  "analysis_id": "an_…",
  "status": "classified",           // classified | unclear | non_political | blocked

  "classification": {               // present only when status = classified
    "label": "slightly_left",       // strongly_left … strongly_right, center
    "position": -0.35               // PRESENTATIONAL ONLY — see §4
  },

  "confidence": "high",             // high | medium | low
  "evidence_strength": "strong",    // strong | moderate | weak

  "evidence": [
    {
      "category": "policy_framing",
      "excerpt": "Government must step in to protect vulnerable families.",
      "span": { "start": 142, "end": 197 },
      "interpretation": "Presents government intervention as necessary rather than as one policy option.",
      "strength": "strong"
    }
  ],

  "propaganda": {                   // null when nothing survived validation — and null always until build step 15
    "level": "low",
    "techniques": [
      { "technique": "fear_appeal", "excerpt": "…", "span": { "start": 12, "end": 61 } }
    ]
  },

  "explanation": "…",               // one or two sentences, no model prose passthrough
  "limitations": ["…"],

  "meta": {
    "cached": false,
    "min_supported_client": "0.1.0"
  }
}
```

### Status-specific shapes

- **`unclear`** — `classification` absent. `evidence` may still be **non-empty**: show what was
  observed and why it fell short. See §5.
- **`non_political`** — `classification` absent, `evidence` empty, short `explanation`.
- **`blocked`** — everything absent except `status`, `analysis_id`, `explanation`. Distinct from
  `unclear` on purpose; it is a reliability event, not an analytical outcome.

---

## 4. `position` is presentational — or absent (Open Q1)

`position` exists only to place the needle on the spectrum. It is **derived from the label**, not a
measurement.

It must never be:

- displayed as a number
- compared across analyses
- reported in aggregate as if it were a measured quantity
- treated as more granular than the label

The alternative, currently preferred, is to **drop it from the contract entirely** and let each
client derive needle position from the label. A published two-decimal number over a step function of
~4 discrete signals is precision we cannot defend, and unearned precision is the exact failure this
product argues against. Decide before v1 freezes.

The internal calibration float stays internal, in telemetry, where it is useful for threshold tuning.

---

## 5. Evidence spans

```jsonc
"span": { "start": 142, "end": 197 }
```

- Half-open `[start, end)`.
- Indices are into the **normalized** content ([architecture.md §4](architecture.md#normalization)),
  and the normalizer is reversible to the original selection.
- `excerpt` is always `normalized_content[start:end]` — the **source substring**, never the model's
  string. A client that finds `excerpt` and `span` disagree should treat the response as corrupt.
- Spans exist from day one even though nothing renders highlights yet. Retrofitting them later means
  re-deriving them for every cached and stored analysis.

The response carries `meta.content_hash` — sha256 of the normalized content — so a client can
confirm a response applies to the text it submitted rather than to a cached analysis of something
else. **Added at step 11.**

It does **not** let a client verify `excerpt` against `span`. That needs the normalized text, and
the normalizer is server-side only. A client holds the raw selection, whose indices do not match.

---

## 6. Unclear must still be useful

A product that shrugs is a product nobody opens twice — and Unclear will be common, because most
text people casually select is short and mildly political. This is a product risk, not just a
quality metric.

So an `unclear` response carries what was actually observed:

> **Insufficient evidence for a directional read.**
> One loaded-language signal was found, which isn't enough on its own.
> "…Republicans **refused** to consider…"

Correct abstention that also teaches the user something is the difference between a tool that feels
rigorous and one that feels broken. Track unclear rate as a **product** metric with a target band,
not only as an accuracy metric.

---

## 7. Version compatibility

Extensions update lazily. Users will run a build from six weeks ago. Design for it now; retrofitting
is expensive.

- **The API is backward compatible within a major `api_version`.** Adding optional fields is fine.
  Removing or re-typing a field is not.
- **Clients must tolerate unknown enum values without crashing.** A new taxonomy category or a new
  propaganda technique must degrade to a generic rendering, never a blank screen or an exception.
  Write this into the client's parsing layer on day one, not after the first incident.
- **`meta.min_supported_client`** lets the server tell an old client to prompt for an upgrade. Ship
  the field before it is needed; it cannot be added retroactively to clients already in the wild.
- Clients send `client_version` on every request and it is recorded in telemetry. Without it, a
  regression that only affects old clients is invisible.

---

## 8. Validation ownership

```
client input   → validated by the API. Never trusted.
model output   → validated by the API. Never trusted.
client identifiers → treated as hints, never as authorization.
```

Both untrusted inputs are validated by the same service, and that service is the only place either
schema is known.

---

## 9. Known limitations

- v0 is not frozen. Field names may change before v1; treat the **rules** as stable and the
  **shapes** as provisional.
- No streaming. The analysis is a single response. If latency demands streaming later, it is an
  `api_version` change, not an additive one.
- No batch endpoint. One analysis per request.
- `explanation` is generated text with no span backing. It is constrained to describe only validated
  evidence, but it is the softest part of the contract and the most likely place for an unsupported
  claim to appear. It needs its own eval check.
