"""Measure two policy sets against each other on the slicing defects.

Both defects are properties of where the extractor cut, so a prompt revision
that claims to have fixed one has to be shown not to have bought it with the
other. Over-splitting and under-inclusion trade off directly: a record that
absorbs its neighbours stops being a fragment and starts being unfaithful, and
a record that stops absorbing them stops being unfaithful and starts being a
fragment. Neither number means anything without the other beside it.

Read-only, and it reads whatever policy sets it is given, so the baseline is
never re-extracted to produce a comparison.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.extraction.decision_families import (
    FamilyMember,
    decision_families,
)
from policy_platform.infrastructure.extraction.evaluability import dangling_referents
from policy_platform.infrastructure.quality.logic_faithfulness import judge_logic


def load(policy_set_key: str) -> list[CanonicalRule]:
    query = (
        "select payload_json from candidate_rules c "
        "join policy_sets p on p.id = c.policy_set_id "
        f"where p.key = '{policy_set_key}' and c.superseded_at is null"
    )
    out = subprocess.run(
        [
            "docker", "exec", "policy-postgres", "psql",
            "-U", "policy_admin", "-d", "policy_platform_advtool",
            "-t", "-A", "-c", query,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [
        CanonicalRule.model_validate(json.loads(line))
        for line in out.stdout.splitlines()
        if line.strip()
    ]


def measure(rules: list[CanonicalRule]) -> dict:
    members: list[FamilyMember] = []
    clauses: set[str] = set()
    dangling_ids: list[str] = []
    codes: Counter = Counter()

    for rule in rules:
        canonical = rule.formulation.canonical if rule.formulation else None
        if canonical is None or canonical.rule is None:
            continue
        source = canonical.source_text or ""
        members.append(
            FamilyMember(rule_id=rule.rule_id, sentence=source, core=canonical.rule)
        )
        if rule.evidence:
            clause_id = getattr(rule.evidence[0], "clause_id", None)
            if clause_id:
                clauses.add(clause_id)
        if dangling_referents(canonical.rule, source):
            dangling_ids.append(rule.rule_id)
        for finding in judge_logic(canonical).findings:
            codes[finding.code] += 1

    families = decision_families(members)
    return {
        "records": len(rules),
        "examined": len(members),
        "clauses": len(clauses),
        "not_self_contained": len(dangling_ids),
        "not_self_contained_ids": dangling_ids,
        "families": len(families),
        "records_in_families": sum(len(f.rule_ids) for f in families),
        "family_detail": [
            (len(f.rule_ids), f.varying, f.sentence[:90]) for f in families
        ],
        "logic_codes": dict(codes),
    }


def _pct(n: int, total: int) -> str:
    return f"{n} ({100 * n / total:.1f}%)" if total else f"{n} (n/a)"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: compare_slicing.py <baseline-key> <candidate-key>")
        return 2

    baseline_key, candidate_key = sys.argv[1], sys.argv[2]
    base = measure(load(baseline_key))
    cand = measure(load(candidate_key))

    if not base["examined"] or not cand["examined"]:
        print("one side examined no records; the comparison would be silence, not a result")
        return 1

    rows = [
        ("records", base["records"], cand["records"]),
        ("source clauses", base["clauses"], cand["clauses"]),
        ("records examined", base["examined"], cand["examined"]),
    ]
    print(f"{'measure':<34}{baseline_key:<32}{candidate_key}")
    print("-" * 96)
    for label, b, c in rows:
        print(f"{label:<34}{b:<32}{c}")

    print(
        f"{'not self-contained':<34}"
        f"{_pct(base['not_self_contained'], base['examined']):<32}"
        f"{_pct(cand['not_self_contained'], cand['examined'])}"
    )
    print(
        f"{'records in split families':<34}"
        f"{_pct(base['records_in_families'], base['examined']):<32}"
        f"{_pct(cand['records_in_families'], cand['examined'])}"
    )
    print(f"{'split families':<34}{base['families']:<32}{cand['families']}")

    print()
    print("judge_logic findings by code")
    print("-" * 96)
    for code in sorted(set(base["logic_codes"]) | set(cand["logic_codes"])):
        print(
            f"{code:<34}{base['logic_codes'].get(code, 0):<32}"
            f"{cand['logic_codes'].get(code, 0)}"
        )

    for label, data in ((baseline_key, base), (candidate_key, cand)):
        print()
        print(f"=== {label}: families")
        for size, varying, sentence in data["family_detail"]:
            print(f"  {size} records, differ in {', '.join(varying)}: {sentence!r}")
        print(f"=== {label}: not self-contained")
        print(f"  {', '.join(data['not_self_contained_ids']) or '(none)'}")

    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
