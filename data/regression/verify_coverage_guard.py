"""Does the transitive resolution still fail the cases it must fail?

I widened `_coverage_ledgers` in test_coverage_shortfall_is_visible.py to follow
assignments, and claimed in its docstring that this makes the guard harder to
defeat rather than easier. That is a claim about a detector, so it gets checked
rather than asserted.

Each case below is a miniature ai_extraction: a skip ledger appended to three
times, and some way of arriving at `coverage_complete=`. The guard should pass
the honest derivations and fail the laundered ones.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "unit"))
from test_coverage_shortfall_is_visible import (  # noqa: E402
    _MINIMUM_KNOWN_SKIP_SITES,
    _append_targets,
    _coverage_ledgers,
)

_LEDGER = """
def extract():
    skipped = []
    skipped.append(1)
    skipped.append(2)
    skipped.append(3)
"""

CASES = {
    # honest: the shape before my change
    "direct (not skipped)": (_LEDGER + "    repo.mark_completed(run, coverage_complete=not skipped)\n", True),
    # honest: the shape after my change — one hop of filtering
    "one hop (filtered list)": (
        _LEDGER
        + "    unread = [s for s in skipped if breaks(s)]\n"
        + "    repo.mark_completed(run, coverage_complete=not unread)\n",
        True,
    ),
    # honest: several hops
    "three hops": (
        _LEDGER
        + "    a = [s for s in skipped if breaks(s)]\n"
        + "    b = list(a)\n"
        + "    c = bool(b)\n"
        + "    repo.mark_completed(run, coverage_complete=not c)\n",
        True,
    ),
    # dishonest: constant
    "hard-coded True": (_LEDGER + "    repo.mark_completed(run, coverage_complete=True)\n", False),
    # dishonest: constant laundered through a variable — the case my widening
    # could plausibly have let through
    "laundered constant": (
        _LEDGER + "    flag = True\n    repo.mark_completed(run, coverage_complete=flag)\n",
        False,
    ),
    # dishonest: laundered through two variables
    "doubly laundered constant": (
        _LEDGER
        + "    inner = True\n    flag = inner\n"
        + "    repo.mark_completed(run, coverage_complete=flag)\n",
        False,
    ),
    # dishonest: derived from a separate counter nobody appends skips to
    "separate counter": (
        _LEDGER
        + "    errors = 0\n"
        + "    repo.mark_completed(run, coverage_complete=errors == 0)\n",
        False,
    ),
}


def guard_passes(source: str) -> bool:
    """The assertion inside test_completion_derives_coverage_from_the_skip_ledger."""
    tree = ast.parse(source)
    referenced = _coverage_ledgers(tree)
    if not referenced:
        return False
    appended = _append_targets(tree)
    return any(appended.get(name, 0) >= _MINIMUM_KNOWN_SKIP_SITES for name in referenced)


print(f"{'case':<32} {'expected':<10} {'actual':<10} verdict")
print("-" * 66)
ok = True
for name, (source, expected) in CASES.items():
    actual = guard_passes(source)
    good = actual == expected
    ok = ok and good
    print(
        f"{name:<32} {'pass' if expected else 'FAIL':<10} "
        f"{'pass' if actual else 'FAIL':<10} {'ok' if good else '<-- WRONG'}"
    )
print("-" * 66)
print("ALL CORRECT" if ok else "GUARD IS WRONG")
