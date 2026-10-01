# ADR-0001 — Result surface is an in-page shadow-DOM overlay

**Date:** 2026-09-11 · **Status:** Accepted

## Context

The master plan specified `select text → right click → Frame It → popup`, where "popup" meant the
extension's action popup.

Two problems:

1. Opening the action popup programmatically from a context-menu click is not reliable.
   `chrome.action.openPopup()` is gesture-restricted and has behaved inconsistently across Chrome
   versions and platforms. The core interaction of the product would rest on it.
2. The action popup lives outside the page's DOM, so it can never highlight evidence inside the
   article text — and inline evidence highlighting is plausibly Frame's strongest eventual UX
   feature.

A content script is required regardless, because `info.selectionText` is not a safe source for a
5,000-character selection (see [architecture.md §2](../architecture.md#2-chrome-extension)).

## Decision

The analysis result renders in an **overlay injected into the page by the content script, inside a
shadow root**. The action popup is reduced to settings / about.

## Consequences

**Good**

- The core flow does not depend on an unreliable API.
- Same-DOM surface, so inline highlighting is reachable later without re-architecting.
- The DOM `Range` from selection capture is available as a highlighting anchor from day one.
- No additional permissions beyond what selection capture already requires.

**Bad**

- CSS isolation work. Host pages will attack the overlay's styling; `all: initial` on the shadow
  host is mandatory, and news sites will still find ways to interfere.
- Overlay positioning and dismissal behavior must be handled on pages we do not control, including
  pages with their own overlays, sticky headers and scroll-jacking.
- The overlay dies on navigation. State is lost; re-invoking should hit the cache and return
  instantly.

## Alternatives considered

- **`chrome.sidePanel`** — can legally be opened from a context-menu handler and survives navigation.
  Rejected as primary because it can never highlight in-page and permanently occupies screen width.
  **Retained as the fallback** if overlay isolation proves worse than expected.
- **Action popup as planned** — rejected for the reasons above.
- **Separate popup window** — works, but is a jarring interaction for a read-in-place tool.
