"""Nothing shown to a user reports being decided by reading as a defect.

A policy is served one of two ways. `deterministic` means the source states its
test as a comparison the engine can compute. `ai_ready` means the source states
it in words, and a judge decides it by reading the record. Most policy text is
the second — 53 of 55 in the live corpus — and that is a property of how policy
is written, not a shortcoming of the extraction.

Text that calls the second kind "not machine-executable" turns the ordinary
case into a standing fault. It had spread into six places, and the loudest was
a high-severity quality finding raised against nearly every policy on every
run, recommending a configuration exercise that would never be done and could
not help. Findings that always fire teach a reader to ignore findings.

Scope is the same as the domain-wording guard beside this one: string literals
in behavioural code, prompt instructions, and strings the interface renders.
Comments and docstrings are excluded, because recording the wording that was
removed is how the next reader learns why the rule exists.

The field name `machine_executable` is deliberately allowed. It is a real field
on a real contract, it appears in payloads a model reads, and renaming it is a
migration rather than a wording fix. What is forbidden is the prose.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"
WEB = ROOT / "apps" / "web" / "src"
DOCS = ROOT / "docs"

#: Documents whose purpose is recording the wording that was removed.
_FAILURE_RECORD = DOCS / "failures"

#: Prose that frames being decided by reading as a shortfall.
#:
#: Hyphenated and spaced forms only. `machine_executable` with an underscore is
#: the field, and is allowed everywhere.
_FRAMING = (
    r"machine[- ]executable",
    r"machine[- ]ready",
    r"documentation[- ]only",
    r"FACT_MODEL_REQUIRED",
    r"OUTPUT_MODEL_REQUIRED",
    r"requires? (?:a )?(?:formal )?fact[- ]model",
    r"configure a fact model",
    r"supply the missing mapping",
)
_FRAMING_RE = re.compile(rf"(?:{'|'.join(_FRAMING)})", re.IGNORECASE)

#: Files whose whole purpose is the mechanism rather than the message.
#:
#: `contracts/formulation.py` declares the requirement codes as an enum: the
#: names have to exist for the agent's replies to parse. They are excluded from
#: serialization, so they reach no reader.
_MECHANISM = {
    SRC / "contracts" / "formulation.py",
    SRC / "infrastructure" / "dmn_parity.py",
}


def _string_literals(path: Path) -> list[tuple[int, str]]:
    """Every string literal in a Python file, excluding docstrings."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            found.append((node.lineno, node.value))
    return found


def test_the_guard_would_notice_the_wording_it_forbids():
    """Proves the pattern matches, so a clean run means something.

    Every phrase here was in served output or a prompt before this file
    existed.
    """

    for phrase in (
        "3 rule(s) are not machine-executable.",
        "0% machine-ready",
        "this rule is documentation-only",
        "it still reports FACT_MODEL_REQUIRED",
        "Configure a fact model, or publish a revision",
        "a reviewer must supply the missing mapping",
    ):
        assert _FRAMING_RE.search(phrase), phrase

    # And does not fire on the field name, which is allowed.
    assert not _FRAMING_RE.search('"machine_executable": rule.machine_executable')


def test_no_readiness_framing_in_python_string_literals():
    """Text a user reads, wherever a string ends up being rendered."""

    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path in _MECHANISM:
            continue
        for lineno, value in _string_literals(path):
            match = _FRAMING_RE.search(value)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {value[:70]!r}"
                )

    assert not offenders, "readiness framing in code:\n  " + "\n  ".join(offenders)


def test_no_readiness_framing_in_rendered_web_strings():
    """The interface reaches every user, whatever they upload."""

    offenders: list[str] = []
    for path in sorted(p for p in WEB.rglob("*.ts*") if p.is_file()):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            match = _FRAMING_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {stripped[:70]!r}"
                )

    assert not offenders, "readiness framing in the interface:\n  " + "\n  ".join(offenders)


def test_no_readiness_framing_in_the_documentation():
    """Documentation reaches users too, and it was never checked.

    Scope started at code and the interface, so `docs/` went unscanned. The
    user guide accordingly told a reader to "improve machine-executable
    coverage" and listed it beside publication and ownership as something a
    package should be — presenting the ordinary case as a gap to close, in the
    one document written for the person least able to tell it was wrong.

    `docs/failures/` is excluded for the same reason docstrings are: its whole
    purpose is recording the wording that was removed and why.
    """

    offenders: list[str] = []
    for path in sorted(DOCS.rglob("*.md")):
        if _FAILURE_RECORD in path.parents:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _FRAMING_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {line.strip()[:70]!r}"
                )

    assert not offenders, "readiness framing in documentation:\n  " + "\n  ".join(offenders)


def test_the_documentation_scan_reaches_files_and_honours_its_exclusion():
    """Guard the guard: an empty glob or a swallowed root would prove nothing."""

    scanned = [p for p in DOCS.rglob("*.md") if _FAILURE_RECORD not in p.parents]
    assert len(scanned) > 20, f"only {len(scanned)} documents scanned; the glob is wrong"
    assert (DOCS / "user-guide.md") in scanned

    # The exclusion is real, and the excluded records do contain the wording --
    # so excluding them is a deliberate decision, not a way to pass.
    excluded = list(_FAILURE_RECORD.rglob("*.md"))
    assert excluded, "the failure records are missing, so the exclusion hides nothing"
    assert any(
        _FRAMING_RE.search(path.read_text(encoding="utf-8")) for path in excluded
    ), "no excluded document contains the framing, so the exclusion is unnecessary"
