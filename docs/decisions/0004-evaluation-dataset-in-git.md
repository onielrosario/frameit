# ADR-0004 — Evaluation dataset lives as JSONL in git

**Date:** 2026-09-11 · **Status:** Accepted

## Context

The master plan put `evaluation_examples` and `evaluation_reviews` in Postgres alongside the
operational tables, which made Neon a Milestone 0 dependency.

For ~150 hand-labeled examples, a database is the wrong shape. What the dataset actually needs is
review, diffing, and reproducibility — a label change should be visible in a pull request, and an
evaluation report should be reproducible against an exact dataset state.

## Decision

`evaluation/dataset/*.jsonl`, version-controlled. The dataset version is the git SHA. Reports in
`evaluation/reports/` are committed alongside.

This also removes Postgres from the critical path entirely: telemetry is structured logs until
Milestone 9, so nothing between here and the first working analysis requires a database.

## Consequences

**Good**

- Label changes appear in diffs and can be reviewed. This matters more than usual here, because
  quietly changing a label after seeing a bad result is the exact failure mode
  [evaluation.md §2.2](../evaluation.md#22-label-blind) exists to prevent, and a diff makes it visible.
- Evaluation runs are reproducible against an exact dataset SHA.
- One fewer piece of infrastructure before the product does anything.
- Trivially portable if the storage decision changes later.

**Bad**

- No review UI. Labeling happens in an editor or a small local script.
- Merge conflicts on the JSONL if two review passes ever run in parallel. Mitigated by one record per
  line and stable ordering by `id`.
- Does not scale past a few thousand examples. That is well beyond the MVP.

## Revisit when

Manual review becomes the bottleneck and a review UI is worth building. At that point the JSONL is
the seed for the tables, and migration is mechanical — the record format in
[evaluation.md §1](../evaluation.md#1-where-it-lives-adr-0004) is already table-shaped.
