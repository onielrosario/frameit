# Labeling guidelines

> **Draft for review.** Written by Claude from [docs/methodology.md](../../docs/methodology.md) and
> [docs/evaluation.md](../../docs/evaluation.md). It is a rubric, not labels — the labels are yours.
>
> §2.1 requires guidelines to exist **before** labeling starts, because guidelines drafted afterwards
> are a description of what you already did. Revise this first, then label. Every revision after
> labeling begins is a dataset change, not a correction.

---

## Why Claude did not label the examples

§2.2 says label blind: never label an example after seeing Frame's output on it. An AI writing the
labels that will judge an AI breaks that rule in the worst available way — the dataset would stop
measuring Frame and start ratifying a model's priors about what left- and right-leaning text looks
like, and **nothing in the numbers would show it had happened**.

§2.4 already names the real limitation: one annotator means the metric is "agreement with Oniel."
That is honest and publishable. "Agreement with a model" is neither.

So the passages and their labels are collected by you. Claude can help with the mechanics — format
validation, mirror-pair bookkeeping, composition counts — and with drafting **non-political**
filler, which carries no directional judgment. Ask explicitly if you want that.

---

## Before you start

1. Read [methodology.md §3–§4](../../docs/methodology.md) — the spectrum and the taxonomy.
2. Decide your sources for the first 20 and write them down. Whatever you reach for first is your
   sampling bias; naming it is cheaper than pretending it is absent.
3. Label in one pass with no system output visible. Close the extension.

---

## What each field means

| Field | How to fill it |
|---|---|
| `input` | The passage exactly as a user would have selected it. Do not tidy it. Ragged selections are real inputs. |
| `expected_status` | `classified` only if you can point at the evidence. `unclear` when it is political but the evidence is thin. `non_political` when the passage is not about a political issue. |
| `expected_label` | Only for `classified`. Use the strength table below. |
| `acceptable_labels` | **Always include `expected_label`, plus any band you would not argue with.** This is what stops a legitimate one-band disagreement being scored as a failure. |
| `expected_evidence` | Excerpts must be **exact substrings of `input`**. If you cannot quote it, it is not evidence. |
| `expected_confidence` | Your confidence in your own label, not a prediction of Frame's. |
| `expected_propaganda` | Empty unless a technique is clearly present. See the precision note below. |
| `rationale` | One or two sentences, written before seeing any output. This is what makes a disagreement reviewable later. |
| `mirror_of` | The id of the polarity-swapped twin, on both records. |

## Strength requirements (methodology §3)

| Label band | Requires |
|---|---|
| Slightly Left / Right | At least one meaningful directional signal. |
| Left / Right | Multiple consistent signals. |
| Strongly Left / Right | Multiple **strong** signals across **independent categories**. |

Three loaded-language findings are one signal wearing three hats. Policy framing + loaded language +
viewpoint treatment is three. Only the second can reach a strong label.

## What pushes a case to `unclear`

- Under ~40 words with a single weak signal.
- Sarcasm or satire where the literal reading inverts the intent.
- A fragmentary selection — nav chrome, half a sentence, a caption.
- Political topic, neutral presentation. **Reporting a policy is not framing it.**

`unclear` is a successful outcome, not a failure. But it must still carry what you observed — an
`unclear` that shows nothing is a product failure (§6).

## Propaganda: precision over recall

A false "fear appeal" on ordinary advocacy is a much worse error than a missed one. Tag a technique
only when you could defend it to someone who disagrees with the passage's politics. Emotionally
intense is not the same as manipulative: *"The attack killed 14 people, including children"* is a
fact stated plainly.

## Mirror pairs (§4)

Hand-write the twin: same rhetorical structure, same loaded-language density, same sentence shapes —
swapped actors and policy direction. **Do not mechanically swap words**; mechanical swaps produce
unnatural text that fails for the wrong reason.

Write the twin *immediately* after the original, before labeling anything else. Coming back later
means writing it with the original's label already in mind.

## The first 20

Composition targets in §3 describe the full ~150. For the first 20, breadth beats proportion — the
point is that prompt iteration starts with a scoreboard, not that the scoreboard is complete.
Aim to cover: both directions, at least one center, at least two `unclear`, at least two
`non_political`, at least one mirror pair, and at least one of each must-have negative in §3
(emotionally intense but not manipulative; persuasive but not propaganda; short input; sarcasm;
non-political with strong emotional language; fragmentary selection).

Mark everything `"split": "dev"`. Do not start the holdout until you have enough examples that
splitting is meaningful — a 5-example holdout measures nothing and burns the discipline.

## Validating what you wrote

```
PYTHONPATH=services/api:evaluation/runners python -m frame_eval.validate
```

Checks the record format, that every `expected_evidence` excerpt really is a substring of its
`input`, that mirror pairs point at each other, and prints composition counts against §3.
It does not check whether your labels are any good. Nothing can.
