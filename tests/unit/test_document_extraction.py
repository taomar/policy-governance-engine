"""Regression tests for running-header/footer suppression.

These cover a real historical defect: running page-footer text (e.g. "Policies
and Procedures Template - Page 7") was being baked into clause bodies,
polluting search results and Ask-AI answers with meaningless fragments.

The parsing implementation was later replaced (see
`infrastructure/ingestion/document_ingestion.py`), so these tests were retargeted at the
new module. The *assertions* are deliberately unchanged in substance: a
recurring page-edge line is boilerplate, a recurring in-body subheading is
content, and a short document has neither. Retargeting a regression test is
legitimate; weakening one is not, because the bug it guards against is a
property of the product, not of the module that happened to implement it.
"""
from __future__ import annotations

from policy_platform.infrastructure.ingestion.document_ingestion import (
    _Line,
    _detect_boilerplate,
    _normalize_line,
)


def _page(lines: list[str], page: int) -> list[_Line]:
    """Build page lines with plausible geometry.

    Only vertical order matters to boilerplate detection, so `top` increments
    per line and the remaining geometry is held constant.
    """

    return [
        _Line(
            text=text,
            top=float(idx * 12),
            bottom=float(idx * 12 + 10),
            x0=50.0,
            x1=500.0,
            size=11.0,
            page=page,
        )
        for idx, text in enumerate(lines)
    ]


class TestNormalizeLine:
    def test_digits_replaced_with_placeholder(self):
        assert _normalize_line("Page 7") == _normalize_line("Page 51")

    def test_whitespace_collapsed_and_lowercased(self):
        assert _normalize_line("  Foo   Bar  ") == _normalize_line("foo bar")


class TestDetectBoilerplate:
    def test_repeated_footer_line_is_detected(self):
        pages = [
            _page(
                [
                    "Some heading",
                    f"Body text for page {i}.",
                    "More body text.",
                    f"Policies and Procedures Template - Page {i}",
                ],
                i,
            )
            for i in range(1, 11)
        ]
        boilerplate = _detect_boilerplate(pages)
        assert _normalize_line("Policies and Procedures Template - Page 1") in boilerplate

    def test_repeated_in_body_subheading_is_not_treated_as_boilerplate(self):
        # A structural subheading that repeats on most pages but sits away from
        # the page edges must be preserved as real content. This is the false
        # positive the positional-window rule addresses.
        pages = [
            _page(
                [
                    f"Policy Title {i}",
                    "Policy and Procedure Statement",
                    f"Body text describing policy {i} in detail across a few lines.",
                    "Second line of body text.",
                    "Third line of body text.",
                    "Fourth line of body text.",
                    f"Policies and Procedures Template - Page {i}",
                ],
                i,
            )
            for i in range(1, 11)
        ]
        boilerplate = _detect_boilerplate(pages)
        assert _normalize_line("Policy and Procedure Statement") not in boilerplate
        assert _normalize_line("Policies and Procedures Template - Page 1") in boilerplate

    def test_short_documents_produce_no_boilerplate(self):
        pages = [_page(["Page one body."], 1), _page(["Page two body."], 2)]
        assert _detect_boilerplate(pages) == set()

    def test_infrequent_repeated_line_is_not_boilerplate(self):
        # A line repeating on only a small minority of pages (below both the
        # fraction and absolute-count thresholds) should not be stripped.
        pages = [_page([f"Unique body text {i}."], i) for i in range(10)]
        pages[0].extend(_page(["Occasional aside."], 0))
        pages[1].extend(_page(["Occasional aside."], 1))
        boilerplate = _detect_boilerplate(pages)
        assert _normalize_line("Occasional aside.") not in boilerplate
