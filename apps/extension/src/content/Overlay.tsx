/**
 * The result surface (ADR-0001), rendered inside a shadow root.
 *
 * Every branch below corresponds to a status the API can return. An unknown
 * status degrades to a generic rendering rather than a blank panel — §7 of the
 * contract, written now because users run stale builds for weeks.
 */
import {
  evidenceOf,
  humanize,
  showsConfidence,
  type AnalysisResponse,
  type EvidenceItem,
} from "../api/contract";
import type { FrameMessage } from "../types";

interface OverlayProps {
  state: FrameMessage;
  onClose: () => void;
}

export function Overlay({ state, onClose }: OverlayProps) {
  return (
    <div className="panel" role="dialog" aria-label="Frame">
      <div className="head">
        <h2 className="title">Frame</h2>
        <button className="close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <div className="body">{renderState(state)}</div>
    </div>
  );
}

function renderState(state: FrameMessage) {
  if (state.type === "FRAME_LOADING") {
    return (
      <p className="muted">
        Analyzing {state.pending.charCount.toLocaleString()} characters…
      </p>
    );
  }
  if (state.type === "FRAME_ERROR") {
    return (
      <>
        <p className="status-line warn">Couldn't analyze this selection</p>
        <p className="muted">{state.message}</p>
      </>
    );
  }
  return <Result response={state.response} />;
}

function Result({ response }: { response: AnalysisResponse }) {
  const evidence = evidenceOf(response);

  if (response.status === "blocked") {
    // A reliability event, not an analytical outcome — worded so it cannot be
    // mistaken for "we looked and found nothing" (§3).
    return (
      <>
        <p className="status-line warn">Analysis unavailable</p>
        <p className="muted">{response.explanation}</p>
      </>
    );
  }

  if (response.status === "non_political") {
    return (
      <>
        <p className="status-line">Not a political passage</p>
        <p className="muted">{response.explanation}</p>
      </>
    );
  }

  return (
    <>
      <p className="status-line">
        {response.status === "classified" && response.classification
          ? humanize(response.classification.label)
          : response.status === "unclear"
            ? "Unclear"
            : humanize(response.status)}
      </p>

      {showsConfidence(response) && (response.confidence || response.evidence_strength) && (
        <p className="meta-line">
          {response.confidence && <>Confidence {humanize(response.confidence).toLowerCase()}</>}
          {response.confidence && response.evidence_strength && " · "}
          {response.evidence_strength && (
            <>Evidence {humanize(response.evidence_strength).toLowerCase()}</>
          )}
        </p>
      )}

      {response.explanation && <p className="explanation">{response.explanation}</p>}

      {evidence.length > 0 && (
        <>
          <p className="label">Evidence</p>
          <ul className="evidence">
            {evidence.map((item, index) => (
              <Evidence key={`${item.span.start}-${index}`} item={item} />
            ))}
          </ul>
        </>
      )}

      {response.propaganda && response.propaganda.techniques.length > 0 && (
        <>
          <p className="label">Potential propaganda indicators</p>
          <ul className="evidence">
            {response.propaganda.techniques.map((item, index) => (
              <li key={`${item.span.start}-${index}`}>
                <span className="chip">{humanize(item.technique)}</span>
                <blockquote className="quote">{item.excerpt}</blockquote>
              </li>
            ))}
          </ul>
        </>
      )}

      {response.limitations && response.limitations.length > 0 && (
        <ul className="limitations">
          {response.limitations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function Evidence({ item }: { item: EvidenceItem }) {
  return (
    <li>
      <span className="chip">{humanize(item.category)}</span>
      {/*
        The excerpt is the source substring recovered by span — never the
        model's string. Rendered verbatim, never trimmed or prettified, because
        altering it here would defeat the guarantee it exists to provide.
      */}
      <blockquote className="quote">{item.excerpt}</blockquote>
      <p className="interpretation">{item.interpretation}</p>
    </li>
  );
}
