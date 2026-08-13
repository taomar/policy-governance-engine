"""Tests for Stage 1 verbatim passage extraction.

The verbatim guarantee is the whole reason this stage exists, so these tests
concentrate on the one property that must never regress: text the model did not
copy from the source must not reach Stage 2.
"""
from __future__ import annotations

import json

import pytest

from policy_platform.contracts.passage import PassageExtraction, PassageSource
from policy_platform.infrastructure.extraction.passage_extractor import (
    PassageExtractionError,
    clean_clause_ref,
    parse_passages,
    resolve_span,
    verify_verbatim,
)

SOURCE = (
    "The employee must submit the request within 30 days.\n"
    "If the transaction exceeds SAR 50,000, approval from the Finance Director "
    "is required.\n"
    "The worker recieve the payment not exceeding (90) ninety days."
)


class TestVerifyVerbatim:
    def test_accepts_exact_substring(self):
        assert verify_verbatim("The employee must submit the request within 30 days.", SOURCE)

    def test_accepts_passage_split_across_lines(self):
        # PDF ingestion breaks lines at arbitrary points; the words are identical.
        assert verify_verbatim("approval from the Finance\nDirector is required", SOURCE)

    def test_accepts_curly_quote_and_dash_variation(self):
        source = "The employee\u2019s manager \u2014 or their delegate \u2014 shall approve."
        assert verify_verbatim("The employee's manager - or their delegate - shall approve.", source)

    def test_rejects_reworded_passage(self):
        # Meaning-preserving but not a copy: specification Section 8.
        assert not verify_verbatim("Employees must submit requests within thirty days.", SOURCE)

    def test_rejects_normalized_numbers(self):
        # Specification Section 14: "(90) ninety days" must not become "90 days".
        assert not verify_verbatim("not exceeding 90 days", SOURCE)

    def test_rejects_corrected_spelling(self):
        # Specification Section 15: source errors are preserved, not repaired.
        assert not verify_verbatim("The worker receives the payment", SOURCE)

    def test_rejects_text_synthesized_from_two_locations(self):
        # Specification Section 9: words exist, but not contiguously.
        assert not verify_verbatim(
            "The employee must submit the request. The worker recieve the payment.", SOURCE
        )

    def test_rejects_empty_and_whitespace(self):
        assert not verify_verbatim("", SOURCE)
        assert not verify_verbatim("   \n  ", SOURCE)


class TestParsePassages:
    def _reply(self, **overrides) -> str:
        payload = {
            "document_id": "doc-1",
            "document_name": "Handbook",
            "policy_passages": [
                {
                    "passage_id": "P000001",
                    "classification": "POLICY",
                    "text": "The employee must submit the request within 30 days.",
                    "source": {"clause_ref": "p1-para-1", "page": 1},
                }
            ],
        }
        payload.update(overrides)
        return json.dumps(payload)

    def test_parses_valid_reply(self):
        result = parse_passages(self._reply())
        assert isinstance(result, PassageExtraction)
        assert len(result.policy_passages) == 1
        passage = result.policy_passages[0]
        assert passage.classification == "POLICY"
        assert passage.source.clause_ref == "p1-para-1"

    def test_tolerates_code_fence(self):
        assert len(parse_passages(f"```json\n{self._reply()}\n```").policy_passages) == 1

    def test_empty_passage_list_is_valid(self):
        # A batch of pure boilerplate correctly yields nothing.
        assert parse_passages(self._reply(policy_passages=[])).policy_passages == []

    def test_ambiguous_classification_allowed(self):
        reply = json.loads(self._reply())
        reply["policy_passages"][0]["classification"] = "POLICY_AMBIGUOUS"
        assert parse_passages(json.dumps(reply)).policy_passages[0].classification == "POLICY_AMBIGUOUS"

    def test_rejects_invented_classification(self):
        reply = json.loads(self._reply())
        reply["policy_passages"][0]["classification"] = "DEFINITELY_A_POLICY"
        with pytest.raises(PassageExtractionError, match="contract validation"):
            parse_passages(json.dumps(reply))

    def test_raises_on_empty_response(self):
        with pytest.raises(PassageExtractionError, match="empty response"):
            parse_passages("   ")

    def test_raises_on_unparseable_response(self):
        with pytest.raises(PassageExtractionError, match="unparseable"):
            parse_passages("here are the passages you asked for")

    def test_raises_on_non_object_response(self):
        with pytest.raises(PassageExtractionError, match="expected a JSON object"):
            parse_passages("[]")


class TestResolveSpan:
    """The application copying text from a span reference, rather than trusting
    the model's transcription. This is the strongest guarantee in the pipeline:
    a passage produced this way contains no model-authored character at all."""

    ORDER = ["p1-E000001", "p1-E000002", "p2-E000003"]
    TEXTS = {
        "p1-E000001": "An employee shall be granted annual leave.",
        "p1-E000002": "The leave shall not be less than twenty-one days.",
        "p2-E000003": "Leave may be postponed by agreement.",
    }

    def _source(self, start, end=None):
        return PassageSource(clause_ref=start, end_clause_ref=end)

    def test_single_clause_span_returns_that_clause(self):
        assert resolve_span(self._source("p1-E000002"), self.TEXTS, self.ORDER) == self.TEXTS["p1-E000002"]

    def test_multi_clause_span_joins_in_document_order(self):
        resolved = resolve_span(self._source("p1-E000001", "p2-E000003"), self.TEXTS, self.ORDER)
        assert resolved is not None
        assert resolved.startswith("An employee shall be granted")
        assert "twenty-one days" in resolved
        assert resolved.endswith("by agreement.")

    def test_reversed_span_is_normalized_rather_than_lost(self):
        # An end before its start is a model slip, not an unresolvable
        # reference: both endpoints are real, so the span is still knowable.
        forward = resolve_span(self._source("p1-E000001", "p2-E000003"), self.TEXTS, self.ORDER)
        reversed_ = resolve_span(self._source("p2-E000003", "p1-E000001"), self.TEXTS, self.ORDER)
        assert reversed_ == forward

    def test_unknown_start_is_unresolvable(self):
        # Guessing here would attribute one clause's text to another clause's
        # location, which is worse than returning nothing.
        assert resolve_span(self._source("p9-E999999"), self.TEXTS, self.ORDER) is None

    def test_missing_start_is_unresolvable(self):
        assert resolve_span(self._source(None), self.TEXTS, self.ORDER) is None

    def test_unknown_end_degrades_to_the_known_start(self):
        resolved = resolve_span(self._source("p1-E000001", "p9-E999999"), self.TEXTS, self.ORDER)
        assert resolved == self.TEXTS["p1-E000001"]

    def test_blank_clause_text_resolves_to_none_not_empty_string(self):
        assert resolve_span(self._source("only"), {"only": "   "}, ["only"]) is None


class TestCleanClauseRef:
    """An agent will decorate an addressing label no matter how it is asked not
    to. Discarding a correct answer over formatting is a self-inflicted loss."""

    def test_bare_ref_is_unchanged(self):
        assert clean_clause_ref("p3-E000016") == "p3-E000016"

    def test_strips_brackets_and_prefix(self):
        assert clean_clause_ref("[clause_ref=p3-E000016]") == "p3-E000016"

    def test_strips_trailing_section_label(self):
        assert clean_clause_ref("p3-E000016 (Article 2)") == "p3-E000016"

    def test_none_and_blank_are_none(self):
        assert clean_clause_ref(None) is None
        assert clean_clause_ref("   ") is None


class TestResolveSpanToleratesDecoratedRefs:
    def test_decorated_ref_still_resolves(self):
        texts = {"p1-E000001": "An employee shall be granted annual leave."}
        source = PassageSource(clause_ref="[clause_ref=p1-E000001 (Article 109)]")
        assert resolve_span(source, texts, ["p1-E000001"]) == texts["p1-E000001"]
