"""Capture the served candidate rules as the test corpus.

Several tests check properties of real extraction output rather than of
constructed records, because constructed records agree with whatever the test
assumes. That only works if the corpus is what consumers actually receive.

The corpus had been captured by hand, before the derived views existed, so it
carried none of them — and five checks written against those views iterated
over nothing and passed. A guard that cannot fail is worse than no guard,
because it is counted as coverage.

Capturing from the API rather than from the database is deliberate: the derived
views are added on read, and it is the read path's output that the rest of the
system consumes.

    python scripts/capture_corpus.py [--url http://localhost:8050] [--set benefits]

Regenerate `tests/fixtures/ad103_status_snapshot.json` afterwards with
`scripts/freeze_status_inventory.py`, and read the diff: a verdict that moved
without an intended cause is the finding.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "tests" / "fixtures" / "ad103_rules.json"


def fetch(url: str, policy_set: str) -> list[dict]:
    endpoint = f"{url.rstrip('/')}/api/policy-sets/{policy_set}/candidate-rules"
    with urllib.request.urlopen(endpoint, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"unexpected response shape from {endpoint}")
    return [entry["rule"] for entry in payload if "rule" in entry]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8050")
    parser.add_argument("--set", dest="policy_set", default="benefits")
    args = parser.parse_args(argv)

    rules = fetch(args.url, args.policy_set)
    if not rules:
        raise SystemExit("no rules returned; refusing to write an empty corpus")

    derived = {
        "xacml_view": sum(1 for r in rules if r.get("xacml_view")),
        "fact_model": sum(1 for r in rules if r.get("fact_model")),
        "attributes": sum(1 for r in rules if r.get("attributes")),
        "required_facts": sum(1 for r in rules if r.get("required_facts")),
        "condition_provenance": sum(1 for r in rules if r.get("condition_provenance")),
    }
    missing = [name for name, count in derived.items() if count == 0]
    if missing:
        # Writing it anyway would silently disarm the checks that read them.
        raise SystemExit(
            f"refusing to write a corpus carrying no {missing}: "
            "the API is stale, or these are no longer served"
        )

    CORPUS.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rules)} rules to {CORPUS.relative_to(REPO_ROOT)}")
    for name, count in derived.items():
        print(f"  {name:22} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
