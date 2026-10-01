/**
 * Typed client for the Frame API.
 *
 * Called only from the service worker. A content script's fetch carries the
 * PAGE's origin, which would force the API to allow arbitrary origins; the
 * worker's fetch carries the extension origin, which is pinned and allowlistable
 * (see the `key` in manifest.json).
 */
import { isAnalysisResponse, type AnalysisResponse } from "./contract";

export const CLIENT_VERSION = "0.1.0";

/** Distinguishes "the API said no" from "the API never answered". */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function analyze(
  baseUrl: string,
  content: string,
  options: { timeoutMs?: number } = {},
): Promise<AnalysisResponse> {
  // Above the API's own 25s model timeout, so a slow model surfaces as the
  // API's 504 with a real message rather than as a client-side abort.
  const { timeoutMs = 30_000 } = options;

  const url = new URL("/analyze", baseUrl);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        source: "chrome",
        // Sent on every request and recorded in telemetry. Without it, a
        // regression affecting only old clients is invisible (§7).
        client_version: CLIENT_VERSION,
      }),
      signal: controller.signal,
    });
  } catch (error) {
    const aborted = error instanceof Error && error.name === "AbortError";
    throw new ApiError(
      aborted ? `No response within ${timeoutMs / 1000}s` : "Could not reach the Frame API",
      null,
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new ApiError(await describeFailure(response), response.status);
  }

  const body: unknown = await response.json();
  if (!isAnalysisResponse(body)) {
    throw new ApiError("The API returned a response this client cannot read", response.status);
  }
  return body;
}

async function describeFailure(response: Response): Promise<string> {
  if (response.status === 413) return "Selection is too long for Frame to analyze";
  if (response.status === 503) return "Frame is unavailable right now. Try again shortly.";
  if (response.status === 504) return "Frame took too long to analyze this selection";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Body was not JSON. The status alone is the whole story.
  }
  return `Frame API returned ${response.status}`;
}
