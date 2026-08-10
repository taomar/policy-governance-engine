"""Tests for the governed Search projections.

The gate being protected is "zero draft, rejected, superseded-inactive or
unresolved content in the active runtime projection". These tests concentrate on
the ways that could be violated quietly: a status that slips through, a document
inserted around the builder, or an index that silently holds something other
than what was built.
"""
from __future__ import annotations

import pytest

from policy_platform.infrastructure.search.projection import (
    RUNTIME_ELIGIBLE_STATUSES,
    ProjectionRefused,
    build_review_document,
    build_runtime_document,
    document_hash,
    projection_document_id,
    runtime_query_filter,
    verify_projection,
)

TEXT = "Employees must apply in writing at least five days in advance."
LOCATORS = [{"element_id": "E1", "page": 1, "start": 0, "end": len(TEXT)}]


def _runtime(**overrides) -> dict:
    base = {
        "release_id": "REL-1",
        "rule_id": "r1",
        "status": "approved",
        "policy_title": "HR Special Leave Policy",
        "section_path": ["2. Leave", "2.1 Annual"],
        "exact_text": TEXT,
        "evidence_locators": LOCATORS,
    }
    base.update(overrides)
    return build_runtime_document(**base)


class TestRuntimeEligibility:
    @pytest.mark.parametrize("status", sorted(RUNTIME_ELIGIBLE_STATUSES))
    def test_approved_content_is_accepted(self, status: str) -> None:
        assert _runtime(status=status)["status"] == status

    @pytest.mark.parametrize(
        "status",
        ["draft", "candidate", "needs_changes", "rejected", "superseded", "unresolved", ""],
    )
    def test_unapproved_content_cannot_be_built(self, status: str) -> None:
        """Refusing at build time protects every caller, including ones written
        later by someone who did not know the rule."""

        with pytest.raises(ProjectionRefused):
            _runtime(status=status)

    def test_status_matching_ignores_case_and_padding(self) -> None:
        assert _runtime(status="  Approved ")["status"] == "  Approved "

    def test_a_rule_without_evidence_text_is_refused(self) -> None:
        with pytest.raises(ProjectionRefused, match="no exact evidence"):
            _runtime(exact_text="   ")

    def test_a_rule_without_a_locator_is_refused(self) -> None:
        """A result a reader cannot trace back to the source is not evidence."""

        with pytest.raises(ProjectionRefused, match="no evidence locator"):
            _runtime(evidence_locators=[])


class TestTextSeparation:
    def test_exact_text_is_carried_unchanged(self) -> None:
        assert _runtime()["exact_text"] == TEXT

    def test_retrieval_text_adds_headings_without_touching_exact_text(self) -> None:
        """Collapsing the two is how a heading gets quoted back as policy."""

        document = _runtime()

        assert "HR Special Leave Policy" in document["retrieval_text"]
        assert "2.1 Annual" in document["retrieval_text"]
        assert TEXT in document["retrieval_text"]
        assert "HR Special Leave Policy" not in document["exact_text"]

    def test_retrieval_text_contains_only_source_material(self) -> None:
        """Every hit must be explainable by pointing at the document."""

        document = _runtime()
        for part in document["retrieval_text"].split(" \n"):
            assert part in {TEXT, "HR Special Leave Policy", "2. Leave", "2.1 Annual"}


class TestDocumentIdentity:
    def test_id_is_derived_from_release_and_rule(self) -> None:
        """Republishing must overwrite its own documents, not accumulate a
        second copy beside them."""

        first = _runtime()["id"]
        second = _runtime()["id"]

        assert first == second == projection_document_id(release_id="REL-1", rule_id="r1")

    def test_different_releases_produce_different_documents(self) -> None:
        assert _runtime()["id"] != _runtime(release_id="REL-2")["id"]

    def test_content_hash_excludes_itself(self) -> None:
        document = _runtime()
        assert document_hash(document) == document["content_hash"]

    def test_content_hash_changes_with_content(self) -> None:
        assert _runtime()["content_hash"] != _runtime(exact_text=TEXT + " Amended.")["content_hash"]


class TestReviewProjection:
    def test_review_documents_carry_their_uncertainty(self) -> None:
        """The review surface exists to show what runtime must not."""

        document = build_review_document(
            document_version_id="DV-1",
            candidate_key="c1",
            policy_title="HR Policy",
            section_path=["2. Leave"],
            exact_text=TEXT,
            evidence_locators=LOCATORS,
            review_status="candidate",
            findings=["actor was not determined"],
            provenance_strength="observed",
        )

        assert document["projection_kind"] == "review"
        assert document["status"] == "candidate"
        assert document["findings"] == ["actor was not determined"]
        assert document["provenance_strength"] == "observed"

    def test_review_and_runtime_ids_cannot_collide(self) -> None:
        """One index holding both must not have a candidate shadow an approved
        rule through a shared key."""

        review = build_review_document(
            document_version_id="REL-1",
            candidate_key="r1",
            policy_title="t",
            section_path=[],
            exact_text=TEXT,
            evidence_locators=LOCATORS,
        )
        assert review["id"] != _runtime()["id"]


class TestVerification:
    def test_a_faithful_upload_verifies(self) -> None:
        built = [_runtime(), _runtime(rule_id="r2")]
        assert verify_projection(built, list(built)).ok

    def test_a_missing_document_fails(self) -> None:
        built = [_runtime(), _runtime(rule_id="r2")]
        report = verify_projection(built, built[:1])

        assert not report.ok
        assert report.missing_ids == [built[1]["id"]]
        assert "expected 2" in report.failure_summary()

    def test_an_extra_document_fails(self) -> None:
        built = [_runtime()]
        indexed = built + [_runtime(rule_id="stowaway")]
        report = verify_projection(built, indexed)

        assert not report.ok
        assert report.unexpected_ids

    def test_altered_content_fails(self) -> None:
        """A truncated or partially-applied upload must be detectable.

        The altered copy keeps the original `content_hash`, which is the hard
        case: verification must recompute from the indexed content rather than
        trust the index to report its own corruption.
        """

        built = [_runtime()]
        indexed = [dict(built[0], exact_text="Something else entirely.")]
        report = verify_projection(built, indexed)

        assert not report.ok
        assert report.hash_mismatches == [built[0]["id"]]

    def test_altered_content_with_a_recomputed_hash_also_fails(self) -> None:
        """The other shape: content and hash rewritten together."""

        built = [_runtime()]
        tampered = dict(built[0], exact_text="Something else entirely.")
        tampered["content_hash"] = document_hash(tampered)
        report = verify_projection(built, [tampered])

        assert not report.ok
        assert report.hash_mismatches == [built[0]["id"]]

    def test_ineligible_content_inserted_around_the_builder_is_caught(self) -> None:
        """The build-time refusal is only worth as much as the guarantee that
        nothing was inserted beside it."""

        built = [_runtime()]
        indexed = built + [dict(built[0], id="smuggled", status="draft")]
        report = verify_projection(built, indexed)

        assert not report.ok
        assert "smuggled" in report.ineligible_documents

    def test_review_projections_are_not_status_checked(self) -> None:
        """Drafts are the point of the review projection."""

        built = [
            build_review_document(
                document_version_id="DV-1",
                candidate_key="c1",
                policy_title="t",
                section_path=[],
                exact_text=TEXT,
                evidence_locators=LOCATORS,
            )
        ]
        assert verify_projection(built, list(built), kind="review").ok

    def test_an_empty_projection_verifies(self) -> None:
        assert verify_projection([], []).ok


class TestQueryFilter:
    def test_status_is_always_constrained(self) -> None:
        """Relevance ranks what matches; it cannot exclude a rejected rule that
        happens to be the best textual match."""

        assert "status eq 'approved'" in runtime_query_filter()

    def test_status_cannot_be_widened_by_a_caller(self) -> None:
        import inspect

        signature = inspect.signature(runtime_query_filter)
        assert "status" not in signature.parameters

    def test_optional_dimensions_allow_unscoped_rules(self) -> None:
        """A rule with no jurisdiction applies everywhere, so filtering it out
        would hide global policy from a scoped query."""

        clause = runtime_query_filter(jurisdiction="UK")
        assert "jurisdiction eq 'UK'" in clause
        assert "jurisdiction eq null" in clause

    def test_effective_dates_bound_both_ends(self) -> None:
        clause = runtime_query_filter(as_of="2026-08-10")
        assert "effective_from" in clause
        assert "effective_until" in clause
