"""Grouping keys on structure, never on a particular document.

THE CONSTRAINT

    Nothing may key on a particular document, heading, numbering style or
    language. The documents in the database are witnesses, never targets.

The grouping was measured against two handbooks, so the standing risk is that
it encodes what those two happen to look like: latin script, arabic numerals,
`1.`/`1.1` numbering, headings in English. A third document arriving with roman
numerals, or no numbering at all, or in a right-to-left script, must group by
the same rule and not silently degrade to one policy per passage.

WHAT "GENERAL" MEANS OPERATIONALLY, AND WHY THAT IS TESTABLE

`provision_key_for` sees a source release, a chain of heading *texts*, and an
occurrence number. It never sees a page, a document title, a numbering style or
a language tag, because it is not given them. So generality here is not a
property to be asserted about behaviour on samples — it is a property of the
function's inputs, and the tests below check both: that the same structure in
five different scripts and numbering styles produces the same *shape* of
grouping, and that the key function's own source contains no literal from any
document.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from policy_platform.contracts import provision_grouping
from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.provision_grouping import (
    group_into_provisions,
    normalise_heading,
    provision_key_for,
)
from policy_platform.contracts.structural_graph import build_structural_graph

_RELEASE = "release-1"


def _element(element_id: str, text: str, kind: str, order: int) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type=kind,  # type: ignore[arg-type]
        logical_order=order,
        text=text,
        source_fragments=[
            SourceFragment(page=1, start_offset=0, end_offset=len(text), text=text)
        ],
    )


def _document(rows: list[tuple[str, str, str]]) -> CanonicalDocument:
    """`rows` is (element_id, text, element_type), all on one page."""

    elements = [
        _element(eid, text, kind, order) for order, (eid, text, kind) in enumerate(rows)
    ]
    return CanonicalDocument(
        document_id="DOC",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text="")],
        elements=elements,
        parser="docling",
    )


def _shape(rows: list[tuple[str, str, str]]) -> list[int]:
    """How many elements each provision claims, in document order.

    The heading counts as one of its own provision's elements, so a heading
    with two paragraphs under it reports 3.
    """

    document = _document(rows)
    provisions = group_into_provisions(
        document, build_structural_graph(document), source_release=_RELEASE
    )
    return [len(provision.element_ids) for provision in provisions]


#: The same document, six ways. One heading with two paragraphs, then a second
#: heading with one. Any grouping that is general reports [3, 2] for all six --
#: each heading plus what it governs.
_SAME_STRUCTURE = {
    "arabic numerals, english": [
        ("E1", "1. Employment", "heading"),
        ("E2", "Staff shall hold a valid permit.", "paragraph"),
        ("E3", "The employer bears the renewal cost.", "paragraph"),
        ("E4", "2. Leave", "heading"),
        ("E5", "Annual leave accrues monthly.", "paragraph"),
    ],
    "roman numerals": [
        ("E1", "IV. Employment", "heading"),
        ("E2", "Staff shall hold a valid permit.", "paragraph"),
        ("E3", "The employer bears the renewal cost.", "paragraph"),
        ("E4", "V. Leave", "heading"),
        ("E5", "Annual leave accrues monthly.", "paragraph"),
    ],
    "lettered": [
        ("E1", "(a) Employment", "heading"),
        ("E2", "Staff shall hold a valid permit.", "paragraph"),
        ("E3", "The employer bears the renewal cost.", "paragraph"),
        ("E4", "(b) Leave", "heading"),
        ("E5", "Annual leave accrues monthly.", "paragraph"),
    ],
    "no numbering at all": [
        ("E1", "Employment", "heading"),
        ("E2", "Staff shall hold a valid permit.", "paragraph"),
        ("E3", "The employer bears the renewal cost.", "paragraph"),
        ("E4", "Leave", "heading"),
        ("E5", "Annual leave accrues monthly.", "paragraph"),
    ],
    "right-to-left script": [
        ("E1", "\u0627\u0644\u062a\u0648\u0638\u064a\u0641", "heading"),
        ("E2", "\u064a\u062c\u0628 \u0623\u0646 \u064a\u062d\u0645\u0644 \u0627\u0644\u0645\u0648\u0638\u0641 \u062a\u0635\u0631\u064a\u062d\u0627\u064b.", "paragraph"),
        ("E3", "\u064a\u062a\u062d\u0645\u0644 \u0635\u0627\u062d\u0628 \u0627\u0644\u0639\u0645\u0644 \u062a\u0643\u0644\u0641\u0629 \u0627\u0644\u062a\u062c\u062f\u064a\u062f.", "paragraph"),
        ("E4", "\u0627\u0644\u0625\u062c\u0627\u0632\u0629", "heading"),
        ("E5", "\u062a\u0633\u062a\u062d\u0642 \u0627\u0644\u0625\u062c\u0627\u0632\u0629 \u0634\u0647\u0631\u064a\u0627\u064b.", "paragraph"),
    ],
    "ideographic script": [
        ("E1", "\u7b2c\u4e00\u7ae0\u3000\u96c7\u7528", "heading"),
        ("E2", "\u5f93\u696d\u54e1\u306f\u8a31\u53ef\u3092\u4fdd\u6301\u3059\u308b\u3053\u3068\u3002", "paragraph"),
        ("E3", "\u66f4\u65b0\u8cbb\u7528\u306f\u4f7f\u7528\u8005\u304c\u8ca0\u62c5\u3059\u308b\u3002", "paragraph"),
        ("E4", "\u7b2c\u4e8c\u7ae0\u3000\u4f11\u6687", "heading"),
        ("E5", "\u5e74\u6b21\u4f11\u6687\u306f\u6bce\u6708\u767a\u751f\u3059\u308b\u3002", "paragraph"),
    ],
}


@pytest.mark.parametrize("style", sorted(_SAME_STRUCTURE))
def test_the_same_structure_groups_the_same_way_in_every_style(style: str) -> None:
    assert _shape(_SAME_STRUCTURE[style]) == [3, 2], (
        f"grouping changed shape for '{style}'. The six documents state the "
        "same structure in different scripts and numbering styles; a grouping "
        "that keys on structure cannot tell them apart."
    )


def test_the_shape_assertion_can_fail() -> None:
    # CONTROL. The parametrised test above would pass on a grouping that
    # returned [3, 2] unconditionally.
    rows = [
        ("E1", "1. Employment", "heading"),
        ("E2", "Staff shall hold a valid permit.", "paragraph"),
        ("E3", "2. Leave", "heading"),
        ("E4", "Annual leave accrues monthly.", "paragraph"),
        ("E5", "Leave is approved by the manager.", "paragraph"),
    ]
    assert _shape(rows) == [2, 3]


def test_a_document_with_no_headings_still_produces_a_provision() -> None:
    """The degenerate case must extract, not vanish.

    A scanned circular with no heading structure at all is a document this
    system is meant to serve. It groups into one provision with no heading
    chain rather than into none.
    """

    rows = [
        ("E1", "Staff shall hold a valid permit.", "paragraph"),
        ("E2", "The employer bears the renewal cost.", "paragraph"),
    ]
    document = _document(rows)
    provisions = group_into_provisions(
        document, build_structural_graph(document), source_release=_RELEASE
    )

    assert [len(p.element_ids) for p in provisions] == [2]
    assert provisions[0].heading_path == ()


def test_normalisation_keeps_the_numbering_the_document_wrote() -> None:
    """`1. Leave` and `2. Leave` are two sections, not one seen twice.

    Stripping numbering would look like tidying and would merge every
    identically-titled clause in a numbered document into a single policy. The
    normalisation is case, width and whitespace only.
    """

    assert normalise_heading("1. Leave") != normalise_heading("2. Leave")
    assert normalise_heading("  1.   LEAVE  ") == normalise_heading("1. Leave")
    # Full-width digits and latin letters fold to their ordinary forms, which
    # is a Unicode fact rather than a fact about any document.
    assert normalise_heading("\uff11. \uff2c\uff45\uff41\uff56\uff45") == normalise_heading("1. Leave")


def test_the_key_is_blind_to_everything_except_structure() -> None:
    """Its signature is the argument. It cannot key on what it is not given."""

    parameters = inspect.signature(provision_key_for).parameters
    assert set(parameters) == {"source_release", "heading_texts", "occurrence"}, (
        "provision_key_for gained a parameter. Anything beyond the release, "
        "the heading chain and which statement of it this is, is a fact about "
        "a particular document rather than about structure."
    )


def test_the_same_chain_in_two_releases_gets_two_keys() -> None:
    # CONTROL for the blindness test: scoping by release is the one piece of
    # document identity the key is *supposed* to carry, because element ids
    # restart at E000001 in every document.
    a = provision_key_for(source_release="rel-a", heading_texts=("1. Leave",), occurrence=0)
    b = provision_key_for(source_release="rel-b", heading_texts=("1. Leave",), occurrence=0)
    assert a != b


def test_the_grouping_module_recognises_no_document_text() -> None:
    """No heading, phrase or element id from the two witnesses is *executable*.

    Read from the syntax tree rather than the file, and deliberately narrower
    than a text search: the module's prose *does* discuss the violations
    schedule, because that is the case the adjacency rule was measured
    against, and describing your evidence is not the same as keying on it. So
    the assertion covers string constants the code can compare against and the
    names it defines — the two places a special case could actually live —
    while leaving comments and docstrings free to name what was measured.
    """

    tree = ast.parse(inspect.getsource(provision_grouping))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    executable: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings:
                executable.append(node.value)
        elif isinstance(node, ast.Name):
            executable.append(node.id)
        elif isinstance(node, ast.Attribute):
            executable.append(node.attr)

    forbidden = (
        "iqama",
        "sponsorship",
        "handbook",
        "violation",
        "penalt",
        "e0000",
        "employment",
        "leave",
    )
    haystack = " ".join(executable).lower()
    hits = sorted(word for word in forbidden if word in haystack)
    assert not hits, (
        f"provision_grouping compares against or defines {hits}. The documents "
        "in the database are witnesses, never targets: grouping must be decided "
        "by structure the document declares, not by text this codebase "
        "recognises."
    )


def test_the_literal_scan_looks_at_something() -> None:
    # CONTROL. The test above passes trivially if the tree walk collects
    # nothing -- an ast API change, a rename, an early return.
    tree = ast.parse(inspect.getsource(provision_grouping))
    names = [node.id for node in ast.walk(tree) if isinstance(node, ast.Name)]
    assert len(names) > 20
