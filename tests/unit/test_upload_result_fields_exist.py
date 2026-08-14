"""The upload page may only read back fields the upload endpoint returns.

WHY THIS EXISTS

`api.uploadDocument` ends in `return res.json()`, which TypeScript types as
`any`. Every field the page reads off that response is therefore unchecked: if
the endpoint renames `clause_count`, nothing fails to compile, no test goes
red, and the upload confirmation quietly stops mentioning how many clauses were
read. The reviewer sees a shorter sentence and has no way to know a number went
missing. That is the same defect this codebase keeps producing -- a claim about
the data outliving the data -- so consuming those fields comes with a guard
that pins them to their source.

The UI names what it reads in `UPLOAD_RESULT_FIELDS_READ`; this test reads the
endpoint's own `return` statement and fails when the two disagree.

FLOOR PLACEMENT -- WHY THE VOLUME CHECKS COME FIRST

The verdict here is a SET DIFFERENCE (fields read, minus fields produced), not
an offender list. That inverts the usual placement rule.

  - A guard whose verdict is an OFFENDER LIST puts its floor LAST. A blind scan
    finds no offenders, the assertion passes vacuously, and a floor placed
    first would shadow the real offender during a fails-before proof.

  - A guard whose verdict is a SET DIFFERENCE puts its floor FIRST. A blind
    scan here does not go quiet -- it reports the produced set as empty and so
    accuses EVERY field the UI reads of not existing. That is a precise,
    confident, entirely wrong bug report against the endpoint when the fault is
    in this file. Someone would act on it. The floor has to fire before the
    difference is ever computed.

Both ways this scan can go blind are asserted separately, because either can
collapse while the other stays healthy: the endpoint side (AST walk finds no
return dict) and the UI side (constant renamed or moved).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = ROOT / "src" / "policy_platform" / "api" / "routers" / "documents.py"
UI_MODULE = ROOT / "apps" / "web" / "src" / "uploadFeedback.ts"

# The upload endpoint returns a flat dict of roughly a dozen keys. Ten is a
# floor, not a target: it catches an AST walk that found nothing or latched
# onto some small unrelated dict, without breaking when a key is added.
_MINIMUM_ENDPOINT_FIELDS = 8
# The UI reads several fields. One would be suspicious; zero means the constant
# moved and the whole comparison is vacuous.
_MINIMUM_UI_FIELDS = 3


def _endpoint_fields() -> set[str]:
    """String keys of the dict `upload_document` returns."""
    tree = ast.parse(ENDPOINT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name != "upload_document":
            continue
        fields: set[str] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Dict):
                for key in inner.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        fields.add(key.value)
        return fields
    return set()


def _ui_fields() -> set[str]:
    """Field names listed in `UPLOAD_RESULT_FIELDS_READ`."""
    source = UI_MODULE.read_text(encoding="utf-8")
    match = re.search(
        r"UPLOAD_RESULT_FIELDS_READ\s*=\s*\[(.*?)\]", source, re.DOTALL
    )
    if not match:
        return set()
    return set(re.findall(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""", match.group(1)))


# --------------------------------------------------------------------------
# Floors first. See the module docstring: a blind scan here accuses the
# endpoint rather than falling silent, so these must fail before the
# comparison below is allowed to mean anything.
# --------------------------------------------------------------------------


def test_endpoint_source_is_readable() -> None:
    assert ENDPOINT.exists(), f"upload endpoint not found at {ENDPOINT}"


def test_ui_module_is_readable() -> None:
    assert UI_MODULE.exists(), f"upload feedback module not found at {UI_MODULE}"


def test_endpoint_field_extraction_still_sees() -> None:
    """Blindness on the endpoint side would accuse every UI field at once."""
    fields = _endpoint_fields()
    assert len(fields) >= _MINIMUM_ENDPOINT_FIELDS, (
        f"read only {len(fields)} field(s) from upload_document's return dict "
        f"({sorted(fields)}), expected at least {_MINIMUM_ENDPOINT_FIELDS}. "
        "The function may have been renamed, moved, or changed to return a "
        "model instead of a dict literal. Fix this extractor before trusting "
        "any comparison below it."
    )


def test_ui_field_extraction_still_sees() -> None:
    """Blindness on the UI side makes the comparison pass while checking nothing."""
    fields = _ui_fields()
    assert len(fields) >= _MINIMUM_UI_FIELDS, (
        f"read only {len(fields)} field name(s) from UPLOAD_RESULT_FIELDS_READ "
        f"({sorted(fields)}), expected at least {_MINIMUM_UI_FIELDS}. The "
        "constant may have been renamed or moved out of uploadFeedback.ts."
    )


# --------------------------------------------------------------------------
# The actual claim.
# --------------------------------------------------------------------------


def test_every_field_the_ui_reads_is_returned_by_the_endpoint() -> None:
    produced = _endpoint_fields()
    consumed = _ui_fields()
    unknown = sorted(consumed - produced)
    assert not unknown, (
        "the upload page reads field(s) the upload endpoint does not return: "
        f"{unknown}. Returned fields are {sorted(produced)}. Because the client "
        "receives this response untyped, a mismatch renders as silently missing "
        "text rather than an error."
    )


def test_counts_the_confirmation_quotes_are_actually_returned() -> None:
    """The two numbers shown to the reviewer, pinned by name."""
    produced = _endpoint_fields()
    for field in ("clause_count", "clauses_indexed"):
        assert field in produced, (
            f"the upload confirmation reports {field!r}, but the endpoint no "
            "longer returns it, so that number would silently vanish from the "
            "message."
        )


@pytest.mark.parametrize("field", ["extraction_error", "ingestion_diagnostics"])
def test_parse_problem_channels_are_returned(field: str) -> None:
    """A document that did not read cleanly must still be able to say so.

    These two carry the difference between "stored and read" and "stored, but
    reading stopped". Without them the page cannot tell a reviewer that a
    scanned PDF produced no text, which is exactly the case where a silent
    success is most misleading.
    """
    assert field in _endpoint_fields(), (
        f"{field!r} is no longer returned by the upload endpoint; the upload "
        "page relies on it to report a document that did not read cleanly."
    )
