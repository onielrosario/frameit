# Frame — Evaluation

> **Owner of:** dataset format, labeling protocol, mirror testing, metrics, and the honesty rules
> for reporting results.

The evaluation set is the most valuable asset in this project. It is also the easiest thing to
quietly corrupt into a machine that tells us what we want to hear. Most of this document is about
preventing that.

---

## 1. Where it lives (ADR-0004)

`evaluation/dataset/*.jsonl`, version-controlled.

Not Postgres. 150 examples are better as diffable, reviewable, PR-able files: a label change shows up
in a diff, the dataset version is the git SHA, and results are reproducible against an exact
dataset state. It also removes a database from the path to the first analysis.

Revisit when manual review actually becomes the bottleneck — i.e. when a review UI exists.

### Record format

```jsonc
{
  "id": "ev_0042",
  "input": "…",
  "source_type": "news" | "opinion" | "social" | "non_political" | "synthetic",
  "expected_status": "classified" | "unclear" | "non_political",
  "expected_label": "slightly_left",
  "expected_direction": "left" | "right" | "none",
  "acceptable_labels": ["center", "slightly_left"],
  "expected_evidence": [
    { "category": "policy_framing", "excerpt": "…" }
  ],
  "expected_confidence": "medium",
  "expected_propaganda": ["fear_appeal"],
  "rationale": "…",
  "mirror_of": null,
  "split": "dev" | "holdout",
  "review_state": "not_reviewed" | "in_review" | "reviewed" | "needs_second_review" | "resolved",
  "label_provenance": "human_blind" | "agent_drafted_human_reviewed" | "unreviewed",
  "reviewers": ["oniel"],
  "disagreement_note": null
}
```

`label_provenance` matters as much as the label. A label a person wrote with nothing in front of
them and a label a person accepted from a model's proposal are different measurements, and the
second is pulled toward agreement by anchoring. Only `human_blind` supports "agreement with our
reviewers" without a qualifier; `agent_drafted_human_reviewed` supports "agreement with a reviewer
who saw a proposal". The validator refuses to score `unreviewed`.

`acceptable_labels` matters. Scoring a "slightly left" prediction as wrong because the reviewer wrote
"center" manufactures a failure out of a legitimate disagreement between two adjacent bands. Band-
adjacent answers get partial credit; direction reversals do not.

---

## 2. Labeling protocol

Three rules, in order of how much damage breaking them does.

### 2.1 Write the guidelines before labeling

Not after. A written rubric for what counts as each category, what "strong" means, what pushes a case
to Unclear. Guidelines drafted after labeling are a description of what you already did.

### 2.2 Label blind

**Never label an example after seeing Frame's output on it.** The temptation is enormous and the
damage is total: the dataset stops measuring Frame and starts ratifying it, and you cannot tell from
the numbers that this happened. Blind labeling is the single most important rule here.

Practically: label in a pass that has no access to system output. If you need to revisit a label
after seeing a result, mark it `needs_second_review` and treat the change as a dataset change, not a
correction.

### 2.3 Keep a holdout split you do not tune against

- **dev** (~110) — iterate prompts freely.
- **holdout** (~40) — run rarely; a small number of times before launch, at most. Never tune against.

Without a holdout, prompt iteration overfits the eval set within a couple of weeks and the reported
numbers stop meaning anything. 50–100 examples are too few to split usefully, which is why the target
is **~150**.

If for some reason we run dev-only, every report must say **in-sample** in plain language. No
exceptions.

### 2.4 The single-annotator problem

One annotator means the metric is "agreement with Oniel," and Oniel has politics. This is a real,
unavoidable-at-MVP-scale limitation and it belongs in published material, not in a footnote.

Partial mitigations:

- ~25% of examples get a second reviewer. Where possible, someone whose politics differ.
- Disagreements are **recorded, not resolved away**. Inter-reviewer disagreement is a finding about
  the difficulty of the item, and items with high disagreement should be excluded from headline
  accuracy and reported separately.
- The point is not to prove humans are objectively right. It is to locate where reasonable people
  disagree — and Frame should be abstaining more often in exactly those places.

---

## 3. Composition

Aim for deliberate balance rather than whatever was convenient to collect:

| Bucket | Target |
|---|---|
| Left-leaning framing | ~20% |
| Right-leaning framing | ~20% |
| Center | ~15% |
| Unclear (political but insufficient) | ~15% |
| Non-political | ~10% |
| Mirror pairs (§4) | ~15% |
| Adversarial / injection | ~5% |

Must-have negative examples, because a naive prompt fails all of these:

- **Emotionally intense but not manipulative.** *"The attack killed 14 people, including children."*
- **Persuasive but not propaganda.** An ordinary op-ed argument with a clear thesis.
- **Short input.** An X post of 15 words that should not yield a confident read.
- **Sarcasm / satire** that should route to `unclear`.
- **Non-political with strong emotional language.** Product marketing, sports writing.
- **Fragmentary selection** — someone drag-selected nav chrome and half a paragraph.

---

## 4. Mirror tests

The most important instrument in this document, and the one the master plan did not have.

Frame's entire credibility dies the day someone demonstrates that structurally identical left- and
right-leaning passages get systematically different treatment. Language models have documented
directional asymmetries. A 150-example set labeled by one person cannot detect this on its own —
it has to be tested for directly.

### Method

For a subset of examples, hand-write a **polarity-swapped twin**: same rhetorical structure, same
loaded-language density, same sentence shapes — swapped actors, swapped policy direction.

```
A: "Republicans refused to consider the bill that would protect vulnerable families."
B: "Democrats refused to consider the bill that would protect taxpayers from overreach."
```

Link them with `mirror_of`. Then assert:

| Assertion | Failing means |
|---|---|
| Labels are symmetric in **magnitude** (`slightly_left` ↔ `slightly_right`) | directional bias in classification |
| Confidence is within one band | asymmetric certainty |
| Propaganda findings match in technique and count | asymmetric technique detection |
| Evidence categories match | asymmetric attention |

Mirror pairs are hand-written, not generated by swapping words mechanically — a mechanical swap
produces unnatural text that fails for the wrong reason.

### In production

The same concern, monitored live: track unclear rate, confidence distribution, and propaganda-flag
rate **bucketed by predicted direction**. If right-leaning content is flagged for propaganda at
three times the rate of left-leaning content, that is either a real finding about the sample or a
broken system — and we must know which before a user tells us.

---

## 5. Metrics

### 5.1 Evidence grounding — the hard gate

> Does every displayed excerpt exist in the submitted content?

**Target: 100%.** This is not an accuracy metric to be traded off; it is a product requirement. A
single fabricated excerpt in a shipped build is a release blocker, not a backlog item.

Measured as: displayed excerpts that are exact substrings of the normalized submission ÷ total
displayed excerpts.

Report alongside it: **evidence recovery rate** (model excerpts successfully located ÷ model excerpts
produced). Low recovery is not a correctness failure — the validator caught it — but it is a direct
measure of prompt quality and the earliest signal of model drift.

### 5.2 Abstention quality

Where reviewers said there was insufficient evidence, does Frame return `unclear`?

Report both directions:

- **Correct abstention** — reviewer unclear, Frame unclear. Good.
- **Over-abstention** — reviewer classified, Frame unclear. The product-killing direction.
- **Under-abstention** — reviewer unclear, Frame classified. The trust-killing direction.

Under-abstention is worse. But over-abstention is what makes people stop using the thing, so it does
not get to hide behind "abstention is a success."

### 5.3 Directional agreement

Where reviewers agreed meaningful framing exists, does Frame agree on **direction**? Band-adjacent
answers get partial credit via `acceptable_labels`. Direction reversals are counted separately and
prominently — they are qualitatively different from being one band off.

### 5.4 Propaganda agreement

Per-technique precision and recall. Precision matters far more: a false "fear appeal" on ordinary
advocacy is a much worse error than a missed one.

### 5.5 Mirror symmetry

Pass rate on the §4 assertions. Reported as its own headline number.

### 5.6 Operational

p50 / p95 latency, average cost per analysis, cache hit rate, `blocked` rate.

### 5.7 The one that actually matters

**Repeat usage.** Do the 2–3 testers come back unprompted? No benchmark substitutes for it.

---

## 6. The runner

`evaluation/runners/` — a CLI that takes a dataset split and a config fingerprint, runs Frame, and
writes a report to `evaluation/reports/<timestamp>-<fingerprint>.json` plus a markdown summary.

- Every report records the **full version set**, not just the fingerprint, and the dataset git SHA.
- Reports are committed. Comparing two runs should be a diff.
- Golden-file tests on the report format so a formatting change does not look like a quality change.
- The runner must be runnable against a **mocked model** so the harness itself can be tested without
  spending tokens.

Build it at step 11 of the build order, before Gemini is first connected. Twenty examples and a
scoreboard beat a hundred examples that arrive after six weeks of tuning by feel.

**Status (step 11): the harness is built, the dataset is empty.**

`evaluation/runners/frame_eval/` — records, metrics, report, CLI, validator. 25 tests, golden file
on the report format, runnable end to end against a mocked analyzer. `evaluation/README.md` has the
commands.

The dataset is empty on purpose. §2.2 requires blind human labeling, and labels written by an AI
would make this set measure a model's priors about political language while reporting nothing that
reveals it had happened. §2.4's "agreement with Oniel" is an honest, publishable limitation;
"agreement with a model" is not. `evaluation/dataset/GUIDELINES.md` is the rubric §2.1 requires —
drafted by Claude, for review, before labeling starts.

Two things the harness enforces that a summary writer could otherwise forget:

- **Grounding is measured by the runner**, which re-checks every displayed excerpt against the
  normalized submission. A system reporting its own grounding rate is not a measurement.
- **Zero displayed excerpts reports as `null`, not 100%.** A system that displays nothing must not
  be able to claim a perfect score on the hard gate.

---

## 7. Reporting honesty

Rules for anything published:

- Say the sample size. 150 examples is a small sample, and the confidence interval on a percentage
  from 150 items is wide. Do not present a 3-point movement as a result.
- Say "agreement with our reviewers," never "accuracy."
- Say which split. In-sample numbers are labeled in-sample.
- Publish mirror-symmetry results **including failures**. A published failure is worth more to the
  product's credibility than a withheld success.
- Never publish a metric whose computation is not in the repo.

---

## 8. Known limitations

- 150 examples cannot establish political symmetry, only fail to refute it. Mirror tests catch gross
  asymmetry, not subtle asymmetry.
- One primary annotator. Second review covers ~25%. The dataset encodes one person's judgment.
- **The first 18 records are `agent_drafted_human_reviewed`** (2026-09-30). Passages were collected
  by hand from real pages; the labels were drafted by an agent and then reviewed. That is not blind
  labeling, and anchoring means review pulls toward agreeing with the proposal. Any number computed
  from those records is agreement with a reviewer who saw a proposal. How much that costs is
  unmeasured — a blind re-label of a sample would measure it, and until someone does, the size of
  the effect here is unknown rather than small.
- No external ground truth exists for "how left-leaning is this paragraph." There is no gold standard
  to appeal to, only inter-reviewer agreement.
- The dataset is English, U.S.-political, and collected by one person, so it inherits whatever
  sampling bias that implies about which sources and topics appear.
- Holdout discipline is enforced by habit, not by tooling. If this slips even once, the holdout is
  gone and there is no way to detect it after the fact.
