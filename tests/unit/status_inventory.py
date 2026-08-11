"""Deriving each rule's status exactly as the API read path does.

Shared by the freeze script and the characterization test so the snapshot and
the assertion can never disagree about how a verdict is computed. If this
module reimplemented the derivation, the test would be checking its own copy
of the logic rather than the platform's.

Everything here is a pure function of the stored payload. No database, no API,
no network — the corpus is a file, so the test runs anywhere and always sees
the same 44 rules.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from policy_platform.api.routers.candidate_rules import _with_decision_readiness
from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.formulation_mapping import _ambiguity_for

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CORPUS = FIXTURES / "ad103_rules.json"
SNAPSHOT = FIXTURES / "ad103_status_snapshot.json"

#: `formulation_mapping` appends the provenance note to every description as
#: `[Conditions: <code> — <message>]`. Read back rather than recomputed so the
#: snapshot records what a reviewer actually sees.
_PROVENANCE_RE = re.compile(r"\[Conditions:\s*([a-z_]+)\s*—")

#: Roles whose phrase states a requirement the rule depends on.
#:
#: `condition` and `prerequisite` are both requirement-bearing and were both
#: emitted by the formulator on this corpus — a first count that looked only at
#: `condition` undercounted, because an authority inherited from a parent
#: clause lands in `prerequisite`. R2 decomposes both.
_REQUIREMENT_ROLES = ("condition", "prerequisite")

#: Requirement seams the source itself states. Used only to *count* how many
#: requirement phrases bundle more than one requirement — this is a measurement
#: of the corpus, not a splitter. R2 does the splitting, and must justify each
#: seam against a span.
_SEAMS = (" and ", " subject to ", " provided that ", " depending on ")


def load_corpus() -> list[CanonicalRule]:
    """The 44 stored payloads, read back through the same model the API uses."""

    payloads = json.loads(CORPUS.read_text(encoding="utf-8"))
    return [CanonicalRule.model_validate(p) for p in payloads]


def load_snapshot() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _is_vacuous(rule: CanonicalRule) -> bool:
    condition = rule.condition
    if condition is None:
        return True
    if condition.type == "all":
        return not condition.all
    if condition.type == "any":
        return not condition.any
    return False


def status_for(rule: CanonicalRule) -> dict[str, Any]:
    """One rule's complete status picture, as a reviewer receives it.

    Deliberately records *every* representation at once. The point of the
    freeze is that these currently disagree — 21 of 44 rules report
    `decidable`, `human_judgment_required` and `machine_executable=false`
    together — so a snapshot that recorded only one of them would hide the
    problem the revamp exists to fix.
    """

    resolved = _with_decision_readiness(rule)
    readiness = resolved.decision_readiness
    note = _PROVENANCE_RE.search(resolved.description or "")
    requirements: list[dict[str, str]] = []
    parties: list[dict[str, str]] = []
    if readiness is not None:
        requirements = [
            {"role": a.role, "phrase": a.phrase}
            for a in readiness.required_attributes
            if a.role in _REQUIREMENT_ROLES
        ]
        parties = [
            {"name": party.name, "role": party.role.value, "source": party.source}
            for party in readiness.parties
        ]

    canonical = resolved.formulation.canonical if resolved.formulation else None
    canonical_rule = canonical.rule if canonical else None
    condition_code = note.group(1) if note else None

    # Re-derived, not read back. `ambiguity_status` is *stored* in the payload,
    # unlike `decision_readiness`, so reading the stored value would make this
    # snapshot blind to any change in `_ambiguity_for` — which is exactly the
    # function R4 modifies. A first version of this module did read it back,
    # and a mutation that dropped a code from `_TREE_UNDERSTATES_SOURCE` (the
    # gate that stops a narrow permission reading as an open one) passed all
    # twenty tests.
    #
    # Recording both also exposes a real problem: a correction to
    # `_ambiguity_for` today leaves all 44 stored rules carrying the old
    # verdict, the same staleness `_decision_readiness_for` was made
    # derived-on-read to avoid.
    derived_ambiguity = (
        _ambiguity_for(canonical, resolved.machine_executable, condition_code or "derived").value
        if canonical is not None
        else None
    )

    return {
        "rule_id": resolved.rule_id,
        "title": resolved.title,
        "rule_type": resolved.rule_type.value,
        "effect_type": resolved.effect.type.value if resolved.effect else None,
        "machine_executable": resolved.machine_executable,
        "condition_is_vacuous": _is_vacuous(resolved),
        "condition_provenance_code": condition_code,
        # The same fact as the line above, but taken from the structured field
        # the interface reads rather than parsed out of the description. Both
        # are recorded so a drift between them is visible; they are written at
        # different times (extraction vs read) and only real stored data
        # exercises both paths.
        "condition_provenance_field_code": (
            resolved.condition_provenance.code if resolved.condition_provenance else None
        ),
        "ambiguity_status_stored": resolved.ambiguity_status.value,
        "ambiguity_status_derived": derived_ambiguity,
        "evaluability": readiness.evaluability if readiness else None,
        "judgement_bounded": readiness.judgement_bounded if readiness else None,
        # Whether the formulator stated this from the clause itself or carried
        # it down from a parent. An inherited authority is legitimate — clause
        # 3.2 governs 3.2.1-3.2.6 — but it is why a party can name someone the
        # rule's own sentence never mentions, so R2 must record the origin on
        # any dependency node it builds or the node will look invented.
        "source_origin": getattr(canonical_rule, "source_origin", None),
        "required_facts": sorted(f.name for f in (resolved.required_facts or [])),
        "parties": parties,
        "requirements": requirements,
    }


def build_snapshot(rules: list[CanonicalRule]) -> dict[str, Any]:
    entries = sorted((status_for(rule) for rule in rules), key=lambda e: e["rule_id"] or "")

    disagreeing = sum(
        1
        for e in entries
        if e["evaluability"] == "decidable"
        and e["ambiguity_status_stored"] == "human_judgment_required"
        and e["machine_executable"] is False
    )
    stale = sum(
        1 for e in entries if e["ambiguity_status_stored"] != e["ambiguity_status_derived"]
    )
    with_authority = sum(
        1 for e in entries if any(p["role"] == "authority" for p in e["parties"])
    )
    requirement_phrases = [r for e in entries for r in e["requirements"]]
    bundled = [r for r in requirement_phrases if any(s in f" {r['phrase']} " for s in _SEAMS)]
    with_requirements = [e for e in entries if e["requirements"]]
    inherited = sum(1 for e in entries if e["source_origin"] == "inherited_context")

    return {
        "totals": {
            "rules": len(entries),
            "machine_executable": sum(1 for e in entries if e["machine_executable"]),
            "vacuous_conditions": sum(1 for e in entries if e["condition_is_vacuous"]),
            "naming_an_authority": with_authority,
            "rules_with_requirements": len(with_requirements),
            "requirement_phrases": len(requirement_phrases),
            "requirement_phrases_bundling_several": len(bundled),
            "inherited_from_parent_clause": inherited,
            "stored_ambiguity_differs_from_derived": stale,
            "three_flags_disagree": disagreeing,
        },
        "rules": entries,
    }
