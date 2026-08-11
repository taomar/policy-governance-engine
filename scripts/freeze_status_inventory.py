"""Regenerate the frozen status snapshot from the rule corpus.

Run this *only* when a verdict change is intended and understood:

    .venv-graph\\Scripts\\python.exe scripts\\freeze_status_inventory.py

`tests/unit/test_status_inventory_freeze.py` compares live derivation against
the snapshot this writes. Regenerating it to make a failing test pass would
defeat the entire point — the test exists to make a changed verdict visible,
and the snapshot is the record of what the system said before the change.

Review the diff this produces before committing it. A phase of the revamp that
moves a verdict should show exactly which rules moved, and why.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.unit.status_inventory import build_snapshot, load_corpus  # noqa: E402

SNAPSHOT = ROOT / "tests" / "fixtures" / "ad103_status_snapshot.json"


def main() -> None:
    snapshot = build_snapshot(load_corpus())
    SNAPSHOT.write_text(
        json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    totals = snapshot["totals"]
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}")
    for key, value in totals.items():
        print(f"  {key:38} {value}")


if __name__ == "__main__":
    main()
