"""Scan the live policy set for one decision cut across several records.

Read-only, and the counterpart to `scan_self_containment.py`: that one reports
records carrying too little of their sentence, this one reports several records
carrying one obligation between them.

Nothing is merged or rewritten. The output is a list to check by eye.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.extraction.decision_families import (
    FamilyMember,
    decision_families,
)

POLICY_SET = "ais-employee-handbook"

QUERY = (
    "select payload_json from candidate_rules c "
    "join policy_sets p on p.id = c.policy_set_id "
    f"where p.key = '{POLICY_SET}' and c.superseded_at is null"
)


def load() -> list[dict]:
    out = subprocess.run(
        [
            "docker", "exec", "policy-postgres", "psql",
            "-U", "policy_admin", "-d", "policy_platform_advtool",
            "-t", "-A", "-c", QUERY,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]


def main() -> None:
    rules = [CanonicalRule.model_validate(p) for p in load()]
    print(f"records loaded: {len(rules)}")

    members = []
    titles = {}
    for rule in rules:
        canonical = rule.formulation.canonical if rule.formulation else None
        if canonical is None or canonical.rule is None:
            continue
        members.append(
            FamilyMember(
                rule_id=rule.rule_id,
                sentence=canonical.source_text or "",
                core=canonical.rule,
            )
        )
        titles[rule.rule_id] = rule.title

    print(f"records with a canonical decomposition: {len(members)}")

    families = decision_families(members)
    grouped = sum(len(f.rule_ids) for f in families)
    print(f"families found: {len(families)}  records in them: {grouped}")
    print()

    for family in families:
        print("-" * 78)
        print(f"  {len(family.rule_ids)} records; {family.as_reason()}")
        print(f"  source : {family.sentence[:150]!r}")
        for rule_id in family.rule_ids:
            print(f"    {rule_id}  {titles.get(rule_id, '')[:70]}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
