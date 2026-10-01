# ADR-0003 — Exclude headline framing and demonstrable omission from the MVP taxonomy

**Date:** 2026-09-11 · **Status:** Accepted

## Context

The master plan's structural taxonomy had three categories: headline framing, selective presentation,
and demonstrable omission. Two of them do not survive contact with the MVP's own constraints.

**Headline framing** compares a headline against a body. But the MVP input is a text selection, and a
selection almost never includes the headline. Reaching for the page `<title>` or `<h1>` to supply one
would import context from outside the submission, which breaks Rule 4 and the no-surrounding-context
principle the product is built on. The category can essentially never fire legitimately — which means
its main effect is to invite the model to produce one anyway.

**Demonstrable omission** — "what this text conspicuously leaves out, provable from the text alone" —
is the hardest thing in the taxonomy to ground. Omission is by definition not present in the text, so
there is no span to recover, and span recovery is the mechanism that makes every other category
defensible. It is the category most likely to produce an indefensible claim, which is item 1 of the
correctness hierarchy.

## Decision

The MVP structural taxonomy contains **selective presentation** only. Headline framing and
demonstrable omission are excluded.

Both stay in `taxonomy_version` history so reintroducing either is a versioned, deliberate change
rather than a quiet expansion.

## Consequences

**Good**

- Removes the two categories with the worst evidence-grounding properties.
- Shrinks the prompt and the enum surface.
- Removes a whole class of claim ("the article failed to mention X") that Frame cannot defend and
  that reads as a fact-check — the thing Frame explicitly is not.

**Bad**

- Frame will miss real headline-vs-body framing, which is one of the more legible forms of bias to a
  general reader, and a thing users may expect it to catch.
- Both are documented as known limitations in [methodology.md §12](../methodology.md#12-known-limitations),
  which is the honest handling but does not make the gap disappear.

## Revisit when

- **Headline framing:** when full-article extraction exists and the headline is part of a structured
  submission with its own span space. That is the context where the category is actually groundable.
- **Demonstrable omission:** only if evaluation demonstrates it can be grounded — most plausibly by
  restricting it to omissions provable *within* the selection (e.g. a named claim that the text
  promises to support and then does not), rather than omissions relative to the world.
