"""No domain-specific wording in code, prompts, or anything shown to a user.

This platform reads whatever policy document a customer uploads. A term drawn
from one document — a currency, an institution, a job title, a benefit name —
that finds its way into matching logic, prompt instruction, or interface text
does not stay harmless documentation. It becomes behaviour:

* A quantity check that enumerated four currency codes silently passed every
  document denominated in a fifth. It was not finding the limits intact; it
  could not see them.
* A party-name capture that ended at one of three nouns ran on into the next
  clause for any document that used different ones.
* A prompt that teaches with one domain's vocabulary teaches the model to
  expect that domain.

The failure mode is the same each time and it is quiet: the code appears to
work, because it was tested on the document it was written against.

This test is deliberately blunt. It fails on the presence of the terms, and the
remedy is to express the rule structurally — a currency is *shaped* like three
capitals or a currency symbol; a clause boundary is *marked* by a modal verb —
rather than to list the instances one corpus happened to contain.

Scope: what runs or is read. Behavioural code, prompt instructions, and strings
the interface renders. Comments and docstrings are excluded, because recording
the concrete case that motivated a design is how the next reader learns why the
structural rule exists — deleting that leaves the rule looking arbitrary.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"
WEB = ROOT / "apps" / "web" / "src"
PROMPTS = SRC / "infrastructure" / "prompts"

#: Terms tied to a particular domain, employer, sector or currency.
#:
#: Kept as whole words so ordinary technical vocabulary is unaffected: `board`
#: matches a governing body but not `dashboard`, and `HR` matches the function
#: but not `HREF`.
_DOMAIN_TERMS = (
    # Named currencies. A currency belongs in the document, never in the code.
    r"SAR|USD|EUR|GBP|AED|JPY|INR",
    # Roles and bodies from a particular kind of organisation.
    r"President|Board of Trustees|Trustees|Vice[- ]Chancellor|Provost",
    # Sector vocabulary.
    r"basic salary|housing allowance|payroll|employee benefits",
    # A specific customer, document or institution.
    r"FBSU|AD-103",
)
_DOMAIN_RE = re.compile(rf"\b(?:{'|'.join(_DOMAIN_TERMS)})\b")


def _python_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _web_files() -> list[Path]:
    return sorted(p for p in WEB.rglob("*.ts*") if p.is_file())


def _string_literals(path: Path) -> list[tuple[int, str]]:
    """Every string literal in a Python file, excluding docstrings.

    Parsed rather than pattern-matched so a term inside a comment or a
    docstring — where it is documentation — is not confused with one inside a
    literal, where it is behaviour.
    """

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


def test_no_domain_terms_in_python_string_literals():
    """Behaviour and user-facing text must not name one customer's vocabulary."""

    offenders: list[str] = []
    for path in _python_files():
        for lineno, value in _string_literals(path):
            match = _DOMAIN_RE.search(value)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {value[:70]!r}"
                )

    assert not offenders, "domain-specific wording in code:\n  " + "\n  ".join(offenders)


def test_no_domain_terms_in_prompts():
    """A prompt teaches by example, so its examples must be domain-neutral."""

    offenders: list[str] = []
    for path in sorted(PROMPTS.glob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _DOMAIN_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {line.strip()[:70]!r}"
                )

    assert not offenders, "domain-specific wording in prompts:\n  " + "\n  ".join(offenders)


def test_no_domain_terms_in_rendered_web_strings():
    """Strings the interface renders reach every customer, whatever they upload."""

    # Comment lines only; a term inside rendered text is what this guards.
    comment = re.compile(r"^\s*(?://|/\*|\*)")
    offenders: list[str] = []
    for path in _web_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if comment.match(line):
                continue
            match = _DOMAIN_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {line.strip()[:70]!r}"
                )

    assert not offenders, "domain-specific wording in web strings:\n  " + "\n  ".join(offenders)


# --------------------------------------------------------------------------
# The guard must be able to fail
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "a maximum of 5,000 SAR",
        "approval of the Board of Trustees",
        "10% of basic salary",
        "the AD-103 corpus",
    ],
)
def test_the_detector_catches_domain_wording(text):
    assert _DOMAIN_RE.search(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "a maximum of 5,000 per month",
        "approval of the named authority",
        "a proportion of another quantity",
        "the uploaded document",
        # Ordinary vocabulary that merely contains a term as a substring.
        "the dashboard shows the current state",
        "an HREF pointing at the source",
    ],
)
def test_the_detector_leaves_neutral_wording_alone(text):
    assert _DOMAIN_RE.search(text) is None
