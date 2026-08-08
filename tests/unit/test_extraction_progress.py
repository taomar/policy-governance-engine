"""Tests for the in-flight extraction progress registry.

The registry's contract is that it is *total* — a reporting mistake must never
be able to fail an extraction run — so most of these tests assert that bad or
out-of-order calls are silently absorbed rather than raising.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure import extraction_progress


@pytest.fixture(autouse=True)
def _clean_registry():
    extraction_progress.clear()
    yield
    extraction_progress.clear()


def test_unknown_document_returns_none():
    assert extraction_progress.get("does-not-exist") is None


def test_start_publishes_totals():
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    record = extraction_progress.get("doc-1")
    assert record is not None
    assert record["status"] == "running"
    assert record["total_clauses"] == 50
    assert record["total_batches"] == 7
    assert record["total_pages"] == 12
    assert record["processed_clauses"] == 0
    assert record["rules_drafted"] == 0


def test_advance_accumulates_counters():
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    extraction_progress.advance("doc-1", clauses=8, pages=3, drafted=2, skipped=1)
    extraction_progress.advance("doc-1", clauses=9, pages=5, drafted=3)
    record = extraction_progress.get("doc-1")
    assert record["processed_clauses"] == 17
    assert record["rules_drafted"] == 5
    assert record["skipped"] == 1


def test_processed_pages_never_goes_backwards():
    """Pages are a high-water mark, not a sum: a later batch can revisit an
    earlier page (clauses straddle boundaries) and the count must not regress."""
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    extraction_progress.advance("doc-1", pages=6)
    extraction_progress.advance("doc-1", pages=4)
    assert extraction_progress.get("doc-1")["processed_pages"] == 6


def test_update_replaces_stage_rather_than_appending():
    extraction_progress.start("doc-1", total_clauses=10, total_batches=2, total_pages=1)
    extraction_progress.update("doc-1", stage="Reading batch 1 of 2")
    extraction_progress.update("doc-1", stage="Reading batch 2 of 2")
    assert extraction_progress.get("doc-1")["stage"] == "Reading batch 2 of 2"


def test_update_ignores_unknown_run_and_unknown_field():
    """Total by contract: neither call may raise."""
    extraction_progress.update("nope", stage="x")
    extraction_progress.start("doc-1", total_clauses=1, total_batches=1, total_pages=1)
    extraction_progress.update("doc-1", not_a_field="x")
    assert not hasattr(extraction_progress.get("doc-1"), "not_a_field")


def test_advance_ignores_unknown_run():
    extraction_progress.advance("nope", clauses=5)


def test_finish_records_terminal_state_and_keeps_record():
    extraction_progress.start("doc-1", total_clauses=10, total_batches=2, total_pages=1)
    extraction_progress.finish("doc-1", status="completed", stage="Done — 4 rules")
    record = extraction_progress.get("doc-1")
    assert record["status"] == "completed"
    assert record["stage"] == "Done — 4 rules"
    assert record["error"] is None


def test_finish_records_failure_reason():
    extraction_progress.start("doc-1", total_clauses=10, total_batches=2, total_pages=1)
    extraction_progress.finish("doc-1", status="failed", stage="Extraction failed", error="boom")
    record = extraction_progress.get("doc-1")
    assert record["status"] == "failed"
    assert record["error"] == "boom"


def test_restart_resets_counters():
    """Re-running extraction on the same document must not show the prior run's
    totals, which would make a fresh run look instantly half-complete."""
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    extraction_progress.advance("doc-1", clauses=40, drafted=9)
    extraction_progress.start("doc-1", total_clauses=20, total_batches=3, total_pages=5)
    record = extraction_progress.get("doc-1")
    assert record["processed_clauses"] == 0
    assert record["rules_drafted"] == 0
    assert record["total_clauses"] == 20


def test_runs_are_isolated_per_document():
    extraction_progress.start("doc-1", total_clauses=10, total_batches=1, total_pages=1)
    extraction_progress.start("doc-2", total_clauses=20, total_batches=2, total_pages=2)
    extraction_progress.advance("doc-1", drafted=3)
    assert extraction_progress.get("doc-1")["rules_drafted"] == 3
    assert extraction_progress.get("doc-2")["rules_drafted"] == 0


def test_elapsed_seconds_is_exposed():
    extraction_progress.start("doc-1", total_clauses=1, total_batches=1, total_pages=1)
    assert extraction_progress.get("doc-1")["elapsed_seconds"] >= 0


def test_committed_starts_at_zero_and_is_separate_from_drafted():
    # The review-queue stage of the progress readout must never borrow the
    # drafted count: a rule the formulator produced is not a rule a reviewer can
    # open until its insert has committed.
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    extraction_progress.advance("doc-1", drafted=5)
    record = extraction_progress.get("doc-1")
    assert record["rules_drafted"] == 5
    assert record["rules_committed"] == 0


def test_committed_is_set_absolutely_not_accumulated():
    # The loop publishes len(created_ids), which is already cumulative. Treating
    # it as an increment would double-count every batch after the first.
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    extraction_progress.update("doc-1", rules_committed=4)
    extraction_progress.update("doc-1", rules_committed=9)
    assert extraction_progress.get("doc-1")["rules_committed"] == 9


def test_committed_resets_when_a_run_restarts():
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    extraction_progress.update("doc-1", rules_committed=9)
    extraction_progress.start("doc-1", total_clauses=50, total_batches=7, total_pages=12)
    assert extraction_progress.get("doc-1")["rules_committed"] == 0
