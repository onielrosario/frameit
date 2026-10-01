"""
The MVP taxonomy as closed enums, bound to TAXONOMY_VERSION.

docs/methodology.md §4 and §8 OWN the taxonomy. This file is the only place it
becomes code, and both schemas import it: the model-output schema (what Gemini
may emit) and the client response (what the API may send). One definition, so
the two cannot drift apart.

Changing any list here is a taxonomy change: bump TAXONOMY_VERSION, which
changes the config fingerprint (architecture.md §6) and therefore every cache key.
"""

from __future__ import annotations

from typing import Literal, get_args

TAXONOMY_VERSION = "1"
# 0 → 1 (step 12): the step-08 placeholder enums (source_selection, attribution,
# loaded_question, bandwagon) were never the methodology's taxonomy. Replaced with
# methodology §4 / §8 verbatim. Headline framing and demonstrable omission stay
# out (ADR-0003). "Other observable techniques" (§8) is NOT an enum value: an
# open bucket invites the model to invent a technique, and precision beats recall.

EvidenceCategory = Literal[
    # Political framing
    "policy_framing",
    "responsibility_framing",  # government vs. individual responsibility
    "actor_characterization",
    "viewpoint_treatment",
    "argument_emphasis",
    # Language
    "loaded_language",
    "emotional_language",
    "fear_framing",
    "dehumanization",
    "scapegoating",
    "us_vs_them",
    "division_language",
    # Structural
    "selective_presentation",
]

PropagandaTechnique = Literal[
    "fear_appeal",
    "dehumanization",
    "scapegoating",
    "us_vs_them",
    "false_dilemma",
    "emotional_manipulation",
]

# Family of each category — the unit of INDEPENDENCE for scoring (methodology §3:
# "three loaded-language findings are one signal wearing three hats"). Grouping
# is by the methodology's own headings.
CATEGORY_FAMILY: dict[str, str] = {
    "policy_framing": "framing",
    "responsibility_framing": "framing",
    "actor_characterization": "framing",
    "viewpoint_treatment": "framing",
    "argument_emphasis": "framing",
    "loaded_language": "language",
    "emotional_language": "language",
    "fear_framing": "language",
    "dehumanization": "language",
    "scapegoating": "language",
    "us_vs_them": "language",
    "division_language": "language",
    "selective_presentation": "structural",
}

assert set(CATEGORY_FAMILY) == set(get_args(EvidenceCategory)), "every category needs a family"
