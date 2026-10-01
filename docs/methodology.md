# Frame — Methodology

> **Owner of:** the product constitution, the analysis taxonomy, the status model, and the
> public statement of what Frame can and cannot do.
> Schema details live in [analysis-contract.md](analysis-contract.md). System design lives in
> [architecture.md](architecture.md).

This document is written to be published. Assume a hostile reader who wants to prove Frame is
biased garbage. Write nothing here we cannot defend.

---

## 1. The twelve rules

1. **Frame analyzes content, not people.**
2. **Frame does not determine truth.**
3. **Frame does not fact-check the submitted content.**
4. **Frame may use general political knowledge to interpret context, but classification evidence
   must come from the submitted content.**
5. **Frame cannot use evidence it cannot locate in the submitted content.**
6. **Frame must abstain when evidence is insufficient.**
7. **Center and Unclear are different outcomes.**
8. **Political framing and propaganda are independent dimensions.**
9. **Persuasion alone is not propaganda.**
10. **Emotionally intense subject matter is not automatically emotional manipulation.**
11. **Frame does not claim the author's personal political ideology.**
12. **Frame prefers a defensible Unclear over an unsupported classification.**

### What this forbids in output text

Frame may say *"This content exhibits slightly left-leaning framing."*

Frame may **not** say any of:

- "The author is left-wing / conservative / a partisan."
- "This publication is liberal."
- "The author believes X."
- "This claim is false."
- "The article failed to mention X." (see §4, omission is out of MVP scope)

The output must never name the outlet or the author. Not because of legal caution alone — because
naming them converts an analysis of text into a characterization of a person, which is Rule 1.

---

## 2. Status model

Four statuses. They are not degrees of the same thing; they are different outcomes.

| Status | Meaning | User-facing wording |
|---|---|---|
| `classified` | Sufficient validated evidence to place the content on the spectrum, **including at Center**. | the spectrum label |
| `unclear` | The content is political, but there is not enough defensible evidence for a directional read. | "Insufficient evidence to reliably determine political framing." |
| `non_political` | The content does not engage a political issue at all. | "No political framing detected." |
| `blocked` | The model refused or was filtered. An operational failure, not an analytical one. | "Frame couldn't analyze this passage." |

### Center vs. Unclear

- **Center** = there *is* enough evidence, and it does not materially favor a direction.
- **Unclear** = there is not enough evidence to say.

Collapsing these would mean a shrug and a considered neutral verdict look identical, which destroys
the meaning of both.

### Non-political vs. Unclear

The master plan routed non-political content to Unclear. That is wrong for the same reason Center
and Unclear are separate. Telling a user that *"the iPhone has a new camera sensor"* has **unclear
political framing** implies Frame examined it politically and got confused. `non_political` says the
true thing.

`blocked` exists so that model refusals never silently inflate the abstention metric. If a safety
filter blocks a passage about dehumanizing rhetoric — which is exactly the content Frame most needs
to analyze — that must show up as a reliability problem, not as correct abstention.

### Mixed signals

There is no "Mixed" user state. When directional evidence genuinely conflicts, the result is
`unclear`. Frame does not average opposing signals into a fake Center.

---

## 3. What the spectrum measures

> How far the submitted content's presentation appears to deviate from neutral political framing.

Internally `-1.0 … 0 … +1.0`, surfaced as:

```
Strongly Left · Left · Slightly Left · Center · Slightly Right · Right · Strongly Right
```

**Thresholds are not product assumptions.** They are calibrated against the evaluation dataset and
recorded in `scoring_version`. Do not hardcode a threshold anywhere except the scoring module.

**Open (Q1 in SYSTEM-CONTEXT):** the float is an internal calibration value. Publishing
`"score": -0.34` from a step function over ~4 discrete signals is fake precision, and it is exactly
the kind of unearned authority the product exists to argue against. Current default: the client API
returns a label; the spectrum needle position is derived from the label and documented as
presentational.

### Strength requirements per label

Directional confidence must scale with independent evidence, not with volume:

| Label band | Requires |
|---|---|
| Slightly Left / Right | At least one meaningful validated directional signal. |
| Left / Right | Multiple consistent signals. |
| Strongly Left / Right | Multiple **strong** signals across **independent categories**. |

Three loaded-language findings are one signal wearing three hats. Policy framing + loaded language +
viewpoint treatment is three signals. Only the second pattern can reach a strong label. Without this
rule, a single stylistic tic dominates the whole classification.

---

## 4. Taxonomy (MVP)

### Political framing

- **Policy framing** — how proposed political solutions are presented.
- **Government vs. individual responsibility** — where responsibility is located.
- **Characterization of political actors** — how politicians, parties, governments, groups are described.
- **Treatment of competing viewpoints** — how opposing positions are represented.
- **Argument emphasis** — which arguments and consequences get weight.

### Language

- **Loaded / evaluative language** — characterization beyond straightforward description
  ("refused" vs. "opposed").
- **Emotional language**
- **Fear-based framing**
- **Dehumanization**
- **Scapegoating**
- **Us-vs-them framing**
- **Division-oriented language**

### Structural

- **Selective presentation** — emphasis that materially affects framing, demonstrable within the selection.

### Excluded from MVP (ADR-0003)

- **Headline framing.** A text selection almost never contains the headline. Pulling the page
  `<title>` or `<h1>` to compare against would import context from outside the submission, breaking
  Rule 4. A category that can essentially never fire is an invitation for the model to invent one.
- **Demonstrable omission.** "What this text conspicuously leaves out, provable from the text alone"
  is the highest-hallucination category in the taxonomy and the one most likely to produce an
  indefensible claim — which is item 1 of the correctness hierarchy. Out until evaluation shows it
  can be grounded.

Both remain in `taxonomy_version` history so their future reintroduction is a versioned change.

---

## 5. Input rules

- **Maximum 5,000 characters.** The selection is treated as the entire content being analyzed.
- **No surrounding context is retrieved.** No thread, no replies, no author profile, no linked
  article, no page content outside the selection, no search, no fact-check.
- **Soft floor at ~40 words** (Q3). Below it, Frame does not hard-reject — X posts are legitimately
  short — but the evidence bar rises and confidence is capped at **Medium**. A confident directional
  read of eight words is the most embarrassing failure mode available to us.
- The text analyzed is the **normalized** text (see [architecture.md](architecture.md#normalization)).
  Evidence offsets index into it, and the normalization is reversible back to the original selection.

### The political-context boundary

```
Political context   ←  general model knowledge   (allowed)
Classification evidence  ←  submitted content only   (required)
```

The model may know that "universal healthcare" sits in a particular political landscape. It may not
use anything outside the submission as *evidence*.

---

## 6. Evidence model

**Hard requirement:** Frame cannot classify content unless it can produce at least one defensible
piece of evidence located in the submitted content.

Every evidence item is:

```
category  →  exact excerpt (+ span)  →  interpretation
```

Example:

> **Policy framing**
> "Government must step in to protect vulnerable families."
> This presents government intervention as necessary rather than as one policy option among
> competing approaches.

### Validation is span recovery, not accept/reject

The model's excerpt is a *search query*, never the displayed text. The backend **locates** the
excerpt in the normalized submission and displays the source substring. Only when no span can be
recovered is the item rejected. Mechanics in
[architecture.md](architecture.md#evidence-validation).

This matters because naive exact-match discards good analysis over a curly quote, and because
recovering the span is what produces the `start` / `end` offsets that inline highlighting needs.

Semantic paraphrase is never evidence. If the model writes *"the government needs to protect
vulnerable families"* and the text says *"Government must step in to protect vulnerable families"*,
the displayed evidence is the second string or there is no evidence.

### Evidence strength

| Strength | Basis |
|---|---|
| Strong | Direct language clearly establishes the framing. |
| Moderate | A pattern across multiple parts of the content. |
| Weak | Indirect or contextual inference. |

A strong classification may not rest primarily on weak signals.

### Quantity

Free tier displays **the single strongest item**. Not three, not fifteen. Deep analysis later
reveals additional items, categories, propaganda evidence and limitations — as a structured report,
never as a chat.

---

## 7. Confidence

User-facing: **High / Medium / Low**. No percentages — a number implies statistical calibration we
do not have, and claiming calibration we lack is the exact sin the product is built against.

Confidence is a **deterministic pure function** of:

- count of independent validated evidence categories
- maximum evidence strength among survivors
- directional consistency across signals
- input length (short input caps at Medium)

Deterministic means versionable, unit-testable, and explainable. It lives in the scoring module
under `scoring_version` and is never emitted by the model.

---

## 8. Propaganda

A **separate axis**. Political framing is Left↔Right; propaganda is None → Low → Moderate → High
(internal). Neither determines the other. *Right-leaning with no propaganda indicators* and *Center
with propaganda indicators* are both perfectly valid results.

**MVP techniques:** fear appeal · dehumanization · scapegoating · us-vs-them framing · false
dilemma · emotional manipulation · other observable techniques.

### Wording

Never *"This is propaganda."* Always **"Potential propaganda indicators,"** then the named
techniques. This is the claim we can actually defend.

### Same evidence rule

A technique without a recoverable span in the submission is **not reported**. No exceptions, no
"low confidence" version of it.

### Two distinctions that must survive into the prompt

- **Emotionally intense ≠ emotional manipulation.** *"The attack killed 14 people, including
  children"* is disturbing. It is not manipulation. Manipulation requires observable presentation
  technique, not upsetting subject matter.
- **Persuasion ≠ propaganda.** *"We should lower taxes because government spending is inefficient"*
  is an argument. Frame may note the persuasive framing; it may not inflate ordinary political
  advocacy into a propaganda finding.

Both of these will be violated by a naive prompt. They need dedicated negative examples in the
evaluation set.

---

## 9. Fact vs. interpretation

Frame may label a statement as **interpretation**:

> The author attributes the economic improvement to the administration's policies.

Frame may not conclude the interpretation is false. That requires external evidence and is outside
scope (Rule 3).

---

## 10. Sarcasm, satire, memes

If sarcasm or satire makes the political reading unreliable, the result is `unclear`, with:

> This content may be sarcastic or satirical, making political framing unreliable to determine.

Abstention beats invented meaning. Always.

---

## 11. Correctness hierarchy

When optimizing, in strict order:

1. Don't fabricate evidence
2. Correctly abstain
3. Correct directional framing
4. Correct propaganda detection
5. Speed

A politically controversial product that confidently makes unsupported claims is worse than no
product.

### Product priority hierarchy

1. Ease of development · 2. Accuracy · 3. Privacy · 4. Cost · 5. Latency

A trustworthy 4-second analysis beats a fast unreliable one. A simple architecture beats premature
infrastructure.

---

## 12. Known limitations

Stated plainly, and intended for publication.

- **Frame analyzes only what you selected.** It has no access to the surrounding article, the
  thread, the author, or any linked source. A passage that reads as one-sided in isolation may be
  balanced in its full context. This is a deliberate design choice, and it is a real limitation.
- **Frame has no publication-level or author-level knowledge, by design.** It cannot tell you
  whether a source is generally reliable.
- **Frame does not check whether anything in the content is true.**
- **U.S. political framing, English only.** Applying it elsewhere will produce confident nonsense.
- **The spectrum is a model of framing, not a measurement.** There is no ground truth for "how
  left-leaning is this paragraph." Our reference point is a small set of human-labeled examples,
  and reasonable people disagree on many of them. Reported agreement figures are agreement with
  *our reviewers*, not with truth.
- **Political symmetry is monitored, not guaranteed.** Language models have documented directional
  asymmetries. We test for this explicitly (see [evaluation.md](evaluation.md#4-mirror-tests)) and
  publish what we find, including when we find a problem.
- **Headline framing and omission are not analyzed** (§4).
- **Content that attempts to manipulate the analyzer** is an open problem. See
  [threat-model.md](threat-model.md#1-prompt-injection).
- **Confidence labels are not calibrated probabilities.** "High" means several independent validated
  signals agreed, and nothing more.
