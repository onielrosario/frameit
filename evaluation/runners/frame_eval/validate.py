"""
Dataset validator.

    python -m frame_eval.validate

Checks what can be checked mechanically: record format, that every expected
excerpt really occurs in its input, that mirror pairs point at each other, and
how the composition compares to the targets in docs/evaluation.md §3.

It cannot check whether the labels are any good. Nothing can — there is no
external ground truth for how a passage frames an issue, only inter-reviewer
agreement (§8).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from frame_eval.records import Record, load

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "evaluation" / "dataset"

# §3. Proportions for the full ~150; printed as guidance, never enforced.
COMPOSITION_TARGETS = {
    "left": 0.20,
    "right": 0.20,
    "center": 0.15,
    "unclear": 0.15,
    "non_political": 0.10,
    "mirror pairs": 0.15,
}


def check(records: list[Record]) -> list[str]:
    problems: list[str] = []
    by_id = {record.id: record for record in records}

    for record in records:
        for evidence in record.expected_evidence:
            if evidence.excerpt not in record.input:
                # The hard gate applies to the dataset too: an expected excerpt
                # that is not in the input would score Frame against text nobody
                # submitted.
                problems.append(
                    f"{record.id}: expected excerpt is not a substring of input: "
                    f"{evidence.excerpt!r}"
                )

        if record.review_state == "not_reviewed":
            problems.append(
                f"{record.id}: review_state is 'not_reviewed' — an unreviewed record in a "
                "scored split silently becomes ground truth"
            )
        if record.label_provenance == "unreviewed":
            problems.append(
                f"{record.id}: label_provenance is 'unreviewed' — say where the label came "
                "from; it changes what a number computed from it means"
            )
        if record.expected_status == "unclear" and not record.expected_evidence:
            problems.append(
                f"{record.id}: unclear with no expected_evidence — an unclear that shows "
                "nothing is a product failure (evaluation.md §6)"
            )

        twin_id = record.mirror_of
        if twin_id is None:
            continue
        if twin_id not in by_id:
            problems.append(f"{record.id}: mirror_of points at unknown id {twin_id!r}")
        elif by_id[twin_id].mirror_of != record.id:
            problems.append(
                f"{record.id}: mirror pair is not reciprocal — {twin_id} points at "
                f"{by_id[twin_id].mirror_of!r}"
            )
        elif by_id[twin_id].split != record.split:
            problems.append(
                f"{record.id}: mirror twin {twin_id} is in a different split, so one half "
                "can leak across the dev/holdout boundary"
            )
    return problems


def composition(records: list[Record]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        if record.expected_status == "non_political":
            counts["non_political"] += 1
        elif record.expected_status == "unclear":
            counts["unclear"] += 1
        elif record.expected_direction == "none":
            counts["center"] += 1
        else:
            counts[record.expected_direction] += 1
        if record.mirror_of:
            counts["mirror halves"] += 1
    counts["mirror pairs"] = counts["mirror halves"] // 2
    del counts["mirror halves"]
    return counts


def main(argv: list[str] | None = None) -> int:
    paths = sorted(DATASET_DIR.glob("*.jsonl"))
    paths = [path for path in paths if path.name != "TEMPLATE.jsonl"]

    all_records: list[Record] = []
    for path in paths:
        try:
            records = load(path)
        except ValueError as error:
            print(f"FAIL {error}", file=sys.stderr)
            return 1
        print(f"{path.name}: {len(records)} records")
        all_records.extend(records)

    if not all_records:
        print(
            "\nNo records yet. The harness is ready; the dataset is not.\n"
            "See evaluation/dataset/GUIDELINES.md — labels are written by a human, blind."
        )
        return 0

    seen: set[str] = set()
    duplicates = {r.id for r in all_records if r.id in seen or seen.add(r.id)}  # type: ignore[func-returns-value]
    problems = check(all_records)
    problems += [f"duplicate id across splits: {name}" for name in sorted(duplicates)]

    counts = composition(all_records)
    total = len(all_records)
    print(f"\nComposition ({total} records)")
    for bucket, target in COMPOSITION_TARGETS.items():
        actual = counts.get(bucket, 0)
        share = actual / total if total else 0
        print(f"  {bucket:16} {actual:3}  {share:5.0%}  target {target:.0%}")

    # Gaps that are invisible per-record but fatal in aggregate.
    if counts.get("mirror pairs", 0) == 0:
        problems.append(
            "no mirror pairs — §4 calls this the most important instrument in the "
            "evaluation doc, and without a pair nothing tests directional symmetry"
        )
    for direction in ("left", "right", "center"):
        if counts.get(direction, 0) == 0:
            problems.append(
                f"no {direction}-leaning examples — a set with none cannot detect a "
                f"{direction} error at all"
            )

    provenance: Counter[str] = Counter(r.label_provenance for r in all_records)
    print("\nLabel provenance")
    for name, count in sorted(provenance.items()):
        print(f"  {name:30} {count:3}")
    if provenance.get("agent_drafted_human_reviewed"):
        print(
            "  note: agent-drafted labels support 'agreement with a reviewer who saw a "
            "proposal', not blind agreement. Anchoring applies."
        )

    if problems:
        print("\nProblems:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("\nFormat OK. This says nothing about whether the labels are right.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
