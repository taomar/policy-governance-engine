"""A verification must not call correct evidence an error.

THE DEFECT THIS PINS
--------------------
``verify_fragments`` compared ``raw[start:end] == text`` and reported every
inequality as "offsets do not resolve to the recorded text". That sentence is
an overclaim for one whole class of input.

Where a source interleaves two elements' characters in one run - which any
two-column table does by construction, and which a bilingual table does on
every row - a single ``(start, end)`` pair cannot isolate one element. The
recorded text is present at the offsets given, in order, and is correct. Only
the two-offset *representation* is inadequate.

The consequence was not cosmetic. On the legacy path this raised a
``severity="error"`` ingestion diagnostic on a correctly-ingested document. On
the docling path it *raised*, aborting the conversion, so one unaddressable
table row would store the whole document with zero clauses.

WHY THE OBVIOUS FIX WOULD HAVE BEEN WORSE
-----------------------------------------
The tempting rule is "excuse it if the recorded text is an ordered subsequence
of the window". That is far too weak to excuse anything: ``"shall pay"`` is an
ordered subsequence of ``"shall not pay"``, so a dropped negation would be
excused exactly like an interleaved column. ``test_dropped_content_is_still_an_error``
is the test that would fail under that rule, and it is the reason the check
also requires the skipped characters to be *claimed by a named neighbour* -
because dropped content belongs to nobody.

FLOOR PLACEMENT
---------------
The assertions that scan for call sites are set-difference checks: their
verdict is what the scan failed to find, so a scan that silently matches
nothing produces a confident, entirely wrong pass. Those floors go FIRST.
The offender-style assertions come after.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from policy_platform.contracts.canonical_document import (
    UNRESOLVED_FRAGMENT_RESOLUTIONS,
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "policy_platform"


def _document(page_text: str, elements: list[CanonicalElement]) -> CanonicalDocument:
    return CanonicalDocument(
        document_id="d",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text=page_text)],
        elements=elements,
        parser="test",
    )


def _element(element_id: str, text: str, start: int, end: int) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type="table_row",
        logical_order=0,
        text=text,
        source_fragments=[
            SourceFragment(page=1, start_offset=start, end_offset=end, text=text)
        ],
    )


# --------------------------------------------------------------------------
# FLOORS - these run first because every assertion below them is only as
# meaningful as the thing it searched actually existing.
# --------------------------------------------------------------------------


class TestTheGroundIsThere:
    def test_every_resolution_value_is_classified_as_failure_or_not(self):
        """No resolution may be silently neither, which is how a case escapes."""
        from policy_platform.contracts import canonical_document as module

        declared = set(module.FragmentResolution.__args__)
        assert len(declared) >= 5, f"expected the full resolution set, got {declared}"
        assert UNRESOLVED_FRAGMENT_RESOLUTIONS <= declared
        # "resolved" and "span_not_isolating" are the two that must NOT be failures.
        assert declared - UNRESOLVED_FRAGMENT_RESOLUTIONS == {
            "resolved",
            "span_not_isolating",
        }

    def test_the_classifier_is_reachable_from_the_document(self):
        """A classifier nothing calls is the failure mode this repo keeps hitting."""
        source = inspect.getsource(CanonicalDocument.verify_fragments_detailed)
        assert "_classify_fragment_text(" in source

    def test_verify_fragments_still_delegates_to_the_classifier(self):
        """If the two diverge, the string list stops matching the verdicts."""
        source = inspect.getsource(CanonicalDocument.verify_fragments)
        assert "verify_fragments_detailed()" in source
        assert "finding.resolves" in source

    def test_the_call_sites_this_change_affects_still_exist(self):
        """Floor for the scan below: if these files moved, absence proves nothing."""
        callers = {
            "infrastructure/ingestion/document_ingestion.py": 1,
            "infrastructure/docling/converter.py": 1,
            "infrastructure/docling/pipeline.py": 1,
            "infrastructure/docling/shadow_comparison.py": 2,
        }
        found = {}
        for relative, expected in callers.items():
            path = SRC / relative
            assert path.exists(), f"{relative} has moved; this scan proves nothing"
            found[relative] = path.read_text(encoding="utf-8").count("verify_fragments()")
            assert found[relative] >= expected, (
                f"{relative} calls verify_fragments() {found[relative]} time(s), "
                f"expected at least {expected}"
            )
        assert sum(found.values()) >= 5, f"floor not met: {found}"


# --------------------------------------------------------------------------
# The behaviour itself.
# --------------------------------------------------------------------------


class TestASharedSpanIsNotAnError:
    """Two cells interleaved in one run. Structural, not language-specific."""

    #: "AAAA" and "BBBB" interleaved, exactly as a two-column row is emitted.
    PAGE = "AA BB AA BB"

    def _interleaved(self) -> CanonicalDocument:
        return _document(
            self.PAGE,
            [
                _element("E1", "AA AA", 0, 11),
                _element("E2", "BB BB", 0, 11),
            ],
        )

    def test_it_is_not_reported_as_a_failure(self):
        assert self._interleaved().verify_fragments() == []

    def test_it_is_classified_as_a_span_that_cannot_isolate(self):
        resolutions = {
            f.element_id: f.resolution
            for f in self._interleaved().verify_fragments_detailed()
        }
        assert resolutions == {"E1": "span_not_isolating", "E2": "span_not_isolating"}

    def test_the_reason_names_the_neighbour_that_shares_the_range(self):
        finding = self._interleaved().fragments_with_shared_spans()[0]
        assert "E2" in finding.detail
        assert "no single span can isolate it" in finding.detail

    def test_removing_the_error_does_not_create_silence(self):
        """The whole point: it stops being an error, it does not stop being said."""
        diagnostics = self._interleaved().shared_span_diagnostics()
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "fragment_span_not_isolating"
        assert diagnostics[0].severity == "info"
        assert "E1" in diagnostics[0].detail

    def test_a_clean_document_produces_no_such_diagnostic(self):
        """Guards against the diagnostic firing on everything, which is the
        same failure as the error it replaced."""
        clean = _document("AA BB", [_element("E1", "AA", 0, 2)])
        assert clean.shared_span_diagnostics() == []
        assert clean.verify_fragments() == []

    def test_the_severity_keeps_the_document_presenting_as_clean(self):
        """An info diagnostic must not flip the ingestion status built in 0152b70."""
        from policy_platform.api.schemas import INGESTION_STATUS_OK, ingestion_status_of

        diagnostics = [d.model_dump() for d in self._interleaved().shared_span_diagnostics()]
        assert ingestion_status_of(diagnostics, None) == INGESTION_STATUS_OK


class TestTheDetectorStillSees:
    """Everything that was an error before must still be one."""

    def test_wrong_text_is_still_an_error(self):
        document = _document(
            "The employer shall keep records.",
            [_element("E1", "Wrong text!!", 0, 12)],
        )
        assert len(document.verify_fragments()) == 1
        assert document.verify_fragments_detailed()[0].resolution == "text_absent"

    def test_dropped_content_is_still_an_error(self):
        """THE test. A dropped negation is an ordered subsequence of the source.

        Under a subsequence-only rule this document would pass, and the platform
        would record "shall pay" as faithful evidence for a page that says
        "shall not pay". Nothing else in this file matters more.
        """
        document = _document(
            "the employer shall not pay the fee",
            [_element("E1", "the employer shall pay the fee", 0, 34)],
        )
        assert document.verify_fragments_detailed()[0].resolution == "text_absent"
        assert len(document.verify_fragments()) == 1
        assert document.fragments_with_shared_spans() == []

    def test_dropped_content_is_an_error_even_beside_a_real_neighbour(self):
        """The neighbour must claim the skipped characters, not merely exist."""
        document = _document(
            "the employer shall not pay the fee",
            [
                _element("E1", "the employer shall pay the fee", 0, 34),
                # A real neighbour, but elsewhere on the page.
                _element("E2", "the fee", 27, 34),
            ],
        )
        assert document.verify_fragments_detailed()[0].resolution == "text_absent"
        assert len(document.verify_fragments()) >= 1

    def test_a_missing_page_is_still_an_error(self):
        document = _document("text", [_element("E1", "text", 0, 4)])
        document.elements[0].source_fragments[0].page = 9
        assert len(document.verify_fragments()) == 1
        assert document.verify_fragments_detailed()[0].resolution == "page_missing"

    def test_differing_whitespace_is_still_an_error(self):
        """Not excused. Nothing has shown it harmless, so the guard is not widened."""
        document = _document("the  employer", [_element("E1", "the employer", 0, 13)])
        assert document.verify_fragments_detailed()[0].resolution == "whitespace_only"
        assert len(document.verify_fragments()) == 1

    def test_an_empty_fragment_over_real_characters_is_an_error(self):
        document = _document("the employer", [_element("E1", "   ", 0, 12)])
        assert document.verify_fragments_detailed()[0].resolution == "text_absent"

    def test_an_exact_match_is_still_reported_as_resolved(self):
        document = _document("the employer", [_element("E1", "the employer", 0, 12)])
        findings = document.verify_fragments_detailed()
        assert [f.resolution for f in findings] == ["resolved"]
        assert findings[0].resolves is True


class TestTheRuleIsGeneral:
    def test_it_does_not_branch_on_language_script_or_document(self):
        """The fix must not be a bilingual special case."""
        from policy_platform.contracts import canonical_document as module

        source = inspect.getsource(module._classify_fragment_text)
        for forbidden in ("arabic", "rtl", "bilingual", "\\u0600", "lang", "handbook"):
            assert forbidden not in source.lower(), (
                f"{forbidden!r} appears in the classifier; the rule must be a "
                "property of the strings, not of the document"
            )

    def test_the_same_shape_holds_for_a_latin_only_table(self):
        """Same structure, no non-Latin script anywhere: still excused."""
        document = _document(
            "Leave 30 Salary 12",
            [
                _element("E1", "Leave Salary", 0, 18),
                _element("E2", "30 12", 0, 18),
            ],
        )
        assert document.verify_fragments() == []
        assert len(document.fragments_with_shared_spans()) == 2


class TestTheUploadRouteCarriesIt:
    def test_the_upload_appends_the_shared_span_diagnostic(self):
        """Storing it was the point of 0152b70; producing it is the point here."""
        source = (SRC / "api" / "routers" / "documents.py").read_text(encoding="utf-8")
        assert "shared_span_diagnostics()" in source
        assert "ingestion_diagnostics.extend(" in source

    def test_it_is_appended_after_the_warning_filter_not_through_it(self):
        """ingestion_warnings keeps only warning+error, so an info routed through
        it would be dropped and the finding would be silent again."""
        source = (SRC / "api" / "routers" / "documents.py").read_text(encoding="utf-8")
        assert "ingestion_warnings(canonical)" in source, (
            "the warning filter call has moved; this ordering check proves nothing"
        )
        assert "shared_span_diagnostics()" in source, (
            "the upload never asks for shared-span findings, so a document whose "
            "evidence shares a character range reports nothing at all"
        )
        assert source.index("shared_span_diagnostics()") > source.index(
            "ingestion_warnings(canonical)"
        ), "the info diagnostic must be appended after the filter, not through it"

    def test_the_diagnostic_survives_the_json_round_trip_the_column_stores(self):
        import json

        document = _document(
            "AA BB AA BB", [_element("E1", "AA AA", 0, 11), _element("E2", "BB BB", 0, 11)]
        )
        payload = [d.model_dump() for d in document.shared_span_diagnostics()]
        restored = json.loads(json.dumps(payload))
        assert restored[0]["code"] == "fragment_span_not_isolating"
        assert restored[0]["severity"] == "info"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
