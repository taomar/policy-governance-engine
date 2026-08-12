"""The latest reading of a sentence is the one the queue shows.

A re-run records the reading it replaces as its `baseline_candidate_id`, so the
successor relation is already in the data — held by the wrong end of the pair.
Nothing said which record was current, and the consequence was visible: publish
v1, extract again, publish v2, and both sit in the queue with nothing to order
them.

`superseded_at` does not answer this. It is deliberately not set for a candidate
a human has published, because a re-run is a machine action and must not bury
someone's decision. That is right, and it is why the answer has to be derived.

Derived over the set returned rather than globally, because being latest depends
on what was asked for: opening one extraction run's output must not make its
rules look superseded by a run nobody requested.
"""
from __future__ import annotations

from datetime import UTC, datetime

from policy_platform.api.routers.candidate_rules import _with_successors
from policy_platform.api.schemas import CandidateRuleResponse
from policy_platform.contracts.conditions import AllCondition
from tests.fixtures.factories import make_rule


def _candidate(candidate_id: str, *, baseline: str | None = None) -> CandidateRuleResponse:
    return CandidateRuleResponse(
        id=candidate_id,
        policy_set_id="set-1",
        extraction_run_id="run-1",
        rule_type="obligation",
        revision=1,
        review_status="published",
        reviewed_by=None,
        reviewed_at=None,
        review_notes=None,
        published_version_id="v1",
        created_at=datetime.now(UTC),
        baseline_candidate_id=baseline,
        rule=make_rule(f"AI-{candidate_id}", AllCondition(all=[])),
    )


def _successors(responses: list[CandidateRuleResponse]) -> dict[str, str | None]:
    return {r.id: r.superseded_by_candidate_id for r in _with_successors(responses)}


def test_the_record_that_replaced_another_is_named_on_it():
    older = _candidate("older")
    newer = _candidate("newer", baseline="older")

    successors = _successors([older, newer])

    assert successors["older"] == "newer"
    assert successors["newer"] is None


def test_a_record_nothing_points_at_is_the_latest():
    assert _successors([_candidate("only")]) == {"only": None}


def test_a_baseline_outside_the_set_leaves_the_record_latest():
    """Most baselines point at runs already retired from the queue.

    Thirty of forty-one did, in the corpus this was built against. Treating an
    unresolvable baseline as evidence of a successor would hide almost every
    record.
    """

    newer = _candidate("newer", baseline="a-run-not-in-this-view")

    assert _successors([newer]) == {"newer": None}


def test_a_chain_marks_only_the_middle_and_the_start():
    """Three readings of one sentence: only the last is current."""

    successors = _successors(
        [
            _candidate("first"),
            _candidate("second", baseline="first"),
            _candidate("third", baseline="second"),
        ]
    )

    assert successors == {"first": "second", "second": "third", "third": None}


def test_nothing_else_about_the_records_changes():
    """A derived field, added; everything the caller sent is returned intact."""

    older = _candidate("older")
    newer = _candidate("newer", baseline="older")

    returned = {r.id: r for r in _with_successors([older, newer])}

    assert returned["newer"].baseline_candidate_id == "older"
    assert returned["older"].rule.rule_id == older.rule.rule_id
    assert returned["older"].review_status == "published"
    # The stored flag is untouched: a published record is deliberately not
    # retired by a re-run, and this derivation does not change that.
    assert returned["older"].superseded_at is None
