#!/usr/bin/env python3
"""
Render the mirror-pair asset from a LIVE Frame analysis.

    python marketing/mirror/render.py --api http://localhost:8000

The result is not an input. This calls the API with both passages, applies the
same symmetry rule the evaluation harness uses
(frame_eval.metrics.compare_predictions), and stamps the outcome on the image.

If the pair comes back asymmetric the image says so. That is the point: a demo
that can only ever show success is not evidence, and docs/evaluation.md §7 says
a published failure is worth more here than a withheld success.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "evaluation" / "runners"))

from frame_eval.metrics import Prediction, compare_predictions  # noqa: E402

HERE = Path(__file__).parent
OUT = REPO / "marketing" / "out"


def _opener(api: str):
    """
    Bypass any configured HTTP proxy for a loopback API. A proxy that intercepts
    localhost turns "the server is right here" into an opaque 503.
    """
    host = urllib.parse.urlparse(api).hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def analyze(api: str, content: str) -> dict:
    request = urllib.request.Request(
        f"{api.rstrip('/')}/analyze",
        data=json.dumps(
            {"content": content, "source": "web", "client_version": "marketing"}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _opener(api).open(request, timeout=90) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        # The server answered. Show what it said — reporting this as a
        # reachability problem sends people to debug the network while the API
        # is explaining the actual fault.
        try:
            detail = json.loads(error.read()).get("detail", "")
        except Exception:
            detail = ""
        sys.exit(f"Frame API returned {error.code}: {detail or error.reason}")
    except urllib.error.URLError as error:
        sys.exit(f"Could not reach the Frame API at {api}: {error.reason}")


def to_prediction(raw: dict) -> Prediction:
    classification = raw.get("classification") or {}
    propaganda = raw.get("propaganda") or {}
    return Prediction(
        status=str(raw.get("status", "")),
        label=classification.get("label"),
        confidence=raw.get("confidence"),
        evidence=tuple(
            (str(i.get("category", "")), str(i.get("excerpt", "")))
            for i in raw.get("evidence") or []
        ),
        propaganda=tuple(str(t.get("technique", "")) for t in propaganda.get("techniques") or []),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--pair", default=str(HERE / "pair.json"))
    parser.add_argument("--out", default=str(OUT / "mirror.png"))
    args = parser.parse_args()

    pair = json.loads(Path(args.pair).read_text())
    for key in ("a", "b"):
        if "REPLACE ME" in pair[key]["text"]:
            sys.exit(
                f"pair.json side {key!r} is still a placeholder.\n"
                "Write the pair by hand first — see docs/evaluation.md §4. A mirror pair "
                "written by anything other than a person cannot be used to show that a model "
                "treats both directions the same way."
            )

    raw_a, raw_b = analyze(args.api, pair["a"]["text"]), analyze(args.api, pair["b"]["text"])
    pred_a, pred_b = to_prediction(raw_a), to_prediction(raw_b)

    # A mock agreeing with itself is not evidence of symmetry.
    if pred_a == pred_b and pred_a.evidence and pred_b.evidence:
        first = [e[1] for e in pred_a.evidence]
        second = [e[1] for e in pred_b.evidence]
        if first == second:
            sys.exit(
                "Both passages returned byte-identical analyses, including the same excerpts.\n"
                "That is a mocked backend agreeing with itself. Connect a real model before "
                "rendering a symmetry claim."
            )

    result = compare_predictions(("A", "B"), pred_a, pred_b)
    checks = [
        {"name": "Label magnitude", "ok": result.label_symmetric},
        {"name": "Confidence band", "ok": result.confidence_within_one_band},
        {"name": "Evidence categories", "ok": result.categories_match},
        {"name": "Propaganda flags", "ok": result.propaganda_matches},
    ]
    failed = [c["name"].lower() for c in checks if not c["ok"]]
    detail = (
        "Mirrored passages, mirrored treatment. One pair — this demonstrates the test, "
        "not that the property holds."
        if result.passed
        else "Frame treated these two differently: " + ", ".join(failed) + "."
    )

    data = {
        "headline": pair.get("headline", "Same structure. Opposite politics."),
        "subhead": pair.get("subhead", ""),
        "sides": [
            {
                "label": pair[key]["label"],
                "text": pair[key]["text"],
                "label_value": prediction.label or prediction.status,
                "confidence": prediction.confidence,
                "strength": raw.get("evidence_strength"),
                "evidence": [
                    {
                        "category": item.get("category", ""),
                        "excerpt": item.get("excerpt", ""),
                        "interpretation": item.get("interpretation", ""),
                    }
                    for item in (raw.get("evidence") or [])[:2]
                ],
            }
            for key, prediction, raw in (("a", pred_a, raw_a), ("b", pred_b, raw_b))
        ],
        "verdict": {"passed": result.passed, "detail": detail, "checks": checks},
        "footnote": pair.get("footnote", "One pair · demonstrates the test, not the result"),
    }

    html = (HERE / "template.html").read_text().replace("/*__DATA__*/ {}", json.dumps(data))
    OUT.mkdir(parents=True, exist_ok=True)
    html_path = OUT / "mirror.html"
    html_path.write_text(html)

    print(f"A: {pred_a.label or pred_a.status}   B: {pred_b.label or pred_b.status}")
    print("SYMMETRIC" if result.passed else f"ASYMMETRIC — {', '.join(failed)}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"\nplaywright not installed; wrote {html_path}")
        print("Open it and screenshot, or: pip install playwright && playwright install chromium")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        page.goto(f"file://{html_path}")
        page.wait_for_function("window.__ready === true", timeout=15000)
        page.wait_for_timeout(2500)
        page.screenshot(path=args.out)
        browser.close()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
