# CLAUDE.md

Thin pointer. The substance lives in the docs tree — do not duplicate it here.

## Start here

1. [SYSTEM-CONTEXT.md](SYSTEM-CONTEXT.md) — the hub. Read first, always.
2. [docs/methodology.md](docs/methodology.md) — the product constitution. Non-negotiable.
3. [docs/architecture.md](docs/architecture.md) — system design, lifecycle, hosting constraints.
4. [docs/analysis-contract.md](docs/analysis-contract.md) — **single owner** of both schemas.
5. [docs/evaluation.md](docs/evaluation.md) · [docs/threat-model.md](docs/threat-model.md)
6. [docs/decisions/](docs/decisions/) — ADRs. Append-only.

## Working agreements

**Documentation**

- One owner per topic. The contract lives in `analysis-contract.md` and nowhere else; link, never restate.
- Context docs are committed. `.claude/` is gitignored.
- Known limitations get an explicit section. An implicit limitation gets rediscovered as a bug.
- A decision that changes architecture gets an ADR before the code, not after.

**Verification**

- A passing test is not evidence. Remove the guard and prove the test fails. A test that still
  passes without its guard is decoration.
- Reproduce a bug before claiming it exists or claiming it is fixed.
- Do not report a number that was not measured. Design intent is labeled as design intent.

**The rules that are not negotiable**

- Frame analyzes content, not people. Never name the author or the outlet in output.
- Displayed evidence is always the source substring, recovered from the submission. Never the
  model's string.
- No client ever talks to Gemini. No client ever sees raw model output.
- The model never emits a score, a confidence, or a character offset. The backend owns all three.
- Abstain rather than classify without validated evidence.

## Unresolved

Open questions Q1–Q5 are listed in [SYSTEM-CONTEXT.md §6](SYSTEM-CONTEXT.md#6-open-questions).
They are open on purpose. Do not close one by writing code that assumes an answer — raise it.
