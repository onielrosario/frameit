# Chrome Extension — Context

> Spoke doc. Hub is [../../../SYSTEM-CONTEXT.md](../../../SYSTEM-CONTEXT.md).
> Architecture decisions live in [../../../docs/architecture.md §2](../../../docs/architecture.md#2-chrome-extension).
> The API contract is owned by [../../../docs/analysis-contract.md](../../../docs/analysis-contract.md) — do not restate it here.

**Status:** build stages 1-7 implemented; step 12 removed the mock selector. The extension calls
the development API, which now calls Gemini. The service-worker handoff is **still not built** — see
[Where the request is issued](#where-the-request-is-issued).

---

## Stack

Manifest V3 · TypeScript · React · Vite. No Plasmo, no Redux, no extension framework.

Build: `npm run build --workspace apps/extension` from the repo root, output in `dist/`.
`vite.config.ts` emits two entries — `popup.html` and `background.js` — and
`scripts/postbuild.mjs` copies `manifest.json` alongside them. Load `dist/` as an unpacked
extension; the package root is not loadable.

## Shape

| Piece | Role |
|---|---|
| `background/` | service worker: context menu registration, click handling |
| `content/` | shadow-DOM overlay mount. **Not declared in `content_scripts`** — the background injects `content.js` with `executeScript({ files })` on user gesture, which is what keeps `host_permissions` out of the manifest. Guards re-entry, since injecting a file twice re-executes it. |
| `popup/` | settings / about only — **not** the result surface (ADR-0001) |
| `api/` | typed client + a mirror of the response contract. Every enum is widened with `(string & {})` so an unknown value from a newer API degrades to a generic rendering instead of crashing — §7, written on day one rather than after the first incident. |
| `types/` | generated/mirrored contract types |

## Permissions

Each one is justified here before it goes in the manifest.

| Permission | Why | Could we drop it? |
|---|---|---|
| `contextMenus` | The entire MVP interaction is a context-menu item. | No. |
| `scripting` | Reads the selection with `executeScript`, and mounts the overlay at stage 05. | No. |
| `activeTab` | Grants access to the current tab **on user gesture only**. A context-menu click is such a gesture. This is what lets us avoid `host_permissions: ["<all_urls>"]`, which is a Web Store review problem and a trust problem. | No — it is the cheap alternative. |
| `storage` | Settings (API base URL), and the last 20 selection-length measurements — numbers only, **no page URLs and no selected text**. Will carry the service-worker handoff described in architecture.md §2. | No — settings need it. |

No `host_permissions`. No `tabs` (we get the tab from the context-menu callback).

### Stable dev extension ID

`key` is pinned in `manifest.json`, so the unpacked extension always loads at the same origin:

```
chrome-extension://bjmnmjlmiffncikflnabhbnjgipfkipo/
```

That is the origin the API's CORS allowlist will name at stage 06. The private key that generates
it lives at `apps/extension/key.pem` and is **gitignored** — it is not in the repo and never will
be. Losing it changes the dev extension ID, which is an annoyance, not a disaster: regenerate and
update this doc. The Web Store issues its own ID at publication and does not use this key.

## Measured facts

Fill these in as they are measured. Do not carry an unmeasured number forward as if it were measured.

| Fact | Expected | Measured | Date |
|---|---|---|---|
| `info.selectionText` max length | ~1,024 chars (undocumented folklore) | **no truncation at 5,000** — delivered all 5,000 chars of block A | 2026-09-11 |
| `window.getSelection()` max length | no limit expected | 5,000 chars, matching the source exactly | 2026-09-11 |
| `selectionText` newline handling | newlines collapsed | **substituted, not collapsed** — each U+000A becomes U+0020; length unchanged (block B: 1,606 chars both, 6 newlines vs 0, 6 differing positions, first at index 400) | 2026-09-11 |
| Cold-path end-to-end latency | — | — | — |

Measured on macOS, Chrome version **not yet recorded** — fill in from `chrome://version`. The
fixture was served over `http://localhost`, not `file://`.

### What the block B result means

`selectionText` is **character-lossy at identical length**. Block B is 1,606 characters in both
sources. `getSelection()` reports 6 newlines; `selectionText` reports 0 — and a character-level
comparison finds exactly 6 differing positions, the first at index 400, where the page holds
U+000A and the menu payload holds U+0020.

So the substitution is newline → space, one for one. Nothing is dropped, nothing is merged, and
**a length check cannot detect it**. Any validator that compares `len(evidence)` against
`len(source)`, or that trusts character offsets computed on one source and applied to the other,
would pass this and still be displaying text that does not appear in the submission.

**Corrected at step 09.** This said the substitution was disqualifying on its own. It is not: the
backend normalizer collapses whitespace runs, so U+000A and U+0020 land on the same single space and
both sources produce identical normalized text and `content_hash`
(`services/api/tests/test_normalize.py::test_selection_text_substitution_survives_normalization`).

The narrower true statement: equal-length character substitution defeats cheap integrity checks, so
such a source is only safe where something downstream provably erases the difference. Only U+000A
was present to test — a substitution the normalizer does not fold would break the exact-substring
rule silently, and nobody has looked for one.

Not established: whether other characters are also substituted (tabs, non-breaking spaces,
zero-width joiners, CRLF sources). Only U+000A was present to test. Anything else is unmeasured.

### What the block A result means

The folklore figure is **wrong at this size**, on this Chrome, on this platform. `selectionText`
carried the full 5,000 characters, which is the product's entire input ceiling, so truncation is
not a reason to avoid it.

This does **not** reverse the design. Reading from the page stays, for the reasons that survive:
the DOM `Range` is the future highlighting anchor and `selectionText` cannot produce one, and
`allFrames` coverage of iframe selections is not something the menu payload gives us. What changes
is the *justification* — `architecture.md` §2 currently leads with truncation, and that argument is
now measured false. The remaining arguments are the real ones.

Not established by this measurement: where the limit actually is above 5,000, whether it differs on
Windows or Linux, and whether it differs across Chrome versions. None of those matter while the
input cap is 5,000, and none should be asserted without measuring.

**The selectionText measurement is a Stage 4 blocker.** The whole selection-capture design
depends on this number and it is not documented by Google.

### How to run it

1. Build, then load `apps/extension/dist` at `chrome://extensions` with Developer mode on.
2. Open `apps/extension/test-fixtures/selection-truncation.html`. Over `file://` this needs
   "Allow access to file URLs" enabled for the extension, or serve the folder over `http://`
   instead.
3. Click **Select block A** — exactly 5,000 characters in one paragraph, selected
   programmatically so the run is reproducible. The bar at the bottom of the page reports what
   the page itself thinks is selected.
4. Right click inside the selection, choose **Frame It**.
5. Read the result in the extension popup, or in the service worker console
   (`chrome://extensions` → Frame It → "service worker").
6. Repeat with **Select block B** — four paragraphs — to see whether newlines survive
   `selectionText`. Chrome is documented nowhere on this either; the fixture's own readout is the
   reference count, not the number predicted in any doc.
7. Record what you measured in the table above, with the Chrome version.

The comparison is `info.selectionText.length` (what the context-menu handler receives) against
`window.getSelection().toString().length` (read from the page via `executeScript`). Both numbers,
plus newline counts and the frame count, are written to `chrome.storage.local` under
`measurements`.

## Where the request is issued

From the **service worker**, not the content script. A content script's `fetch` carries the page's
origin, which would force the API to allow arbitrary origins; the worker's carries the extension
origin, which is pinned by `key` and allowlistable.

The worker is ephemeral and can be terminated mid-`fetch` (architecture.md §2). The `chrome.storage`
handoff that would let a restarted worker recover is **not built**. That is deliberate: a fix that
cannot be reproduced cannot be tested.

**Step 12 status:** the failure is now *reachable* — the call takes seconds, not microseconds — but
it has **not been reproduced**. Reproducing it needs a person at Chrome, so it was not done in the
step-12 session. The recipe:

1. Load the rebuilt extension, API running with a real key.
2. Open `chrome://extensions` → Frame → **service worker** (DevTools for the worker).
3. Frame It on a long passage. While the badge shows `...`, go to DevTools → Application → Service
   workers → **Stop**.
4. Record what happens: does the overlay stay on "loading" forever, does the result still arrive, is
   there a console error? Also record whether a normal multi-second call ever dies on its own.

If the overlay hangs, the handoff is the fix: write `{requestId, tabId, startedAt}` to
`chrome.storage.session` before the fetch; on worker start, find stale entries and send the overlay
`FRAME_ERROR` (or retry). If the result always arrives, record that here and close the item —
Chrome keeping the worker alive through a pending fetch would make the handoff unnecessary.

## Settings

`chrome.storage.local`, edited in the popup:

| Setting | Default | Notes |
|---|---|---|
| `apiBaseUrl` | `http://localhost:8000` | Must appear in the API's CORS allowlist. |

## Overlay

Mounted by `src/content/index.ts`, rendered by `src/content/Overlay.tsx`.

- The host element gets `all: initial` **before** anything else is set on it. Without that, page
  rules matching `div`, `[id]`, or `*` inherit straight through the shadow boundary.
- Styles live in `overlay.css`, imported with Vite's `?inline` and injected as a `<style>` inside
  the shadow root — not as a separate stylesheet file, which a content script cannot load without
  making it web-accessible.
- Appended to `document.documentElement`, not `body`: some pages replace or restyle `body` wholesale.
- Built by `vite.content.config.ts` as a **single IIFE** with no code splitting. A classic injected
  script cannot carry `import` statements. Verified in `dist/content.js`.
- Background sends `{ type: "FRAME_RESULT", payload }` after `executeScript` resolves. That
  resolution happens only once the file has finished executing, so the message listener is always
  registered before the message is sent.

## Build stages

Incremental, so that Chrome APIs + React + Vite + API + Gemini are never debugged simultaneously.

1. Extension loads — **built**
2. Popup renders — **built** (about + temporary measurement readout)
3. Context menu "Frame It" appears and fires — **built**
4. Capture selection — **built**; the measurement itself is **not yet run**
5. Render captured text in the shadow-DOM overlay — **built**
6. Call the development API — **built**
7. Render a real analysis — **built**
8. Handle loading / error / unclear / blocked states — **built**, except retry
9. Package
10. Web Store submission

## Gotchas to carry

- **Service worker is ephemeral** (~30s idle) and can die mid-`fetch`. Do not own the LLM request
  from the worker without a `chrome.storage` handoff.
- **`allFrames: true`** on `executeScript` — a selection inside an iframe is invisible to the top frame.
  Take the first non-empty result.
- **`all: initial`** on the shadow host, or host-page CSS bleeds into the overlay.
- **Pin `key` in `manifest.json`** for a stable dev extension ID, so the API's CORS allowlist does
  not need editing on every reload.
- **No `eval`** — MV3 CSP. Vite's dev HMR must not end up in the built extension.
- **Tolerate unknown enum values** from the API without crashing. Users run stale builds for weeks.
- **Permissions stay minimal** and each one is justified here before it is added.

## Packaging and Web Store submission

Build stages 9 and 10. Not started — written now because two of these constraints affect decisions
made earlier, and discovering them at submission time is expensive.

### The package

`npm run build:extension` produces `apps/extension/dist`. The uploaded artifact is a **zip of the
contents of `dist`**, not of the folder itself — `manifest.json` must sit at the zip root. `dist` is
gitignored, so packaging is a release step, never a committed artifact.

### Account

A Chrome Web Store developer account requires a **one-time** registration fee — Google's registration
page confirms it is one-time but does not state the amount there; it is widely reported as **$5**,
covering up to 20 extensions. Use a dedicated email you check often: **it cannot be changed after
the account is created**.

### The `key` field is a submission hazard

`manifest.json` pins `key` so the unpacked dev extension keeps a stable origin. On upload the store
dashboard has been observed **rejecting manifests containing `key`**, inconsistently — some
developers succeed on a retry, others must strip it. After first publication the field is
unnecessary, because the store has locked the ID.

The consequence for Frame: **the published extension ID may differ from the pinned dev ID**, and the
API's CORS allowlist names that ID. `FRAME_CORS_ALLOWED_ORIGINS` is a comma-separated list precisely
so both can be present. Add the published ID before the first real user loads the extension, or
every request fails CORS with no visible cause on the page.

### Review

Submission requires a privacy policy URL (`/privacy` on the web app, per
[apps/web/docs/CONTEXT.md](../../web/docs/CONTEXT.md)) and a justification for **each** permission.
Frame requests four — `contextMenus`, `scripting`, `activeTab`, `storage` — and the table above is
the justification, written before each was added. Requesting no broad host permissions is the single
biggest lever on review friction.

Review time is not predictable and is not something to schedule a launch around.

## Known limitations

- **The overlay bundle is 248 KB** (57 KB gzipped), almost entirely React. It is injected only on
  user gesture, never on page load, so no page pays for it unless Frame is invoked there. If that
  stops being acceptable, the overlay is small enough to rewrite without React — the measurement is
  recorded here so that trade is made against a number rather than a feeling.
- **The overlay is positioned fixed at top-right, not anchored to the selection.** The captured
  rect is viewport-relative and goes stale on scroll, and anchoring on sites with sticky headers or
  scroll-jacking is unsolved. Provisional, and revisit when the result content is real.
- **The client cannot verify that `excerpt` matches `span`.** §5 says a client finding them in
  disagreement should treat the response as corrupt — but spans index the *normalized* content and
  the client only holds the original selection. The check becomes possible when the response carries
  `content_hash` (§5, "add before v1") or the normalized text. Today the excerpt is displayed on
  trust. Worth knowing, because it is the one guarantee the client currently cannot enforce for
  itself.
- **A live DOM `Range` cannot cross the `executeScript` boundary.** Results are structured-cloned,
  so the injected function can only return the range's *geometry*, not the range. Stage 05 must
  re-derive the `Range` inside the content script that owns the overlay. The capture path records
  the bounding rect today so the anchor exists from day one, but that rect is viewport-relative and
  goes stale on scroll.
- **Selection capture uses `executeScript`, not a declared content script.** That is what keeps
  `host_permissions` out of the manifest, but it also means nothing runs on the page until the user
  invokes the menu. Anything needing page state *before* invocation will force a redesign here.
- **`file://` pages need "Allow access to file URLs"** enabled per-extension. This affects the test
  fixture, not real use.
- The overlay is lost on navigation. Re-invoking should hit the cache and return instantly.
- Sites with aggressive overlays, sticky headers or scroll-jacking will fight the overlay's
  positioning. No general solution; handle cases as they appear.
- No highlighting yet. The DOM `Range` is captured from day one so it can be added without rework.
