/**
 * Client-side mirror of the response shape in docs/analysis-contract.md §3.
 *
 * The contract is OWNED there. This file mirrors it for type-checking and does
 * not restate its rules. If the two disagree, the doc wins and this is the bug.
 *
 * Every enum is deliberately widened with `(string & {})`. §7 requires clients
 * to tolerate unknown enum values without crashing — a new taxonomy category or
 * propaganda technique must degrade to a generic rendering, never a blank screen
 * or an exception. Users run stale builds for weeks, so this is written on day
 * one rather than after the first incident.
 */

/** A known value, but any string is accepted. Autocomplete without brittleness. */
type Open<T extends string> = T | (string & {});

export type AnalysisStatus = Open<"classified" | "unclear" | "non_political" | "blocked">;

export type ClassificationLabel = Open<
  | "strongly_left"
  | "left"
  | "slightly_left"
  | "center"
  | "slightly_right"
  | "right"
  | "strongly_right"
>;

export type Confidence = Open<"high" | "medium" | "low">;
export type Strength = Open<"strong" | "moderate" | "weak">;

export interface EvidenceItem {
  category: Open<string>;
  excerpt: string;
  span: { start: number; end: number };
  interpretation: string;
  strength: Strength;
}

export interface AnalysisResponse {
  api_version: string;
  analysis_id: string;
  status: AnalysisStatus;
  /** Present only when status is "classified" (§3). */
  classification?: { label: ClassificationLabel };
  confidence?: Confidence;
  evidence_strength?: Strength;
  evidence?: EvidenceItem[];
  propaganda?: {
    level: Open<"none" | "low" | "moderate" | "high">;
    techniques: { technique: Open<string>; excerpt: string; span: { start: number; end: number } }[];
  } | null;
  explanation?: string;
  limitations?: string[];
  meta?: { cached?: boolean; content_hash?: string; min_supported_client?: string };
}

/**
 * Minimal runtime guard. The API owns validation (§8); this exists only so a
 * malformed body surfaces as an error state instead of a render crash.
 */
export function isAnalysisResponse(value: unknown): value is AnalysisResponse {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.api_version === "string" &&
    typeof candidate.analysis_id === "string" &&
    typeof candidate.status === "string"
  );
}

/**
 * Turns any label into display text, including one this build has never seen.
 * `some_future_label` renders as "Some future label" rather than throwing or
 * rendering blank.
 */
export function humanize(value: string): string {
  const spaced = value.replace(/_/g, " ").trim();
  if (!spaced) return "";
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Evidence, defaulted. An absent array and an empty one mean the same to a renderer. */
export function evidenceOf(response: AnalysisResponse): EvidenceItem[] {
  return Array.isArray(response.evidence) ? response.evidence : [];
}

/**
 * Whether to show the confidence / evidence-strength line.
 *
 * Only for a classification. On `unclear` and `non_political` the API still
 * sends both fields (the contract requires them), but they are placeholders:
 * "Unclear · Confidence low" reads as "Frame is unsure it is unclear", which is
 * not what happened.
 */
export function showsConfidence(response: AnalysisResponse): boolean {
  return response.status === "classified";
}
