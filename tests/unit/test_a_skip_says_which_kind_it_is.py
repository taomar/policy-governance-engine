"""A skip that was never read and a skip that was declined are not the same event.

The extraction ledger appends to one flat list from three places. Two of them
mean roughly fifteen clauses — some pages of the document — were never read.
One means a sentence was read and judged to carry no rule. Until these carried a
`kind`, a reviewer saw the same `skipped: 10` in both worlds, and every reading
of that number was wrong in one direction or the other:

- Read as harmless, a run that lost two batches reported ``status="completed"``
  and looked identical to a clean one.
- Derived as a coverage shortfall from the bare count, a clean 45-page run with
  ten non-normative sentences announced that it "did not read the whole
  document" — and, because ``completed_with_gaps`` disqualifies a run as a delta
  baseline, quietly stopped being comparable.

Measured on RUN-83257A81: 27 batches, 0 unread, 10 read-and-declined. Both
readings above get that run wrong.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    PolicyFormulation,
)
from policy_platform.infrastructure.extraction.formulation_mapping import (
    SKIP_BATCH_UNREAD,
    SKIP_DISCARDED,
    SKIP_NOT_EXTRACTED,
    formulation_to_candidate_rules,
    skip_breaks_coverage,
)


def _map(policies: list[CanonicalPolicy]):
    return formulation_to_candidate_rules(
        PolicyFormulation(canonical_policies=policies),
        policy_set_id="test-set",
        extraction_run_id="test-run",
        deployment_name="test",
        prompt_version="test",
        parser_version="test",
    )


def test_a_non_normative_sentence_is_recorded_as_read_and_declined() -> None:
    """The ten skips on the live run. Coverage was complete; a judgement was made.

    "GMU is fully committed to equal opportunity at all levels..." was one of
    them, so this is not a category that can be assumed to be boilerplate — but
    it is a category in which the document was read.
    """

    _, skipped = _map(
        [
            CanonicalPolicy(
                source_text="GMU is fully committed to equal opportunity at all levels.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.NON_NORMATIVE,
                    subject="GMU",
                    predicate="is committed to",
                    object="equal opportunity",
                ),
            )
        ]
    )

    assert [s["kind"] for s in skipped] == [SKIP_NOT_EXTRACTED]
    assert skip_breaks_coverage(skipped[0]) is False


def test_a_policy_with_no_rule_is_recorded_as_discarded() -> None:
    """Read, but lost to a fault rather than to a judgement.

    Still not a coverage hole — the sentence reached the formulator — but it is
    a recall loss, and it is not the same event as declining to extract.
    """

    _, skipped = _map([CanonicalPolicy(source_text="A sentence.", rule=None)])

    assert [s["kind"] for s in skipped] == [SKIP_DISCARDED]
    assert skip_breaks_coverage(skipped[0]) is False


def test_every_skip_declares_its_kind() -> None:
    """A skip site that forgets is the defect this vocabulary exists to stop."""

    _, skipped = _map(
        [
            CanonicalPolicy(source_text="A sentence.", rule=None),
            CanonicalPolicy(
                source_text="Boilerplate.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.NON_NORMATIVE, subject="x", predicate="y"
                ),
            ),
        ]
    )

    assert len(skipped) == 2
    assert all("kind" in s for s in skipped)
    assert all("reason" in s and "item" in s for s in skipped)


def test_an_unread_batch_breaks_coverage() -> None:
    """The kind the two batch-level failure paths in ai_extraction record."""

    assert skip_breaks_coverage({"item": "p12", "reason": "...", "kind": SKIP_BATCH_UNREAD}) is True


def test_an_untagged_skip_is_treated_as_unread() -> None:
    """Fail towards the alarm.

    A skip site added later without a kind should make the run look partial
    rather than be silently counted as harmless — the direction that gets
    noticed is the safe default.
    """

    assert skip_breaks_coverage({"item": "p12", "reason": "something new"}) is True


@pytest.mark.parametrize(
    "kinds,expected_complete",
    [
        ([], True),
        ([SKIP_NOT_EXTRACTED] * 10, True),
        ([SKIP_DISCARDED, SKIP_NOT_EXTRACTED], True),
        ([SKIP_BATCH_UNREAD], False),
        ([SKIP_NOT_EXTRACTED] * 10 + [SKIP_BATCH_UNREAD], False),
    ],
)
def test_coverage_is_decided_only_by_unread_batches(kinds, expected_complete) -> None:
    """RUN-83257A81 is the second row: ten declined sentences, full coverage."""

    skips = [{"item": "i", "reason": "r", "kind": k} for k in kinds]

    assert (not [s for s in skips if skip_breaks_coverage(s)]) is expected_complete


class _Run:
    """Stands in for an ExtractionRun row; _run_coverage reads one attribute."""

    def __init__(self, skipped_json):
        self.skipped_json = skipped_json


def test_a_run_that_kept_no_record_reports_no_coverage_claim() -> None:
    """Every run predating the column. None, not zeroes.

    Reporting `batches_unread: 0` for a run that never stored its skip list
    would invent a coverage claim nobody made — the same class of error as
    reading `status="completed"` as proof of full coverage.
    """
    from policy_platform.api.routers.ai import _run_coverage

    assert _run_coverage(_Run(None)) is None


def test_the_reviewer_surface_separates_unread_from_declined() -> None:
    """The shape RUN-83257A81 should have reported: complete, ten declined."""
    from policy_platform.api.routers.ai import _run_coverage

    coverage = _run_coverage(
        _Run([{"item": f"s{i}", "reason": "non_normative", "kind": SKIP_NOT_EXTRACTED} for i in range(10)])
    )

    assert coverage["complete"] is True
    assert coverage["batches_unread"] == 0
    assert coverage["read_not_extracted"] == 10
    # The entries, not just the count. A reviewer judging coverage needs to see
    # that the equal-opportunity commitment was one of them.
    assert len(coverage["skipped"]) == 10


def test_a_lost_batch_shows_as_incomplete_on_the_reviewer_surface() -> None:
    from policy_platform.api.routers.ai import _run_coverage

    coverage = _run_coverage(
        _Run(
            [
                {"item": "batch 7", "reason": "timeout", "kind": SKIP_BATCH_UNREAD},
                {"item": "s1", "reason": "non_normative", "kind": SKIP_NOT_EXTRACTED},
            ]
        )
    )

    assert coverage["complete"] is False
    assert coverage["batches_unread"] == 1
    assert coverage["read_not_extracted"] == 1


def test_an_untagged_stored_skip_counts_as_unread_on_the_surface() -> None:
    """Same fail-towards-the-alarm default as skip_breaks_coverage.

    Rows written before the vocabulary existed have no kind. Treating them as
    harmless would let an old lost-batch run read as fully covered.
    """
    from policy_platform.api.routers.ai import _run_coverage

    coverage = _run_coverage(_Run([{"item": "x", "reason": "who knows"}]))

    assert coverage["complete"] is False
    assert coverage["batches_unread"] == 1
