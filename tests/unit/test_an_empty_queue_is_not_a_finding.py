"""An empty queue is not a finding.

The quality report is read top-down, and every row costs a reader attention.
It was spending some of that on:

    [low] review_backlog — 0 candidate rule(s) awaiting human review

The row was appended unconditionally. The code that built it already knew there
was nothing to say — it withheld the recommendation when the queue was empty
and emitted the row anyway:

    "recommendation": "Review the pending candidates ..." if pending_candidates else ""

A finding reports something that needs attention. "Nothing needs attention" is
a statistic, and one the surrounding page already shows.

This is small, and it is here because the same habit at larger scale is what
made the ambiguity backlog a MEDIUM defect for 51 correct rules: a count is not
a defect, and a report that mixes the two teaches reviewers to skim.
"""

from __future__ import annotations

import inspect

from policy_platform.infrastructure.quality import ai_quality


def _quality_report_source() -> str:
    """The function that assembles the report, as source.

    Read as text rather than executed because the assembly sits inside an async
    database call: driving it needs a session, a policy set, an active version
    and a candidate repository, none of which this guarantee depends on. What is
    pinned is the shape — that the append is conditional — and that is visible
    here without standing a database up.
    """

    return inspect.getsource(ai_quality.evaluate_policy_set_quality)


def test_the_backlog_row_is_conditional() -> None:
    """It must be guarded, not appended and then explained away."""

    source = _quality_report_source()
    assert "if pending_candidates:" in source, (
        "the review_backlog finding is appended unconditionally, so an empty "
        "queue produces a row saying nothing"
    )


def test_the_recommendation_is_no_longer_conditional() -> None:
    """The tell that the old code knew, and the regression to catch.

    A recommendation that empties itself when the queue is empty is the shape of
    a row that should not have been emitted. If that ternary returns, the guard
    above has been removed or worked around.
    """

    source = _quality_report_source()
    assert 'if pending_candidates else ""' not in source, (
        "the recommendation is being blanked for an empty queue again, which "
        "means the row is being emitted for one"
    )


def test_the_backlog_row_still_exists_for_a_real_queue() -> None:
    """Anti-vacuity: the finding is suppressed when empty, not deleted."""

    source = _quality_report_source()
    assert '"category": "review_backlog"' in source
    assert "candidate rule(s) awaiting human review" in source
    assert "Review the pending candidates in the Review Queue." in source
