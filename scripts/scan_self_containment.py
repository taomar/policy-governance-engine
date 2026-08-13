"""Scan the live policy set for records that do not stand on their own.

Read-only. Reports what the detector flags, with the wording it flagged, so the
count can be checked by eye rather than taken on trust.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.extraction.evaluability import (
    Evaluability,
    assess_policy,
    dangling_referents,
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
    payloads = load()
    rules = [CanonicalRule.model_validate(p) for p in payloads]
    print(f"records loaded: {len(rules)}")

    examined = 0
    flagged = []
    for rule in rules:
        canonical = rule.formulation.canonical if rule.formulation else None
        if canonical is None or canonical.rule is None:
            continue
        examined += 1
        items = dangling_referents(canonical.rule, canonical.source_text or "")
        if items:
            before = assess_policy(canonical)
            flagged.append((rule, items, before))

    print(f"records with a canonical decomposition: {examined}")
    print(f"records flagged: {len(flagged)}")
    print()
    for rule, items, verdict in flagged:
        print("-" * 78)
        print(f"{rule.rule_id}  verdict={verdict.evaluability.value}")
        print(f"  source : {(rule.formulation.canonical.source_text or '')[:160]!r}")
        for item in items:
            print(f"  flag   : field={item.field} phrase={item.phrase!r} head={item.head!r}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
