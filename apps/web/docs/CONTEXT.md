# Web — Context

> Spoke doc. Hub is [../../../SYSTEM-CONTEXT.md](../../../SYSTEM-CONTEXT.md).

**Status:** not started. Deliberately the smallest thing in the repo for the MVP.

---

## Stack

Next.js · React · TypeScript, on Vercel.

## MVP scope

A landing page. That is the whole scope.

```
Frame
Political framing, made transparent.

[ Install Chrome Extension ]
```

Plus the pages that the extension and the Web Store submission actually require:

- **`/methodology`** — published from [../../../docs/methodology.md](../../../docs/methodology.md).
  The twelve rules, the taxonomy, and the known-limitations section, unedited. This page is the
  answer to "why should I trust an AI telling me something is Left or Right," and it is a product
  feature, not marketing.
- **`/privacy`** — required for Web Store submission. Must reflect the qualifications in
  [../../../docs/threat-model.md §3](../../../docs/threat-model.md#3-privacy), including that cached
  analyses contain verbatim excerpts. An unqualified "we never store your content" claim would be
  false.

## Not in MVP

Paste-to-analyze, URL analysis, accounts, history, saved analyses, dashboards, the newspaper
aesthetic. The visual identity comes after the analysis engine works, not before.

## Known limitations

- No web client for analysis yet, so the only way to use Frame is the extension.
- The methodology page is a manual publish of the repo doc until something automates it. They will
  drift; check before any launch.
