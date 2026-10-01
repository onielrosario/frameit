/**
 * Tests for the parsing layer.
 *
 * Contract §7 requires clients to tolerate unknown enum values on day one,
 * because users run stale builds for weeks and a new taxonomy category must
 * degrade to a generic rendering rather than a blank screen. That requirement
 * is only real if something checks it.
 *
 * Pure functions only — no DOM, no jsdom. The render path is checked by hand.
 */
import { describe, expect, it } from "vitest";
import { evidenceOf, humanize, isAnalysisResponse, showsConfidence } from "./contract";

describe("humanize", () => {
  it("renders a known label", () => {
    expect(humanize("slightly_left")).toBe("Slightly left");
  });

  it("renders a label this build has never seen", () => {
    // The whole point: a category shipped by a newer API must still display.
    expect(humanize("some_future_taxonomy_value")).toBe("Some future taxonomy value");
  });

  it("survives an empty string without throwing", () => {
    expect(humanize("")).toBe("");
  });
});

describe("isAnalysisResponse", () => {
  it("accepts a minimal valid response", () => {
    expect(isAnalysisResponse({ api_version: "0", analysis_id: "an_1", status: "classified" })).toBe(
      true,
    );
  });

  it("accepts a status this build does not know", () => {
    // Tolerated at the guard; the renderer falls back to a generic view.
    expect(
      isAnalysisResponse({ api_version: "1", analysis_id: "an_1", status: "partially_framed" }),
    ).toBe(true);
  });

  it.each([null, undefined, "a string", 42, [], {}, { api_version: "0" }])(
    "rejects %p",
    (value) => {
      expect(isAnalysisResponse(value)).toBe(false);
    },
  );
});

describe("evidenceOf", () => {
  it("returns an empty array when evidence is absent", () => {
    expect(evidenceOf({ api_version: "0", analysis_id: "an_1", status: "non_political" })).toEqual(
      [],
    );
  });

  it("returns an empty array when evidence is the wrong type", () => {
    const malformed = {
      api_version: "0",
      analysis_id: "an_1",
      status: "classified",
      evidence: "not an array",
    } as unknown as Parameters<typeof evidenceOf>[0];
    expect(evidenceOf(malformed)).toEqual([]);
  });
});

describe("showsConfidence", () => {
  const base = { api_version: "0", analysis_id: "an_1", confidence: "low", evidence_strength: "weak" };

  it("shows the line for a classification", () => {
    expect(showsConfidence({ ...base, status: "classified" })).toBe(true);
  });

  it("hides placeholder confidence on unclear and non_political", () => {
    // The API sends the fields on every status; on these two they are not a
    // statement about the result and must not be rendered as one.
    expect(showsConfidence({ ...base, status: "unclear" })).toBe(false);
    expect(showsConfidence({ ...base, status: "non_political" })).toBe(false);
  });
});
