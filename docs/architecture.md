# Frame — Architecture

> **Owner of:** system design, request lifecycle, normalization and evidence validation mechanics,
> hosting constraints, versioning, cache identity, and build order.
> Schemas are owned by [analysis-contract.md](analysis-contract.md). Product rules are owned by
> [methodology.md](methodology.md).

---

## 1. The one architectural commitment

> **Frame is an analysis engine with multiple future clients, not a Chrome extension with an AI
> endpoint attached to it.**

Every client — Chrome today, web / iOS / Android later — sends the same conceptual object
(`content`, `source`, `client_version`) and receives the same contract. No analysis logic ever lives
in a client. No client ever talks to Gemini.

```
                    USER
                     │
          ┌──────────┴──────────┐
          │  Chrome Extension   │   MV3 · TS · React · Vite
          │  overlay in shadow  │
          └──────────┬──────────┘
                     │  selected text ≤ 5,000 chars
                     ▼
          ┌─────────────────────┐
          │     Frame API       │   FastAPI on Vercel
          └──────────┬──────────┘
             ┌───────┴────────┐
             ▼                ▼
        Upstash Redis    Neon Postgres (M9)
        cache · limits   telemetry · eval runs
             │
        cache miss
             ▼
          Gemini  →  schema validation  →  evidence validation
                                              │
                                              ▼
                                       backend scoring
                                              │
                                    ┌─────────┴─────────┐
                                political framing   propaganda
                                    └─────────┬─────────┘
                                              ▼
                                        compact JSON
```

---

## 2. Chrome extension

Detail lives in `apps/extension/docs/CONTEXT.md`. The architecturally load-bearing parts:

### Result surface: in-page overlay (ADR-0001)

The result renders in a **shadow root injected by a content script**, not in the action popup.

Reasons, in order of weight:

1. **Opening the action popup from a context-menu click is not reliable.** `chrome.action.openPopup()`
   is gesture-restricted and has been inconsistent across Chrome versions and platforms. Building the
   core flow on it risks a Milestone 1 that cannot be finished.
2. **Only a same-DOM surface can ever highlight evidence in the page.** Inline highlighting is
   plausibly Frame's strongest UX feature. A popup or side panel can never do it.
3. The content script is already required for selection capture (below), so the overlay costs no
   additional permission.

The action popup is reduced to settings / about. `chrome.sidePanel` remains the fallback if overlay
isolation proves painful — it *can* legally be opened from a context-menu handler.

**Isolation:** set `all: initial` on the shadow host. Host-page CSS will otherwise bleed into the
overlay on a depressing number of news sites.

### Selection capture: not `info.selectionText`

`chrome.contextMenus` `OnClickData.selectionText` is **not** a safe source — but not for the reason
this document originally gave. Measured 2026-09-11, macOS, fixture served over `http://localhost`
(raw numbers in [apps/extension/docs/CONTEXT.md](../apps/extension/docs/CONTEXT.md#measured-facts)):

| Claim previously made here | Measured result |
|---|---|
| "Chrome truncates it", limit ~1,024 chars (folklore) | **False at 5,000.** `selectionText` delivered all 5,000 characters of a 5,000-character selection — the product's entire input ceiling. |
| "collapses whitespace" | **True, and understated.** Not collapsing: *substitution*. Each U+000A is replaced by U+0020, one for one, with the total length unchanged. |

**Correction, step 09.** This document previously called the substitution disqualifying on its own.
That was too strong, and the normalizer disproves it: whitespace-run collapsing folds U+000A and
U+0020 to the same single space, so both sources converge on identical normalized text and an
identical `content_hash`. There is a test that pins this
(`test_selection_text_substitution_survives_normalization`). For the measured case, the substitution
costs nothing downstream.

What remains true is narrower and worth stating precisely: a source that swaps characters at
unchanged length defeats every cheap integrity check, so it can only be trusted where something
downstream is known to erase the difference. That is a fact about *our normalizer*, not about
`selectionText`. The substitution set is unmeasured beyond U+000A — a substitution normalization
does not fold would break the exact-substring rule silently.

Both of the original arguments are now retired: truncation was folklore and wrong at the size that
matters, and the substitution is neutralized by normalization in the one case anybody has measured.
The reasons to read from the page are the ones that were never about `selectionText`'s text at all:

1. **Character fidelity.** `getSelection()` returns the text as it exists in the DOM. `selectionText`
   does not.
2. **The DOM `Range`.** It is the future highlighting anchor and `selectionText` cannot produce one.
3. **iframe coverage.** `allFrames` reaches a selection the top frame cannot see.

Still unmeasured, and not to be asserted: where `selectionText`'s length limit actually is above
5,000; whether the substitution set includes characters other than U+000A; whether either behavior
differs on Windows or Linux, or across Chrome versions. The measurement above was taken on a single
machine and a single Chrome build.

Regardless of the measured number, the selection is read from the page:

```ts
chrome.scripting.executeScript({
  target: { tabId, allFrames: true },
  func: () => window.getSelection()?.toString() ?? "",
});
```

`allFrames: true` matters — a selection inside an embedded iframe is invisible to the top frame.
Take the first non-empty result.

This path also yields the DOM `Range`, which is the future highlighting anchor. Capture it now even
if nothing consumes it yet.

### MV3 service worker

The background service worker is **ephemeral** and can be terminated (~30s idle), including
mid-`fetch`. Do not own a multi-second LLM request from the worker and expect it to survive. Either
issue the request from the surface that stays alive, or hand off state through `chrome.storage` so a
restarted worker can recover.

### Permissions

Minimal, and justified one by one in the extension CONTEXT doc. Broad host permissions are a Web
Store review problem, a user-trust problem, and unnecessary.

### Stable extension ID in development

Pin `key` in `manifest.json` so the unpacked dev extension has a stable `chrome-extension://` origin.
Without it, the API's CORS allowlist has to be edited every time the extension is reloaded from a
new path.

---

## 3. API hosting (ADR-0002)

**All Vercel.** Two Vercel projects against one repo, each with its own Root Directory:
`apps/web` (Next.js) and `services/api` (FastAPI).

FastAPI is a first-class zero-config backend framework on Vercel: it looks for a `FastAPI` instance
named `app` at a supported entrypoint, or `tool.vercel.entrypoint` in `pyproject.toml`. Lifespan
events are supported.

### Why this is fine (correcting an earlier objection)

The usual serverless-for-LLM-proxy objection does not apply here:

- **Duration is not a constraint.** Fluid compute default max duration is 300s on every plan. A 6s
  Gemini call is not close.
- **Waiting on I/O does not cost CPU time.** Vercel bills active CPU + provisioned memory time;
  time spent waiting on an AI model or a database is explicitly excluded. Frame's workload is ~99%
  waiting. This is close to the ideal Fluid workload.
- **Python bundle limit is 500 MB** (5 GB with the Large Functions beta). `google-genai` +
  `pydantic` + an HTTP driver is nowhere near it.

### What the constraints actually are

These are the ones to design around:

| Constraint | Consequence for Frame |
|---|---|
| **Fluid runs concurrent invocations in one instance** | Module-level mutable state is **shared across concurrent requests**. No request-scoped globals. Any in-process cache must be concurrency-safe or must not exist. This is the #1 footgun. |
| **1,024 file descriptors shared across concurrent executions** | Do not open TCP connection pools per invocation. Use **Upstash REST** and the **Neon serverless HTTP driver**, not long-lived socket pools. |
| **Shutdown cleanup capped at ~500ms after SIGTERM** | Never defer telemetry flush to shutdown. Write telemetry inside the request, or fire-and-forget with the response. |
| **4.5 MB request/response body** | Irrelevant at 5,000 chars. Noted so nobody rediscovers it. |
| **Single region by default (`iad1`)** | Fine. Note it when latency numbers look regional. |

### Escape hatch

Keep `services/api` a **plain ASGI application with no Vercel-specific imports in business logic**.
Vercel-specific configuration lives in `vercel.json` and `pyproject.toml` only. If Fluid's shared-state
model or anything else becomes a problem, moving to a container is a deploy-config change, not a
rewrite. Run `uvicorn` locally; `vercel dev` is for verifying the deployment shape, not for daily work.

---

## 4. Request lifecycle

```
receive request
  ↓ validate schema + client_version
  ↓ enforce 5,000-char limit
  ↓ NORMALIZE content, build offset map
  ↓ compute content_hash = sha256(normalized)
  ↓ rate limit / quota check
  ↓ global spend circuit breaker check
  ↓ cache lookup: content_hash + config_fingerprint
  ├── HIT  → return cached analysis (telemetry: cache_hit)
  └── MISS
        ↓ Gemini call (structured output)
        ↓ handle refusal / safety block → status=blocked, stop
        ↓ schema validation (Pydantic)
        ↓ EVIDENCE VALIDATION (span recovery)
        ↓ [optional] one repair retry for unrecovered excerpts
        ↓ re-score on surviving evidence only
        ↓ backend scoring → label, confidence, propaganda
        ↓ abstention gate → may downgrade to unclear
        ↓ write telemetry (no submitted content)
        ↓ cache result
        ↓ return
```

### Normalization

Normalization is **lossy for display but reversible for offsets**. Build the offset map in the same
pass that does the normalizing.

Applied: Unicode NFC; smart quotes/apostrophes/dashes folded to ASCII equivalents; non-breaking and
exotic spaces folded to U+0020; runs of whitespace collapsed; leading/trailing trim.

**The map is not optional.** Every normalized index must translate back to an index in the original
selection. Without it, every highlight will be a few characters off in exactly the texts that needed
normalizing most — and it will look like a random, unreproducible bug.

Store alongside the analysis: `normalization_version`. A change to the normalizer changes offsets
and therefore invalidates cache entries.

### Evidence validation

Not accept/reject. **Span recovery.**

```
model excerpt ──► normalize with the same normalizer
              ──► exact substring search in normalized content
                    ├── unique hit  → RECOVERED
                    ├── multiple hits → RECOVERED (first; log ambiguity)
                    └── no hit
                          ↓ fuzzy alignment over a sliding window
                            (token-level, high similarity threshold)
                            ├── above threshold → RECOVERED, snap to source span
                            └── below          → REJECT the item
```

Non-negotiable rules:

- **The displayed excerpt is always the source substring**, never the model's string. The model's
  string is a query, not content.
- The model **never** produces character offsets. It cannot count. Offsets are derived by the backend.
- The fuzzy threshold must be high enough that a semantic paraphrase fails. Tune it against the
  evaluation set and record it under `scoring_version`; do not pick it by feel.
  **Status (step 10):** `FUZZY_THRESHOLD = 0.90`, derived from a measured gap on a synthetic corpus
  (0.831 reject ceiling, 0.976 recover floor) — see
  [services/api/docs/CONTEXT.md](../services/api/docs/CONTEXT.md#evidence-validator-step-10).
  It has not seen real model output and there is no `scoring_version` to record it under yet.
  Re-derive at step 17.
- Every rejection is logged with the model's excerpt (a fragment, subject to the retention rules in
  [threat-model.md](threat-model.md#3-privacy)). Rising rejection rate is the single best early warning
  of a bad prompt or model change.

### Re-scoring after validation

This is the step most likely to be skipped and most likely to matter.

If validation removes evidence, the classification **must be recomputed from survivors**, and the
abstention gate re-applied. A `classified` result whose only Strong signal was hallucinated becomes
`unclear`. Emit a distinct telemetry event — `classification_downgraded_after_validation` — because
a rise in that rate is the earliest visible symptom of model drift.

### Repair retry (Q4, open)

Current default: one repair call naming the excerpts that were not found verbatim, asking for their
replacements, then drop and re-score. Capped at one. Revisit once real failure rates exist — if the
first-pass recovery rate is high, the retry is latency we are paying for nothing.

**Step 12:** not built. The API drops and re-scores, and logs signals proposed / recovered /
rejected per request — the rate this decision needs. Q4 stays open.

---

## 5. Backend scoring

The model identifies **signals**. The backend computes the **result**.

Be honest about what this buys. If the model emits `policy framing → Left`, the model still made the
political judgment; the backend did not. What the backend genuinely owns:

- deterministic aggregation of signals into a label
- the independence requirement (§3 of methodology) — three loaded-language findings are one signal
- the abstention gate
- confidence, as a pure function
- thresholds, changeable without touching the prompt and versioned separately

That is real value — consistency, auditability, calibration without re-prompting — but it is not
"the score is model-independent." Say so in public material.

The scoring module is pure, synchronous, and unit-tested. It takes validated evidence in and returns
a result out. No I/O, no model calls.

---

## 6. Versioning and cache identity

Track:

```
schema_version · prompt_version · model_version · scoring_version
taxonomy_version · normalization_version · analysis_version
```

Prompts live as **files in the repo**, hashed at build. Not in the database — a prompt in a database
is a prompt without a diff.

**Cache identity is one derived value:**

```
cache_key = content_hash + config_fingerprint

config_fingerprint = sha256(
    model_version, prompt_version, scoring_version,
    taxonomy_version, normalization_version, schema_version
)
```

One fingerprint, computed in one place. Listing six independent version fields at the call site
guarantees someone eventually forgets one and serves stale analyses across a prompt change — a bug
that is nearly invisible and poisons every evaluation run after it.

Every stored analysis and every eval report records the full version set, not just the fingerprint,
so historical results stay interpretable.

---

## 7. Caching

Key as above. TTL bounded (start at 7 days, tune).

**The cached value contains verbatim excerpts of the submitted content.** That is a real privacy
consequence and it is dealt with honestly in [threat-model.md](threat-model.md#3-privacy) rather than
quietly ignored. Do not claim "we never store submitted content" without qualification.

Cache hits should not consume the user's LLM quota (they cost us nothing). They should still count
toward abuse throttling.

---

## 8. Gemini integration

- **Model is configuration, never a literal.** `FRAME_ANALYSIS_MODEL` env var. Selected by benchmark
  against the evaluation set — cheapest model that clears the quality bar — not by picking the
  biggest one. Start with the current Flash-class model as the production candidate and benchmark a
  Pro-class model against it.
- **Structured output** via response schema. The schema is owned by
  [analysis-contract.md](analysis-contract.md).
- **Safety filters are an operational hazard, not an edge case.** Content exhibiting dehumanization
  and scapegoating is precisely what trips hate-speech filters — which means Gemini is most likely to
  refuse on the passages Frame most needs to analyze. Configure safety settings explicitly, and
  handle refusal / empty candidates / non-`STOP` finish reasons as `status=blocked`. Never let a
  refusal be reported as `unclear`; that corrupts the abstention metric.
- **Thinking budget** is a latency/cost lever. Benchmark it like the model choice.
- **Status (step 12):** safety settings are `BLOCK_ONLY_HIGH` on every text category including civic
  integrity; temperature and thinking are left at model defaults. Mechanics and the outcome table
  are in [services/api/docs/CONTEXT.md](../services/api/docs/CONTEXT.md#gemini-integration-step-12).
- One LLM call per analysis for the MVP. The pipeline in the master plan (understand → issues →
  viewpoints → signals → propaganda → evidence) is the *reasoning* structure, not a call structure.
  Multi-call only if evaluation proves single-call insufficient — each extra call multiplies latency
  and failure surface.

---

## 9. Telemetry

Structured logs until Milestone 9, then Postgres.

Record: `analysis_id`, timestamp, model, full version set, latency (total / LLM), input length,
status, classification, confidence, evidence strength, propaganda status, token usage, estimated
cost, cache hit, client version, browser, error class.

Never record the submitted content.

**Quality signals to watch, beyond the obvious:**

- evidence rejection rate
- `classification_downgraded_after_validation` rate
- `blocked` rate
- unclear rate **bucketed by direction** — see [evaluation.md](evaluation.md#4-mirror-tests); a
  divergence here is either a real finding or a broken system, and we need to know which
- cache hit rate
- p50 / p95 latency, cost per analysis

---

## 10. Build order

Changed from the master plan in two places (see SYSTEM-CONTEXT §4).

```
01  GitHub repo + monorepo skeleton
02  Minimal MV3 extension loads
03  Context menu "Frame It"
04  Capture selection via content script — MEASURE selectionText truncation here
05  Render selection in shadow-DOM overlay          ← Milestone 1 done
06  FastAPI service, POST /analyze, mocked result
07  Extension → API wired end to end
08  Pydantic schemas + response validation          ← Milestone 3
09  Normalizer + offset map + unit tests
10  Evidence validator + unit tests (synthetic pairs, no model needed)
11  Eval harness + first 20 hand-labeled examples   ← MOVED EARLIER
12  Connect Gemini, structured output                ← done 2026-09-29, before the 20 labels (SYSTEM-CONTEXT §4)
13  First eval run — establish the baseline
14  Scoring engine + abstention gate
15  Propaganda pipeline
16  Grow eval set to ~150, add mirror pairs
17  Evaluate, fix failures, iterate prompt against the dev split
18  Redis caching + rate limiting + spend circuit breaker
19  Telemetry
20  Deploy
21  Self-test, then 2–3 external testers
22  Measure repeat usage
```

Steps 9 and 10 need no model and no network. They are pure functions with hard correctness
requirements — build and test them before anything depends on them.

---

## 11. Testing standards

The project's verification bar, stated once:

- **A test that passes is not evidence.** For every guard that matters — evidence validation,
  abstention gate, scoring thresholds, the normalizer's offset map — remove the guard and prove the
  test fails. A test that passes with the guard removed is decoration.
- **Reproduce before claiming.** A bug is not fixed until it was first reproduced.
- The evidence validator gets **mutation-style tests**: paraphrases, curly quotes, collapsed
  whitespace, injected ellipses, and outright fabrications, each with an asserted outcome.
- The normalizer gets **round-trip property tests**: for every normalized index, mapping back to the
  original and slicing must return the expected characters.
- Golden-file tests for the eval runner so report format changes are visible in diffs.
