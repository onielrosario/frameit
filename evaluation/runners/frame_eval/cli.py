"""
Evaluation runner CLI.

    python -m frame_eval.cli --split dev --analyzer mock

`--analyzer mock` runs the whole harness without a model and without spending
tokens, which is what lets the harness itself be tested (docs/evaluation.md §6).
`--analyzer http` points at a running API.

Grounding is computed HERE, not taken from the response: every displayed excerpt
is checked against the normalized submission by this runner. A system reporting
its own grounding is not a measurement.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frame_eval import report as report_module
from frame_eval.metrics import Outcome, Prediction
from frame_eval.records import Record, load

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "evaluation" / "dataset"
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"

Analyzer = Callable[[str], dict[str, Any]]


def mock_analyzer(content: str) -> dict[str, Any]:
    """
    Deterministic stand-in. Returns a grounded excerpt sliced from the content,
    so a harness test exercises the grounding path rather than skipping it.
    """
    excerpt = content[:60]
    return {
        "status": "classified",
        "classification": {"label": "center"},
        "confidence": "medium",
        "evidence": [{"category": "policy_framing", "excerpt": excerpt}],
        "propaganda": None,
    }


def http_analyzer(base_url: str) -> Analyzer:
    def analyze(content: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/analyze",
            data=json.dumps({"content": content, "source": "web", "client_version": "eval"}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())

    return analyze


def run(records: list[Record], analyzer: Analyzer) -> list[Outcome]:
    from app.evidence.normalize import normalize  # imported here so --help needs no API install

    outcomes: list[Outcome] = []
    for record in records:
        try:
            raw = analyzer(record.input)
            prediction = _to_prediction(raw)
        except Exception as error:
            outcomes.append(
                Outcome(
                    record=record,
                    prediction=Prediction(
                        status="error", label=None, confidence=None, error=str(error)
                    ),
                )
            )
            continue

        normalized = normalize(record.input).text
        grounded = [excerpt in normalized for _, excerpt in prediction.evidence]
        outcomes.append(Outcome(record=record, prediction=prediction, grounded=grounded))
    return outcomes


def _to_prediction(raw: dict[str, Any]) -> Prediction:
    classification = raw.get("classification") or {}
    propaganda = raw.get("propaganda") or {}
    return Prediction(
        status=str(raw.get("status", "")),
        label=classification.get("label"),
        confidence=raw.get("confidence"),
        evidence=tuple(
            (str(item.get("category", "")), str(item.get("excerpt", "")))
            for item in raw.get("evidence") or []
        ),
        propaganda=tuple(
            str(item.get("technique", "")) for item in propaganda.get("techniques") or []
        ),
    )


def dataset_sha(path: Path) -> str:
    """Git SHA of the dataset file, so a report names the exact data state."""
    try:
        result = subprocess.run(
            ["git", "hash-object", str(path)],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Frame evaluation harness")
    parser.add_argument("--split", default="dev", choices=["dev", "holdout"])
    parser.add_argument("--analyzer", default="mock", choices=["mock", "http"])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--no-write", action="store_true", help="print the summary, write nothing")
    arguments = parser.parse_args(argv)

    # §2.3: the holdout is run rarely and never tuned against. Tooling cannot
    # enforce that, so it at least refuses to be casual about it.
    if arguments.split == "holdout":
        print(
            "The holdout split is not for iteration. Running it more than a few times before "
            "launch destroys it, and nothing can detect that after the fact.\n"
            "Type 'run holdout' to continue: ",
            end="",
        )
        if input().strip() != "run holdout":
            print("Aborted.")
            return 1

    path = DATASET_DIR / f"{arguments.split}.jsonl"
    if not path.exists():
        print(f"No dataset at {path}", file=sys.stderr)
        return 1

    records = load(path)
    if not records:
        print(
            f"{path} has no records yet.\n"
            "The harness is ready; the dataset is not. See evaluation/dataset/GUIDELINES.md — "
            "labels are written by a human, blind, before any system output is seen.",
            file=sys.stderr,
        )
        return 1

    analyzer = mock_analyzer if arguments.analyzer == "mock" else http_analyzer(arguments.base_url)
    outcomes = run(records, analyzer)

    from app.analysis.gemini import PROMPT_VERSION
    from app.analysis.model_output import SCHEMA_VERSION
    from app.config import API_VERSION, NORMALIZATION_VERSION, get_settings
    from app.evidence.recover import FUZZY_THRESHOLD
    from app.models.taxonomy import TAXONOMY_VERSION
    from app.scoring.provisional import SCORING_VERSION

    # NOTE: with --analyzer http these are the versions of the API code in THIS
    # checkout, read locally. They match the server only when the server runs the
    # same checkout — which is the normal case (uvicorn from this repo).
    versions = report_module.Versions(
        api_version=API_VERSION,
        normalization_version=NORMALIZATION_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        scoring_version=SCORING_VERSION,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        analysis_model=get_settings().analysis_model or f"<{arguments.analyzer}>",
        fuzzy_threshold=FUZZY_THRESHOLD,
        dataset_sha=dataset_sha(path),
    )
    generated = datetime.now(UTC).replace(microsecond=0).isoformat()
    built = report_module.build(outcomes, versions, arguments.split, generated)

    print(report_module.to_markdown(built))
    if not arguments.no_write:
        json_path, markdown_path = report_module.write(built, REPORT_DIR, versions.dataset_sha[:8])
        print(f"\nWrote {json_path.name} and {markdown_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
