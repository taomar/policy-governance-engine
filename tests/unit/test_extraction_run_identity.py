"""Tests for the two pure helpers that give an extraction run a public identity.

Both are user-visible contracts: `ExtractionRun.reference` is the string a
reviewer quotes when asking "which run produced this rule?", and `_page_label`
is the location shown in the live progress readout. Neither touches the
database, so both are covered here rather than in an integration test.
"""

from __future__ import annotations

import uuid

from policy_platform.domain.models import Clause, ExtractionRun
from policy_platform.infrastructure.ai_extraction import _page_label


class TestExtractionRunReference:
    def test_reference_is_derived_from_the_id(self):
        run = ExtractionRun(id=uuid.UUID("e0dafe91-3080-4d6d-8fa7-6287a185b336"))
        assert run.reference == "RUN-E0DAFE91"

    def test_reference_is_stable_for_the_same_run(self):
        run = ExtractionRun(id=uuid.uuid4())
        assert run.reference == run.reference

    def test_distinct_runs_get_distinct_references(self):
        first = ExtractionRun(id=uuid.UUID("11033dae-5fd7-43fb-a731-2604b57d0530"))
        second = ExtractionRun(id=uuid.UUID("963b949e-e101-40e4-88e4-5bbf237751f9"))
        assert first.reference != second.reference

    def test_reference_is_absent_before_the_row_has_an_id(self):
        # A run only becomes quotable once it exists; a half-built object must not
        # invent a reference that will never appear in the database.
        assert ExtractionRun().reference is None


def _clause(page: int | None) -> Clause:
    return Clause(clause_ref="c", text="t", page=page)


class TestPageLabel:
    def test_no_clauses_yields_no_label(self):
        assert _page_label([]) == ""

    def test_unpaginated_clauses_yield_no_label(self):
        # DOCX sources carry no pagination. An empty suffix is correct; "page 0"
        # would be a fabricated location in a system whose whole purpose is
        # traceable provenance.
        assert _page_label([_clause(None), _clause(None)]) == ""

    def test_single_page_is_singular(self):
        assert _page_label([_clause(7), _clause(7)]) == " · page 7"

    def test_span_is_rendered_as_a_range(self):
        assert _page_label([_clause(9), _clause(7), _clause(8)]) == " · pages 7–9"

    def test_range_uses_the_extremes_not_the_batch_order(self):
        assert _page_label([_clause(12), _clause(3)]) == " · pages 3–12"

    def test_unpaginated_clauses_are_ignored_when_others_have_pages(self):
        assert _page_label([_clause(None), _clause(4)]) == " · page 4"
