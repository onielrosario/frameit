import type { AnalysisResponse } from "./api/contract";

/**
 * Stage 04 measurement types.
 *
 * These exist to answer one question the docs flag as a blocker: how much of a
 * selection does Chrome hand to a context-menu handler via
 * `OnClickData.selectionText`? See docs/architecture.md §2 and
 * apps/extension/docs/CONTEXT.md.
 *
 * Nothing here is part of the Frame API contract. That contract is owned by
 * docs/analysis-contract.md and mirrored in ./api/contract.ts.
 */

/** What a single frame reports about its own selection. */
export interface FrameSelection {
  /** window.getSelection().toString() — the authoritative text. */
  text: string;
  /** text.length, carried separately so callers need not re-measure. */
  length: number;
  /** Newlines survive here but are collapsed in selectionText. Measured, not assumed. */
  newlineCount: number;
  rangeCount: number;
  /** Bounding box of range 0, in viewport coordinates. The future overlay anchor. */
  rect: { top: number; left: number; width: number; height: number } | null;
}

/** One recorded comparison between the two selection sources. */
export interface SelectionMeasurement {
  measuredAt: string;
  /** info.selectionText.length as delivered to the context-menu handler. */
  menuSelectionTextLength: number;
  menuNewlineCount: number;
  /** window.getSelection().toString().length read from the page. */
  pageSelectionLength: number;
  pageNewlineCount: number;
  /** True when the menu source delivered less text than the page holds. */
  truncated: boolean;
  /** True when newlines present in the page selection are absent from the menu source. */
  whitespaceCollapsed: boolean;
  /** Frames that executeScript reached, for the allFrames sanity check. */
  framesProbed: number;
  /**
   * First index at which the two sources disagree character-for-character, with
   * the code unit each one holds there. Null when they are identical or when the
   * lengths differ (in which case truncation, not substitution, is the story).
   *
   * Equal lengths plus a non-null divergence means Chrome SUBSTITUTED characters
   * rather than dropping them — the failure mode a length check cannot catch.
   */
  firstDivergence: { index: number; menuCharCode: number; pageCharCode: number } | null;
  /** How many positions differ. Only meaningful when the lengths match. */
  divergenceCount: number;
}

/** What the overlay shows while the request is in flight. */
export interface OverlayPending {
  charCount: number;
}

/**
 * Background -> content script messages.
 *
 * A discriminated union so the overlay renders exactly one state and an
 * unhandled variant is a type error rather than a blank panel.
 */
export type FrameMessage =
  | { type: "FRAME_LOADING"; pending: OverlayPending }
  | { type: "FRAME_RESULT"; response: AnalysisResponse }
  | { type: "FRAME_ERROR"; message: string };
