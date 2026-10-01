/**
 * MV3 service worker: context menu, selection capture, API call, overlay.
 *
 * The worker is ephemeral (~30s idle) and can be terminated mid-`fetch`
 * (architecture.md §2). The request is issued here anyway, because a content
 * script's fetch would carry the page's origin and force the API to allow
 * arbitrary origins. The mitigation the docs describe — a chrome.storage
 * handoff so a restarted worker can recover — is NOT built yet, deliberately:
 * a fix that cannot be reproduced cannot be tested. Since step 12 the call
 * takes seconds, so the failure is reachable; the reproduction recipe is in
 * apps/extension/docs/CONTEXT.md ("Where the request is issued").
 */
import { analyze, ApiError } from "../api/client";
import { getSettings } from "../settings";
import type { FrameSelection, SelectionMeasurement } from "../types";

const MENU_ID = "frame-it";
const MEASUREMENT_HISTORY_LIMIT = 20;

console.log("[Frame] service worker loaded", new Date().toISOString());

async function setBadge(text: string, color: string): Promise<void> {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: MENU_ID, title: "Frame It", contexts: ["selection"] });
  });
});

/**
 * Runs in the page. Self-contained — executeScript serializes it, so it closes
 * over nothing and returns only structured-cloneable data. A live DOM Range
 * cannot cross this boundary; the rect is captured as the future highlight
 * anchor.
 */
function readSelection(): FrameSelection {
  const selection = window.getSelection();
  const text = selection?.toString() ?? "";

  let rect: FrameSelection["rect"] = null;
  if (selection && selection.rangeCount > 0) {
    const box = selection.getRangeAt(0).getBoundingClientRect();
    rect = { top: box.top, left: box.left, width: box.width, height: box.height };
  }

  return {
    text,
    length: text.length,
    newlineCount: (text.match(/\n/g) ?? []).length,
    rangeCount: selection?.rangeCount ?? 0,
    rect,
  };
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== MENU_ID) return;
  if (typeof tab?.id !== "number") return;
  void handleFrameIt(info, tab);
});

async function handleFrameIt(
  info: chrome.contextMenus.OnClickData,
  tab: chrome.tabs.Tab,
): Promise<void> {
  const tabId = tab.id as number;
  const menuText = info.selectionText ?? "";

  let results: chrome.scripting.InjectionResult<FrameSelection>[];
  try {
    results = await chrome.scripting.executeScript({
      // allFrames: a selection inside an iframe is invisible to the top frame.
      target: { tabId, allFrames: true },
      func: readSelection,
    });
  } catch (error) {
    console.error("[Frame] executeScript failed", error);
    await setBadge("ERR", "#B3261E");
    return;
  }

  const capture = results
    .map((entry) => entry.result)
    .find((result): result is FrameSelection => !!result && result.length > 0);

  if (!capture) {
    await setBadge("0", "#B3261E");
    return;
  }

  await recordMeasurement(menuText, capture, results.length);
  await setBadge("...", "#666666");

  await mountOverlay(tabId);
  await send(tabId, { type: "FRAME_LOADING", pending: { charCount: capture.length } });

  const settings = await getSettings();
  try {
    const response = await analyze(settings.apiBaseUrl, capture.text);
    await send(tabId, { type: "FRAME_RESULT", response });
    await setBadge("", "#1B5E20");
    console.log("[Frame] analysis", response.status, response.analysis_id);
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "Something went wrong analyzing this selection";
    console.error("[Frame] analyze failed", error);
    await send(tabId, { type: "FRAME_ERROR", message });
    await setBadge("ERR", "#B3261E");
  }
}

async function mountOverlay(tabId: number): Promise<void> {
  // Re-injection is safe; the content script guards re-entry itself.
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
}

async function send(tabId: number, message: unknown): Promise<void> {
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch (error) {
    // The tab navigated or the overlay is gone. Not worth failing the flow over.
    console.warn("[Frame] overlay unreachable", error);
  }
}

/**
 * Stage 04 measurement, kept running. It costs one string comparison and it is
 * the early-warning signal if a Chrome update changes selectionText's behavior
 * — the measured finding (U+000A becomes U+0020) was taken on one build.
 *
 * Only lengths and character codes are stored. No page URL and no selected
 * text: a history of where someone used Frame is browsing history, and this
 * extension has no business keeping one.
 */
async function recordMeasurement(
  menuText: string,
  capture: FrameSelection,
  framesProbed: number,
): Promise<void> {
  let firstDivergence: SelectionMeasurement["firstDivergence"] = null;
  let divergenceCount = 0;
  if (capture.length === menuText.length) {
    for (let i = 0; i < menuText.length; i += 1) {
      if (menuText[i] !== capture.text[i]) {
        divergenceCount += 1;
        firstDivergence ??= {
          index: i,
          menuCharCode: menuText.charCodeAt(i),
          pageCharCode: capture.text.charCodeAt(i),
        };
      }
    }
  }

  const measurement: SelectionMeasurement = {
    measuredAt: new Date().toISOString(),
    menuSelectionTextLength: menuText.length,
    menuNewlineCount: (menuText.match(/\n/g) ?? []).length,
    pageSelectionLength: capture.length,
    pageNewlineCount: capture.newlineCount,
    truncated: menuText.length < capture.length,
    whitespaceCollapsed: capture.newlineCount > (menuText.match(/\n/g) ?? []).length,
    framesProbed,
    firstDivergence,
    divergenceCount,
  };

  const stored = await chrome.storage.local.get("measurements");
  const history: SelectionMeasurement[] = Array.isArray(stored.measurements)
    ? stored.measurements
    : [];
  history.unshift(measurement);
  await chrome.storage.local.set({ measurements: history.slice(0, MEASUREMENT_HISTORY_LIMIT) });
}
