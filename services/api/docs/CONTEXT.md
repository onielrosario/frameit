# Frame API — Context

> Spoke doc. Hub is [../../../SYSTEM-CONTEXT.md](../../../SYSTEM-CONTEXT.md).
> Lifecycle and hosting constraints: [../../../docs/architecture.md](../../../docs/architecture.md).
> Schemas: [../../../docs/analysis-contract.md](../../../docs/analysis-contract.md) — **owned there, not here.**

**Status:** build step 12 — `POST /analyze` calls Gemini with structured output. The response is
built from span-recovered evidence and a **provisional** scorer (`app/scoring/provisional.py`,
replaced at step 14). Propaganda is requested from the model but **withheld from clients** until
step 15. No cache, no rate limit, no spend breaker (step 18). No baseline eval run yet (step 13), so
nothing about quality has been measured.

---

## Stack

Python · FastAPI · Pydantic. Deployed on Vercel's Python runtime with Fluid compute (ADR-0002).

## Shape

```
app/
├── api/         routes, request model
├── analysis/    prompt file, Gemini client, model-output schema, response pipeline
├── evidence/    normalizer + offset map, span recovery
├── scoring/     provisional scorer (pure)
├── models/      response models, taxonomy enums
├── config.py    environment-derived settings
└── versions.py  version set + the one config fingerprint
tests/
```

Planned, not built: `propaganda/` (step 15) and `cache/` (step 18).

`evidence/` and `scoring/` are **pure, synchronous, and I/O-free**. They are the two modules with
hard correctness requirements and they must be testable without a network or a model.

## Platform rules (Fluid compute)

These are not style preferences — breaking them produces production bugs that do not reproduce locally.

- **No module-level mutable state.** Concurrent invocations share an instance. Any in-process cache
  must be concurrency-safe or must not exist.
- **No TCP connection pools.** 1,024 file descriptors are shared across concurrent executions. Use
  Upstash REST and the Neon serverless HTTP driver.
- **No deferred telemetry flush.** Shutdown cleanup is capped at ~500ms after SIGTERM. Write inside
  the request.
- **No Vercel-specific imports in business logic.** Platform config lives in `vercel.json` and
  `pyproject.toml` only, so the hosting decision stays reversible (ADR-0002).

## Local development

`uvicorn` for daily work. `vercel dev` only to verify the deployment shape.

## Configuration

| Env var | Purpose |
|---|---|
| `FRAME_ANALYSIS_MODEL` | Gemini model ID. **Never hardcode a model anywhere else.** |
| `FRAME_MAX_CONTENT_CHARS` | 5,000 |
| `FRAME_DAILY_SPEND_CEILING_USD` | global circuit breaker — the only real cost protection |
| `GEMINI_API_KEY` · `UPSTASH_*` · `NEON_*` | secrets; never reach a client |

## Running it

Setup commands live in the [root README](../../../README.md#1-api) — one owner per topic. What
belongs here is why one of those flags exists.

**`--reload-dir app` is not optional.** Bare `--reload` watches the whole working directory,
`.venv` included. Each restart imports modules, Python writes `.pyc` files under
`.venv/**/__pycache__`, the watcher sees them, and reloads again — an infinite loop that looks like
the server crashing repeatedly. Scoping the watch to `app/` ends it.

Python 3.12 matches Vercel's runtime. A macOS system `python3` (3.9, pip 21.x) cannot install this
project: `requires-python` is `>=3.11`, and that pip predates editable installs from
`pyproject.toml`. Upgrade pip inside the venv too — a fresh venv inherits its parent's pip.

`GET /health` · `POST /analyze`. The step-06 `?mock=` query parameter was **removed at step 12**;
tests reach every status by overriding the `get_analyzer` dependency with a fixed model outcome
(`tests/fakes.py`). Without `GEMINI_API_KEY` and `FRAME_ANALYSIS_MODEL`, `/analyze` returns **503**
and `/health` keeps answering.

## Normalizer (step 09)

`app/evidence/normalize.py`. Pure, synchronous, I/O-free.

Applies in one pass: NFC, character folds (smart quotes, dashes, exotic spaces), whitespace-run
collapsing, leading/trailing trim — recording the source range of every character emitted.
`content_hash` is sha256 of the **normalized** text, so two submissions differing only in whitespace
cache-hit each other.

**NFC is applied per cluster, not to the whole string.** Composition changes length — `e` + U+0301
becomes `é` — and a whole-string normalize gives no way to know which output characters came from
which input ones. A cluster is a base character plus its following combining marks.

**Mapping within a cluster.** When NFC leaves a cluster's length unchanged, nothing composed and
each output character maps to its own source character. When the length changes, the output
characters map to the whole cluster, because none of them came from part of it. The case that forced
this: `ı` + U+0308 has no precomposed form, so NFC returns both characters unchanged — mapping both
to the whole cluster made two characters claim one source range, and a span covering just the base
character would widen to include the mark.

That bug was found by the round-trip property test, not by a hand-written example. It is exactly the
class the CONTEXT doc predicts: "every highlight a few characters off in exactly the texts that
needed normalizing most."

### What this says about the stage-04 finding

`selectionText` substitutes U+000A with U+0020. Whitespace-run collapsing folds both to the same
single space, so the two sources produce identical normalized text and hash. The extension and
architecture docs previously called that substitution disqualifying on its own; step 09 corrected
both. `test_selection_text_substitution_survives_normalization` pins the behaviour so a future change
to the fold set surfaces the consequence.

## Request path (step 11)

`POST /analyze` normalizes the submission once, at the top. Everything downstream indexes the
normalized text: spans, excerpts, and `meta.content_hash`.

Since step 12 the model's excerpts arrive as *queries* and `recover()` turns them into spans against
this same `Normalized` object. The model is shown the **normalized** text, so it quotes from the text
the spans index.

## Evidence validator (step 10)

`app/evidence/recover.py`. Span recovery, not accept/reject: the model's excerpt is a **query**, and
what gets displayed is always `normalized[start:end]`.

Both sides go through the same normalizer before comparison, so the differences normalization exists
to erase never reach the matcher. Exact hits are found with `re.IGNORECASE` — `casefold()` would be
the obvious choice but it can change length (ß → ss) and silently shift every index after it.

### Case-insensitivity is deliberate

A model quoting mid-sentence often capitalises the first word. Measured, a pure case change scores
**0.853** and would have been rejected as if it were a paraphrase. Ignoring case cannot display the
wrong text — the excerpt returned is the source substring either way — so the exact pass ignores it.

### Measured similarity, synthetic corpus (2026-09-11)

| Case | Outcome | Similarity |
|---|---|---|
| Verbatim, curly quotes, em dash, NBSP, collapsed whitespace, case change | exact | 1.000 |
| One-character typo | fuzzy | 0.991 |
| Small elision marked with an ellipsis | fuzzy | 0.983 |
| Punctuation swapped at the end | fuzzy | 0.976 |
| **— threshold 0.90 sits here —** | | |
| Elision so large the span is not what was quoted | reject | 0.831 |
| Fabricated clause appended | reject | 0.797 |
| Close paraphrase | reject | 0.730 |
| Outright fabrication | reject | 0.480 |
| Distant paraphrase | reject | 0.430 |

The gap is **0.831 → 0.976**. `test_threshold_separates_the_two_groups_with_margin` asserts the two
groups do not overlap and that the threshold lies between them, rather than asserting the constant.
A number chosen to make today's tests pass is a number picked by feel; a measured gap is a fact that
survives new cases being added. Add a case that narrows the gap to nothing and the test says so.

Note that every normalization-difference case recovers through the **exact** path. A test asserts
that: if one of them ever recovers as `fuzzy`, the normalizer stopped folding something and
threshold leniency is quietly covering for it.

## Response models (step 08)

`app/models/analysis.py`. Four models behind a discriminated union on `status`, not one model with
optional fields.

The reason is that §3 gives each status a different shape, and a single all-optional model can
represent every shape the contract *forbids* as easily as the ones it allows — a `blocked` response
carrying a classification, an `unclear` one carrying a label. Those fields simply do not exist on
those models, so the contract's rules are unconstructible states rather than assertions someone has
to remember to write.

Also structural:

- **`extra="forbid"` on every response model.** The structural half of "no client ever sees model
  output" (§1) — a stray `signals` or `raw` key raises instead of shipping.
- **Closed enums** for category, technique, label, confidence, strength (§2). The server is strict
  so clients can afford to be tolerant; §7's "tolerate unknown enums" is about values a *newer*
  server sends, not about this server inventing them.
- **No `position` field on `Classification`.** Q1 stays open; omission is the reversible direction
  (§7).

Serialized keys per status, confirmed over the wire:

| Status | Keys returned |
|---|---|
| `classified` | full shape including `classification` |
| `unclear` | same minus `classification` |
| `non_political` | same minus `classification`, `evidence` empty |
| `blocked` | `status`, `analysis_id`, `explanation`, `api_version`, `meta` only |

## Gemini integration (step 12)

```
app/analysis/
├── prompts/analysis_v0.md   the system prompt — a file, hashed into prompt_version
├── model_output.py          the model-output schema (contract §2) + per-item parse
├── gemini.py                the call (I/O) and interpret() (pure)
└── pipeline.py              model outcome → client response (pure)
app/scoring/provisional.py   stand-in scorer until step 14 (pure)
app/models/taxonomy.py       methodology §4/§8 as closed enums, shared by both schemas
app/versions.py              the version set and the ONE config_fingerprint()
```

### Outcomes

| What came back | Result | Why |
|---|---|---|
| Schema-conforming JSON, finish `STOP` | analysis | |
| `prompt_feedback.block_reason`, no candidates, empty text, any finish other than `STOP`/`MAX_TOKENS` | `status=blocked` | The model refused or was filtered. **Never `unclear`** — that would inflate the abstention metric (architecture §8). |
| Finish `MAX_TOKENS`, invalid JSON, top level off-schema | HTTP 502 | Operational failure, not a refusal. Kept out of `blocked` so the blocked rate still means "the model refused". |
| Gemini 429, or 503 "high demand" | HTTP 503 | Capacity — the client should retry. Observed repeatedly on 2026-09-29. |
| Gemini other 5xx | HTTP 502 | |
| Timeout (25s, below the extension's 30s) | HTTP 504 | |
| Gemini 4xx | HTTP 502, detail logged server-side only | Our request or config is wrong; no upstream text reaches a client. |

Validation is **per item**. A signal with a blank excerpt is dropped before validation (contract §2);
one with an unknown category, or carrying a `score`/`confidence`/offset/`author` key
(`extra="forbid"`), is dropped and logged. The top level must still validate.

### Request construction

- **Structured output** via `response_json_schema`: `ModelOutput.model_json_schema()` with `$defs`
  inlined and titles stripped. Gemini supports a JSON Schema subset; a flat schema is the least likely
  to be rejected or partially honoured. Arrays are capped (`MAX_SIGNALS=8`, `MAX_TECHNIQUES=5`).
- **Delimiting:** the submission is wrapped in `<submission-{random hex}>` tags. A fixed tag could be
  typed into a page to close the data block early; a per-request marker cannot be predicted.
  threat-model §1 — cheap and partial. Content that addresses the analyzer is to be reported as
  `interpretation_risk="addresses_analyzer"`, which the scorer turns into `unclear`.
- **Safety settings are explicit:** `BLOCK_ONLY_HIGH` on harassment, hate speech, dangerous,
  sexually explicit, and civic integrity. A starting point, not a measured choice — the blocked rate
  decides whether it moves.
- **Temperature and thinking are left at the model defaults.** Both are benchmark levers
  (architecture §8), not things to set by feel.
- **One client per call, closed after.** A module-level pooled client is shared mutable state on
  Fluid and holds sockets from the 1,024-descriptor budget (architecture §3). Cost: a TLS handshake
  per analysis.

### First live calls (2026-09-29)

Five passages to exercise each branch (four written by Claude; the Fed sentence was copied from a news article, and its recording was removed before open-sourcing) — **not** a quality measurement, not
human-labeled, n=1 per passage. The four original ones are recorded as fixtures in `tests/recorded/` and replayed by
`test_recorded.py`.

| Passage | 3.8 Flash latency | Result | Notes |
|---|---|---|---|
| Healthcare advocacy | 5.5 s | classified · left · high | 3 signals, all recovered exactly. Two strong, both framing family → not "strongly". |
| Fed rate news | 3.8 s | unclear · no signals | "Reporting a policy is not framing it." |
| Phone review | 4.3 s | non_political | |
| Injection + council vote | 3.0 s | unclear · interpretation risk | Flagged `addresses_analyzer`; the injected label was not obeyed. |
| Dehumanizing immigration rhetoric | 7.7 s (14.8 s on the first try) | classified · right · medium | **Not blocked** at `BLOCK_ONLY_HIGH`. Three strong signals, all language family → "right", not "strongly". Short input caps confidence. |

- Every excerpt the model returned recovered **exactly** (0 fuzzy, 0 rejected, 11 signals).
- Thinking tokens: 130–960 per call, often more than the output itself. The thinking level is the
  first latency lever to benchmark.
- **Gemini returned 503 "high demand" on most first attempts**, on both 3.8 Flash and 3.5 Flash.
  The smoke script retried with backoff; the API does not (it returns 503). A server-side retry
  is a latency/reliability trade to decide with the step-18 work, not by feel.
- `gemini-3.5-flash` on the same passages: 9.9–20.7 s, same statuses. Not a benchmark (n=1, and
  overload noise), but slow enough that it is not the default candidate.
- `FRAME_ANALYSIS_MODEL=gemini-3.8-flash` for development. Chosen because it answered fastest, not
  because it is better — the benchmark against the eval set picks the production model.

### What reaches a client

Built, never copied: excerpts and spans from `recover()`, label/confidence/strength from the
scorer, `explanation` and `limitations` from backend templates. The model's own `limitations`
and `political_issues` are discarded. The **one** piece of model prose that ships is each evidence
item's `interpretation` — the contract defines it as part of a validated item — whitespace-collapsed
and capped at 300 characters, and dropped with its item if the excerpt does not recover.

Propaganda is `null` in every response until step 15. The model is asked for techniques and the
recovered count goes to telemetry, but methodology §8 predicts a naive prompt will inflate ordinary
advocacy into "fear appeal", and a false finding is worse than a missed one.

### Provisional scoring

`SCORING_VERSION = "0-provisional"`. A literal reading of methodology §2/§3/§5/§7, at the most
conservative point each rule allows. **Nothing here is calibrated.**

| Rule | Implementation |
|---|---|
| Independence (§3) | Bands count **distinct categories**, never findings. "Strongly" needs ≥2 strong signals from ≥2 **families** (framing / language / structural — the methodology's own headings). |
| Weak signals (§6) | Only moderate+ categories count toward the Left/Right band. Weak-only tops out at Slightly. |
| No "Mixed" (§2) | Any left + right directional signals → `unclear`. |
| Center ≠ Unclear (§2) | Center needs ≥2 distinct neutral categories and no directional ones. One neutral observation → `unclear`. |
| Short input (§5, Q3 default) | Under 40 words: confidence caps at Medium; weak-only → `unclear`. |
| Sarcasm / satire / fragment / addresses analyzer (§10, threat model §1) | → `unclear`, whatever the evidence. |
| Self-contradiction | `is_political=false` with surviving directional evidence → `unclear`, not `non_political`. |
| Confidence (§7) | high: ≥3 categories and a strong signal; medium: ≥2 categories or a strong signal; else low. |

It scores **survivors only**, so "re-score after validation" (architecture §4) holds by construction.
It also scores the unvalidated set once, for telemetry: when the two labels differ, the request logs
`classification_downgraded_after_validation`.

### Telemetry

One JSON line per request on the `frame.telemetry` logger, written inside the request: status,
label, confidence, the full version set, `config_fingerprint`, latency (total and LLM), tokens
(prompt / output / thinking), signals proposed / recovered / rejected / fuzzy / ambiguous, techniques
proposed / recovered, blocked reason, error class, downgrade flag. **Never** the submission or a
model excerpt. (Evidence *rejections* are still logged by `recover()` with the model's excerpt — a
fragment, under threat-model §3's retention rules.)

## Tooling

`ruff` (lint + format, config in the repo-root `ruff.toml`) and `mypy` with
`disallow_untyped_defs` over `app/`. Both run in CI (`.github/workflows/ci.yml`) alongside the tests;
`make lint` and `make test` run the same checks locally. Adopting mypy surfaced real looseness:
the scorer built labels with an f-string (`f"{band}{side}"`), so a typo would only have failed at
response validation. Labels now come from a typed table.

## Testing standards

Per [../../../CLAUDE.md](../../../CLAUDE.md):

- **Evidence validator:** mutation-style tests — paraphrase, curly quotes, collapsed whitespace,
  injected ellipses, outright fabrication — each with an asserted outcome. Remove the validator and
  prove the tests fail.
- **Normalizer:** round-trip property tests. For every normalized index, mapping back to the original
  and slicing must return the expected characters.
- **Scoring:** table-driven over signal sets, including the independence rule (three loaded-language
  findings must not reach a strong label) and the post-validation downgrade path.
- **Gemini client:** tested against responses in the SDK's own `GenerateContentResponse` shape,
  including a refusal and a safety block. Those two are **synthetic**; the successful responses in
  `tests/recorded/` are live.

### Step 06 mutation results (2026-09-11)

Each guard was removed in a scratch copy and its test re-run. All five failed as they should:

| Guard removed | Test that caught it |
|---|---|
| Server-side 5,000-char check | `test_rejects_content_over_the_limit` |
| Span slicing (fabricated excerpts instead) | `test_every_excerpt_is_a_real_substring_sliced_by_its_own_span` |
| `position` omission (shipped `-0.35`) | `test_classified_response_omits_position` |
| Model-output exclusion (added a `signals` key) | `test_response_carries_no_model_output_fields` |
| `blocked` minimalism (added a classification) | `test_blocked_status_carries_nothing_but_the_minimum` |

Re-run these when the mock is replaced. A test that survives its own guard's removal is decoration.

### Step 08 mutation results (2026-09-11)

| Guard removed | Test that caught it |
|---|---|
| `extra="forbid"` → `"allow"` | `test_no_model_output_can_be_attached`, `test_blocked_cannot_carry_a_classification` |
| `position` added back to `Classification` | `test_classification_cannot_carry_position` |
| Category enum widened to bare `str` | `test_unknown_category_is_a_validation_failure_not_a_passthrough` |
| `max_length=0` dropped from non-political evidence | `test_non_political_cannot_carry_evidence` |

### Step 09 mutation results (2026-09-11)

| Guard removed | Test that caught it |
|---|---|
| Offset map: one source char per output, always | the whole normalizer suite |
| NFC applied to the whole string, not per cluster | `test_nfc_composes_and_maps_back_to_both_source_characters` |
| Whitespace runs no longer collapse | `test_whitespace_runs_collapse_and_the_span_covers_the_whole_run` |
| Trim removed | `test_leading_and_trailing_whitespace_is_trimmed` |
| Zero-width folded to a space instead of dropped | `test_zero_width_characters_are_dropped_not_folded_to_a_space` |
| The 1:1 cluster mapping reverted | `test_spans_round_trip`, and now `test_non_composing_cluster_maps_one_character_at_a_time` |

### Step 10 mutation results (2026-09-11)

| Guard removed | Caught by |
|---|---|
| No validation at all — trust the model's excerpt | the whole validator suite |
| Display the model's string instead of the source substring | `test_displayed_excerpt_is_the_source_substring_not_the_model_string` |
| Threshold dropped to 0.50 | the reject cases |
| Threshold raised to 0.999 | the drift cases |
| Excerpt not normalized before comparison | the fold cases |
| Ambiguity silently resolved as a plain exact hit | `test_repeated_phrase_is_flagged_ambiguous_not_silently_resolved` |
| Rejection no longer logged | `test_rejection_is_logged_with_the_model_excerpt` |

The last row was initially reported as uncaught: the monotonicity test had been relaxed to permit
shared source ranges, so it no longer bit. `test_spans_round_trip` did catch it, incidentally. A
direct test was added so the coverage is deliberate rather than lucky.

### Step 12 mutation results (2026-09-29)

28 guards, each removed in turn by a script (`-x`, restored after each run). All 28 caught. The
first failing test is listed.

| Guard removed | Caught by |
|---|---|
| Display the model's excerpt instead of the recovered substring | `test_displayed_excerpt_is_the_source_substring_not_the_model_string` |
| Skip span recovery — trust every excerpt | `test_fabricated_evidence_never_reaches_the_client` |
| Blocked outcome routed into scoring | `test_blocked_status_carries_nothing_but_the_minimum` |
| Fixed `</submission>` delimiter | `test_submission_cannot_close_its_own_data_block` |
| Propaganda passed through | `test_propaganda_is_withheld_until_step_15` |
| Model `limitations` prose passed through | `test_response_carries_no_model_output_fields` |
| Bands count findings instead of categories | `test_three_loaded_language_findings_do_not_reach_a_strong_label` |
| "Strongly" without the independent-family check | `test_three_loaded_language_findings_do_not_reach_a_strong_label` |
| Conflicting directions not abstained | `test_unclear_still_reports_what_was_observed` |
| Short-input confidence cap | `test_short_input_caps_confidence_at_medium` |
| Short-input weak-only bar | `test_short_input_with_only_weak_signals_is_unclear` |
| Interpretation risk ignored | `test_interpretation_risk_abstains_even_with_strong_evidence` |
| Center from one neutral signal | `test_center_needs_two_independent_neutral_observations` |
| Weak signals count toward the Left/Right band | `test_weak_signals_cannot_lift_a_band_above_slightly` |
| Self-contradicting non-political trusted | `test_self_contradicting_non_political_abstains` |
| Non-`STOP` finish accepted | `test_a_non_stop_finish_is_blocked` |
| `prompt_feedback.block_reason` ignored | `test_a_blocked_prompt_is_blocked` |
| `MAX_TOKENS` reported as blocked | `test_truncated_output_is_an_upstream_error_not_blocked` |
| Empty text accepted | `test_empty_text_is_blocked` |
| Model-output `extra="forbid"` → `"ignore"` | `test_a_smuggled_score_or_confidence_invalidates_the_item` |
| Blank-excerpt drop removed | `test_an_item_without_an_excerpt_is_dropped_before_validation` |
| Model called before the 5,000-char check | `test_rejects_content_over_the_limit` |
| Model shown the raw text, not the normalized text | `test_the_model_is_shown_the_normalized_text` |
| Downgrade telemetry removed | `test_hallucinated_strong_signal_downgrades_the_result` |
| Submission written to telemetry | `test_telemetry_never_contains_the_submission` |
| Missing configuration swallowed | `test_missing_model_configuration_is_a_503_not_a_result` |
| `$ref` left in the schema sent to Gemini | `test_schema_sent_to_gemini_has_no_refs_and_no_forbidden_fields` |
| Gemini 503 overload reported as 502 | `test_gemini_errors_map_to_honest_http_statuses` (run separately, after the first live calls) |

The step-06 rows (limit, span slicing, `position`, model-output exclusion, blocked minimalism) are
re-covered by their step-12 successors in `test_analyze.py`, now running through the real pipeline.

## Known limitations

- **Step 12 was started without the 20 human-labeled examples** SYSTEM-CONTEXT §4 required first.
  Oniel's call, 2026-09-29. There is no baseline, so any prompt change before step 13 is unmeasured.
  Prompt v0 was written once from the methodology and has not been tuned against output.
- **The scorer is provisional** and uncalibrated. Its thresholds are literal readings of the
  methodology, not fitted values. Step 14 replaces it.
- **Propaganda is withheld** from clients until step 15.
- **No repair retry (Q4).** Architecture §4's default is one repair call; it is not built, because
  Q4 asks for a *measured* decision and the recovery rate that measures it is only now being logged.
  Q4 stays open.
- **`interpretation` is model prose that reaches the client.** Capped and tied to a recovered
  excerpt, but nothing checks it for Rule 1 (naming the author or outlet). Needs its own eval check,
  like `explanation` (contract §9).
- **The refusal / safety-block fixtures are synthetic.** Five live responses are recorded, but none
  was a refusal — even the dehumanizing passage was analyzed. The blocked path is tested only
  against hand-built responses in the SDK's shape.
- **Gemini capacity errors are frequent** and the API has no retry. Most first attempts on
  2026-09-29 got a 503.
- **The `Frame` Google project is on the free tier** (AI Studio, 2026-09-29): Gemini 3.8 Flash and
  3.5 Flash each allow **5 requests/minute and 20/day**. The first day of live testing used 19/20
  and peaked at 6 RPM. Free-tier traffic is also the first to get 503 under load. A server-side
  retry is **not** worth adding on this tier — each retry spends scarce daily quota. Revisit after
  billing is enabled.
- **Free-tier data terms may contradict threat-model §3.** As understood on 2026-09-29 (not verified
  against the current terms), unpaid Gemini API content may be used by Google to improve products.
  Confirm before any external tester; Frame should not reach users on the free tier.
- **Injection is mitigated, not solved** (threat-model §1). A random delimiter and an
  `addresses_analyzer` flag raise the cost of the obvious attack; they do not stop an attacker who
  writes persuasive framing without addressing the analyzer.
- **The fuzzy threshold has never seen real model output.** architecture.md §4 requires it tuned
  against the evaluation set and recorded under `scoring_version`. The set arrives at step 11 and
  there is no `scoring_version` yet. What exists is a gap measured on a **synthetic** corpus written
  by the same person who wrote the matcher — which rules out a threshold picked by feel, but not one
  fitted to cases that happen to be easy. Re-derive at step 17 against the dev split.
- **Ellipsis handling falls out of similarity, not a rule.** A small elision recovers and the
  displayed span includes the elided words; a large one rejects. Nobody decided where that boundary
  should be — it is wherever the threshold happens to put it. If quoting with elisions turns out to
  be common, it deserves an explicit rule instead.
- **The fuzzy path is O(tokens x widths) with a `SequenceMatcher` per window.** Fine at 5,000
  characters, unmeasured above it, and it runs once per rejected-exact excerpt rather than once per
  request.
- **The fold set is a judgement call, not a measurement.** Which characters fold to ASCII, and
  which zero-width characters are dropped rather than folded, were chosen by reading
  architecture.md §4. U+200D is preserved because dropping it corrupts emoji sequences; nothing else
  in the set has been validated against real-world text.
- **`excerpt == normalized[start:end]` is upheld by construction, not asserted.** `recover()`
  returns the source substring and the pipeline copies it. The evaluation runner checks grounding
  independently from outside, which is the check that matters — a system reporting its own grounding
  is not a measurement.
- No streaming. Single response per analysis.
- Single region (`iad1` default).
- Postgres is deferred to Milestone 9; telemetry is structured logs until then, which means no
  historical querying before that point.
