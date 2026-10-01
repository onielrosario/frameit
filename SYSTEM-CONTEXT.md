# Frame — System Context

> The hub document. Everything else is a spoke. If a fact appears here and in a spoke,
> the **spoke owns it** and this file should link rather than repeat.

**Status:** build step 12 — Gemini connected with structured output. Evidence is span-recovered, the
result comes from a **provisional** scorer (step 14 replaces it), propaganda is withheld until step
15. No baseline eval run yet (step 13): nothing about quality has been measured. First live calls
(5 passages, n=1): 3–8 s on `gemini-3.8-flash`, every excerpt recovered exactly, frequent Gemini 503s
— see [services/api/docs/CONTEXT.md](services/api/docs/CONTEXT.md#first-live-calls-2026-09-29).
**Last updated:** 2026-09-29
**Audience:** maintainers, contributors, and AI agents working in this repo. Newcomers start at the
[README](README.md).

---

## 1. What Frame is

> Frame analyzes how submitted content frames a political issue, identifies the observable
> signals behind that framing, and flags potential propaganda techniques when supported by evidence.

Frame is **not** a fact checker, a political identity detector, an author profiler, or a chatbot.

The MVP is one interaction:

```
select text on a webpage → right click → "Frame It" → concise, evidence-grounded analysis
```

The product's defensibility rests entirely on one property: **every claim Frame displays can be
traced to an exact span of the text the user submitted.** If that property breaks, the product has
no reason to exist. See [docs/methodology.md](docs/methodology.md).

---

## 2. Repo map

```
frame/
├── SYSTEM-CONTEXT.md          ← you are here (the hub)
├── CLAUDE.md                  ← thin pointer + working agreements
├── apps/
│   ├── extension/             Chrome MV3 · TypeScript · React · Vite
│   │   └── docs/CONTEXT.md
│   └── web/                   Next.js · React · TypeScript
│       └── docs/CONTEXT.md
├── services/
│   └── api/                   Python · FastAPI · Pydantic
│       └── docs/CONTEXT.md
├── evaluation/
│   ├── dataset/               JSONL, version-controlled (ADR-0004)
│   ├── runners/
│   └── reports/
└── docs/
    ├── methodology.md         product constitution · taxonomy · limitations
    ├── architecture.md        system design · lifecycle · hosting · versioning
    ├── analysis-contract.md   SINGLE OWNER of both schemas (LLM + client API)
    ├── evaluation.md          labeling protocol · mirror tests · metrics
    ├── threat-model.md        injection · abuse · privacy · symmetry
    └── decisions/             ADRs, numbered, append-only
```

### Documentation rules

Carried over from the Noema hub-and-spoke setup, which worked:

- **One owner per topic.** The API contract is owned by `docs/analysis-contract.md`. Nothing else
  restates it; other docs link to it. Duplicated contracts drift and then lie.
- **Context docs are committed.** No blanket `*.md` gitignore. `.claude/` is gitignored.
- **`CLAUDE.md` stays thin** — a pointer into this tree, not a second copy of it.
- **Known limitations get their own section, stated plainly,** in every doc that has them. A
  limitation that is implicit is a limitation that gets rediscovered as a bug.

---

## 3. Stack (locked)

| Layer | Choice | Notes |
|---|---|---|
| First client | Chrome extension, Manifest V3 | TypeScript · React · Vite |
| Result surface | **In-page overlay in a shadow root** | ADR-0001 — *not* the action popup |
| Web | Next.js + React + TypeScript | Landing page only for MVP |
| API | Python + FastAPI + Pydantic | |
| Hosting | **All Vercel** | ADR-0002 — two Vercel projects, one repo |
| LLM | Gemini API | model via `FRAME_ANALYSIS_MODEL`, never hardcoded |
| Cache / rate limits | Upstash Redis (REST) | |
| Durable store | Neon Postgres | **deferred to Milestone 9** — not on the critical path |
| Eval data | JSONL in git | ADR-0004 |
| Auth / payments | None | |
| Scope | U.S. politics, English | |
| Input limit | 5,000 chars | soft floor at ~40 words, see §5 of methodology |

---

## 4. Where things stand

Built so far: the monorepo skeleton (npm workspaces over `apps/*`; `services/api` stays outside
them as a Python project) and extension stages 1-5 — an MV3 extension that loads, a popup, the
"Frame It" context menu, selection capture via `executeScript`, and the shadow-DOM overlay
rendering the captured text. The Stage 4 measurement has been run and corrected two claims in
[docs/architecture.md §2](docs/architecture.md#2-chrome-extension). See
[apps/extension/docs/CONTEXT.md](apps/extension/docs/CONTEXT.md).

The build order is in
[docs/architecture.md §Build order](docs/architecture.md#10-build-order), which differs from the
original master plan in two places:

1. **The evaluation harness moves from Milestone 8 to Milestone 4.** Twenty hand-written examples
   before Gemini is first connected means the first prompt iteration has a scoreboard instead of
   vibes. Without this, prompt tuning is guesswork for weeks and you can't tell a regression from
   noise. **Done at step 11 — except the twenty examples, which are Oniel's to write
   ([evaluation/dataset/GUIDELINES.md](evaluation/dataset/GUIDELINES.md)).**
   **Gate overridden 2026-09-29:** step 12 went ahead with `dev.jsonl` at 18 agent-drafted records
   that the validator rejects (Oniel's decision). Those records quoted news articles verbatim and
   were removed on 2026-10-01 before open-sourcing; `dev.jsonl` is empty again. Consequence, stated plainly: until step 13 runs
   against human labels, **any change to the prompt or scorer is unmeasured.** Prompt v0 was written
   once from the methodology and has not been tuned.
2. **Postgres moves from Milestone 0 to Milestone 9.** Telemetry is structured logs until there is
   something worth querying. This removes a whole infra dependency from the path to first analysis.

---

## 5. Decisions already made

See `docs/decisions/`. Summary:

- **ADR-0001** — Result surface is an in-page shadow-DOM overlay, not the action popup.
- **ADR-0002** — All-Vercel hosting; the API is a FastAPI app on the Python runtime with Fluid compute.
- **ADR-0003** — MVP taxonomy excludes *headline framing* and *demonstrable omission*.
- **ADR-0004** — Evaluation dataset lives as JSONL in git, not in Postgres.

---

## 6. Open questions

These are unresolved and are **not** to be silently decided by whoever touches the code first.
Written here so they stay visible.

| # | Question | Default in the docs today | Why it matters |
|---|---|---|---|
| Q1 | Does the public API contract expose a float `score`? | **No** — label only; the needle position is derived client-side and documented as presentational. | A two-decimal score over ~4 discrete signals is precision we cannot defend, and the whole pitch is defensibility. |
| Q2 | Is `non_political` a distinct status from `unclear`? | **Yes** — four statuses: `classified`, `unclear`, `non_political`, `blocked`. | "Unclear political framing" on an iPhone review reads as Frame being confused. |
| Q3 | What is the abstention floor for short input? | ~40 words: below it, confidence is capped at Medium and the evidence bar rises. No hard reject. | X posts are legitimately short; a hard floor kills a primary use case, no floor produces confident reads of eight words. |
| Q4 | One repair retry on failed evidence validation, or drop immediately? | **One repair call**, then drop and re-score. *Step 12 built neither a retry nor a decision: it drops and re-scores, and logs recovered/rejected counts per request so the rate this question needs is now measurable.* | A retry doubles worst-case latency. Needs a measured decision once we see real validation-failure rates. |
| Q5 | Free-tier evidence count | One item (per the master plan) | Untested. May make Unclear and low-evidence results feel empty. |

---

## 7. The thing that actually has to be true

Not "the extension works." This:

> I can select a politically relevant passage on any normal webpage, invoke Frame It, receive a
> concise Left / Right / Center / Unclear assessment, inspect the exact evidence that produced it,
> and verify that the evidence actually exists in the submitted text.

Everything after that is expansion.

---

## 8. Known limitations of this document

- Parts of this tree were written before the code they describe. Where a doc states how a
  component behaves without citing a test or a measurement, treat it as **design intent**. Steps
  13-22 (see architecture.md §10) are not built.
- ~~The Chrome `selectionText` truncation ... must be measured before it is designed around.~~
  **Measured 2026-09-11.** The folklore truncation limit was false at 5,000 characters; the real
  problem is character substitution (U+000A → U+0020) at unchanged length. See
  [docs/architecture.md §2](docs/architecture.md#2-chrome-extension). The design did not change;
  its justification did.
- Cost, latency and unclear-rate targets throughout these docs are guesses. They are placeholders
  for measured values, and should be replaced the moment real numbers exist.
