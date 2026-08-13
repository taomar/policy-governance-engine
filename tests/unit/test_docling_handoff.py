"""Tests for the extraction handoff adapter.

The mapping is where silent corruption would happen — evidence text, identity
and provenance all cross a boundary into a table this pipeline does not own — so
it is a pure function and tested directly. The submission path is tested against
an in-memory double of the repositories, which is enough to prove the properties
that matter (refusal, idempotency, no direct writes) without a database.
"""
from __future__ import annotations

import uuid

import pytest

from policy_platform.contracts.evidence_resolution import ResolvedEvidence
from policy_platform.contracts.extraction_package import (
    ApplicationHandoff,
    CanonicalDocumentRef,
    PolicyExtractionPackage,
    RuleCandidate,
    SourceReleaseRef,
    VerificationSummary,
)
from policy_platform.contracts.graph_run import CoverageReport, ElementCoverage
from policy_platform.infrastructure.docling.handoff import (
    PROVENANCE_KEY,
    HandoffRefused,
    build_candidate_payloads,
    preview_handoff,
    rule_type_for,
    submit_package,
)

TEXT = "Employees must apply in writing."


def _span(evidence_hash: str = "h1", text: str = TEXT, role: str = "target") -> ResolvedEvidence:
    return ResolvedEvidence(
        element_id="E1",
        role=role,  # type: ignore[arg-type]
        exact_text=text,
        page=1,
        page_start_offset=0,
        page_end_offset=len(text),
        element_start_offset=0,
        element_end_offset=len(text),
        evidence_hash=evidence_hash,
    )


def _package(**overrides) -> PolicyExtractionPackage:
    base = {
        "source_release": SourceReleaseRef(document_id="DOC", source_hash="a" * 64),
        "canonical_document": CanonicalDocumentRef(
            document_id="DOC", canonical_hash="b" * 64, parser="docling"
        ),
        "coverage": CoverageReport(
            total_leaf_elements=1,
            elements=[ElementCoverage(element_id="E1", disposition="policy_target")],
        ),
        "evidence_spans": [_span()],
        "canonical_rules": [
            RuleCandidate(
                rule_key="r1",
                title="Written application required",
                modality="must",
                actor="Employees",
                action="apply",
                evidence_hashes=["h1"],
            )
        ],
        "application_handoff": ApplicationHandoff(idempotency_key="key-1"),
    }
    base.update(overrides)
    return PolicyExtractionPackage(**base)


# --------------------------------------------------------------------------
# In-memory repository doubles
# --------------------------------------------------------------------------


class _Row:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _FakeCandidateRepo:
    def __init__(self, store: list[_Row]) -> None:
        self._store = store

    async def list_by_policy_set(self, _policy_set_id, **_kwargs) -> list[_Row]:
        return list(self._store)

    async def create(self, *, policy_set_id, extraction_run_id, rule_type, payload_json) -> _Row:
        row = _Row(
            id=uuid.uuid4(),
            policy_set_id=policy_set_id,
            extraction_run_id=extraction_run_id,
            rule_type=rule_type,
            payload_json=payload_json,
        )
        self._store.append(row)
        return row


class _FakeRunRepo:
    def __init__(self, store: list[_Row]) -> None:
        self._store = store

    async def create(self, **kwargs) -> _Row:
        row = _Row(id=uuid.uuid4(), **kwargs)
        self._store.append(row)
        return row


@pytest.fixture
def fake_repos(monkeypatch):
    candidates: list[_Row] = []
    runs: list[_Row] = []

    from policy_platform.infrastructure.persistence import repositories

    monkeypatch.setattr(
        repositories, "CandidateRuleRepository", lambda _session: _FakeCandidateRepo(candidates)
    )
    monkeypatch.setattr(
        repositories, "ExtractionRunRepository", lambda _session: _FakeRunRepo(runs)
    )
    return candidates, runs


# --------------------------------------------------------------------------


class TestMapping:
    def test_evidence_text_crosses_the_boundary_verbatim(self) -> None:
        """A reviewer must see what the document says, not a summary of it."""

        payloads, _ = build_candidate_payloads(_package())

        assert payloads[0]["evidence"][0]["exact_text"] == TEXT

    def test_evidence_is_embedded_not_referenced(self) -> None:
        """A hash reference would be a dangling pointer once the row is read
        on its own, outside the package."""

        payloads, _ = build_candidate_payloads(_package())
        evidence = payloads[0]["evidence"][0]

        assert "exact_text" in evidence
        assert evidence["page_start_offset"] == 0
        assert evidence["evidence_hash"] == "h1"

    def test_rule_identity_is_preserved(self) -> None:
        payloads, _ = build_candidate_payloads(_package())
        assert payloads[0]["rule_id"] == "r1"

    def test_provenance_ties_the_candidate_to_its_package(self) -> None:
        payloads, _ = build_candidate_payloads(_package())
        provenance = payloads[0][PROVENANCE_KEY]

        assert provenance["source_hash"] == "a" * 64
        assert provenance["canonical_hash"] == "b" * 64
        assert provenance["idempotency_key"] == "key-1"
        assert provenance["parser"] == "docling"

    def test_a_rule_without_resolvable_evidence_is_skipped(self) -> None:
        """A candidate with no evidence is an assertion a reviewer cannot check,
        which is what the pointer-only design exists to prevent."""

        package = _package(
            canonical_rules=[RuleCandidate(rule_key="r1", evidence_hashes=["missing"])]
        )
        payloads, skipped = build_candidate_payloads(package)

        assert payloads == []
        assert skipped and "no resolvable evidence" in skipped[0]

    def test_multi_span_rules_carry_every_role(self) -> None:
        package = _package(
            evidence_spans=[
                _span("h1", TEXT, "target"),
                _span("h2", "This does not apply during probation.", "exception"),
            ],
            canonical_rules=[
                RuleCandidate(rule_key="r1", modality="must", evidence_hashes=["h1", "h2"])
            ],
        )
        payloads, _ = build_candidate_payloads(package)
        roles = {e["role"] for e in payloads[0]["evidence"]}

        assert roles == {"target", "exception"}


class TestRuleType:
    @pytest.mark.parametrize(
        ("modality", "expected"),
        [
            ("must", "obligation"),
            ("must_not", "prohibition"),
            ("may", "permission"),
            ("eligibility", "eligibility"),
            ("authority", "authority"),
            (None, "unclassified"),
            ("something novel", "unclassified"),
        ],
    )
    def test_modality_maps_to_the_platform_vocabulary(
        self, modality: str | None, expected: str
    ) -> None:
        assert rule_type_for({"modality": modality}) == expected

    def test_an_unknown_modality_is_not_guessed_into_a_type(self) -> None:
        """The workbench treats rule_type as classified fact, so a guess there
        is worse than an explicit 'unclassified'."""

        assert rule_type_for({"modality": "possibly obligatory"}) == "unclassified"


class TestRefusal:
    def test_a_package_with_blockers_is_refused(self) -> None:
        package = _package(verification=VerificationSummary(blockers=["evidence mismatch"]))

        with pytest.raises(HandoffRefused, match="verification blockers"):
            preview_handoff(package)

    def test_incomplete_coverage_is_refused(self) -> None:
        coverage = CoverageReport(
            total_leaf_elements=2,
            elements=[ElementCoverage(element_id="E1", disposition="policy_target")],
            unaccounted_element_ids=["E2"],
        )
        with pytest.raises(HandoffRefused, match="coverage is incomplete"):
            preview_handoff(_package(coverage=coverage))

    def test_a_package_without_an_idempotency_key_is_refused(self) -> None:
        """Submitting one would make every retry duplicate the review queue."""

        package = _package(application_handoff=ApplicationHandoff(idempotency_key=""))

        with pytest.raises(HandoffRefused, match="idempotency"):
            preview_handoff(package)

    def test_refusal_is_a_distinct_type_from_a_write_failure(self) -> None:
        """Refusing is correct for an unverified package; retrying it as an
        error would eventually push unverified rules into review."""

        assert issubclass(HandoffRefused, RuntimeError)


class TestPreview:
    def test_preview_reports_what_would_be_created(self) -> None:
        result = preview_handoff(_package())

        assert result.candidates_created == 1
        assert result.idempotency_key == "key-1"
        assert result.already_submitted is False


class TestSubmission:
    async def test_submission_creates_a_run_and_candidates(self, fake_repos) -> None:
        candidates, runs = fake_repos
        result = await submit_package(
            _package(),
            session=object(),
            policy_set_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
        )

        assert result.candidates_created == 1
        assert len(runs) == 1
        assert len(candidates) == 1
        assert candidates[0].rule_type == "obligation"

    async def test_resubmitting_the_same_package_is_a_no_op(self, fake_repos) -> None:
        """A retry must resolve to the same intake, not a second queue entry."""

        candidates, runs = fake_repos
        policy_set_id = uuid.uuid4()
        document_version_id = uuid.uuid4()

        first = await submit_package(
            _package(),
            session=object(),
            policy_set_id=policy_set_id,
            document_version_id=document_version_id,
        )
        second = await submit_package(
            _package(),
            session=object(),
            policy_set_id=policy_set_id,
            document_version_id=document_version_id,
        )

        assert first.already_submitted is False
        assert second.already_submitted is True
        assert second.candidates_created == 0
        assert len(candidates) == 1
        assert len(runs) == 1

    async def test_a_genuinely_different_extraction_submits_separately(
        self, fake_repos
    ) -> None:
        candidates, _ = fake_repos
        policy_set_id = uuid.uuid4()
        document_version_id = uuid.uuid4()

        await submit_package(
            _package(),
            session=object(),
            policy_set_id=policy_set_id,
            document_version_id=document_version_id,
        )
        await submit_package(
            _package(application_handoff=ApplicationHandoff(idempotency_key="key-2")),
            session=object(),
            policy_set_id=policy_set_id,
            document_version_id=document_version_id,
        )

        assert len(candidates) == 2

    async def test_an_unverified_package_is_never_written(self, fake_repos) -> None:
        candidates, runs = fake_repos
        package = _package(verification=VerificationSummary(blockers=["evidence mismatch"]))

        with pytest.raises(HandoffRefused):
            await submit_package(
                package,
                session=object(),
                policy_set_id=uuid.uuid4(),
                document_version_id=uuid.uuid4(),
            )

        assert candidates == []
        assert runs == []
