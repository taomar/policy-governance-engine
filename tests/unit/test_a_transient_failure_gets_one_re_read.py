"""A batch lost to a transient failure gets exactly one re-read; a judgement never does.

A run can lose a batch to something that has nothing to do with the batch: a
DNS blip, a momentary transport error, an endpoint that was briefly unreachable.
The client already retries such a call a few times over a sub-minute window and
then, correctly, declares a dead endpoint dead rather than hanging on it. When
the outage outlasts that window the batch is recorded as ``batch_unread`` and,
until now, abandoned for the rest of the run -- so recovering it meant
re-reading the whole document, every model call again, long after the blip was
over.

This exercises a single recovery pass over the unread batches at the end of a
run. Its correctness rests on one distinction that must never blur:

* ``batch_unread`` is an *infrastructure* fact -- the batch was never read. It is
  the only kind that may be re-read.
* ``not_extracted`` (and ``discarded``) are *judgements* -- the model read the
  content and decided something about it. Re-asking a judgement until it answers
  differently is rolling dice until you like the result, and it would quietly
  destroy the meaning of the skip ledger.

The four run states this produces read differently and are asserted separately
(constraint 5): never failed; failed and recovered; failed and still unread;
failed in a way that was not retryable.

Nothing here is driven by an observed count from any real run: every ledger is
built by the test, and every expectation is a relationship over what the test
put in, never a literal (constraint 1).
"""

from __future__ import annotations

import ast
from pathlib import Path

from policy_platform.infrastructure.extraction import ai_extraction
from policy_platform.infrastructure.extraction.ai_extraction import (
    _coverage_notes,
    _retry_unread_batches,
)
from policy_platform.infrastructure.extraction.formulation_mapping import (
    SKIP_BATCH_RECOVERED,
    SKIP_BATCH_UNREAD,
    SKIP_DISCARDED,
    SKIP_NOT_EXTRACTED,
    is_retryable_skip,
    mark_recovered,
    record_skip,
    skip_breaks_coverage,
)

_AI_EXTRACTION_SOURCE = Path(ai_extraction.__file__).read_text(encoding="utf-8")


def _unread_ledger(*identities: str) -> list[dict]:
    """A ledger holding one ``batch_unread`` entry per identity, as a run would."""

    ledger: list[dict] = []
    for identity in identities:
        record_skip(
            ledger,
            item=identity,
            reason=f"passage extractor was unreachable for {identity}",
            kind=SKIP_BATCH_UNREAD,
            identity=identity,
        )
    return ledger


def _still_unread(ledger: list[dict]) -> list[dict]:
    return [skip for skip in ledger if skip_breaks_coverage(skip)]


class TestOnlyInfrastructureSkipsAreRetryable:
    """``is_retryable_skip`` is strict exactly where ``skip_breaks_coverage`` is generous.

    For *coverage*, an untagged skip is treated as unread -- the safe default is
    to raise the alarm. For *re-invoking the model*, the safe default is the
    opposite: only a skip explicitly tagged as the batch-never-read kind may be
    retried, because anything else might be a judgement, and a judgement must
    never be re-asked. That asymmetry is the correctness guard, so it is checked
    from both sides.
    """

    def test_a_batch_unread_skip_is_retryable(self) -> None:
        assert is_retryable_skip({"kind": SKIP_BATCH_UNREAD, "identity": "batch:a"}) is True

    def test_a_judgement_skip_is_never_retryable(self) -> None:
        for kind in (SKIP_NOT_EXTRACTED, SKIP_DISCARDED):
            assert is_retryable_skip({"kind": kind, "identity": "clauses:a"}) is False, kind

    def test_an_untagged_skip_is_not_retryable(self) -> None:
        untagged = {"identity": "batch:a"}
        # The coverage default treats it as the alarming case ...
        assert skip_breaks_coverage(untagged) is True
        # ... but it must not therefore be re-sent to the model.
        assert is_retryable_skip(untagged) is False

    def test_an_already_recovered_skip_is_not_retryable_again(self) -> None:
        assert is_retryable_skip({"kind": SKIP_BATCH_RECOVERED, "identity": "batch:a"}) is False


class TestMarkRecovered:
    """Relabelling an unread entry to recovered, without deleting the evidence."""

    def test_it_relabels_the_unread_entry(self) -> None:
        ledger = _unread_ledger("batch:a")
        assert mark_recovered(ledger, identity="batch:a", note="read on a second attempt") is True
        (entry,) = ledger
        assert entry["kind"] == SKIP_BATCH_RECOVERED

    def test_it_keeps_the_original_reason_and_adds_the_note(self) -> None:
        ledger = _unread_ledger("batch:a")
        original_reason = ledger[0]["reason"]
        mark_recovered(ledger, identity="batch:a", note="read on a second attempt")
        reason = ledger[0]["reason"]
        # Constraint 11: a run that recovered from a transient failure is not the
        # same as one that never hit it, so the fact it needed a retry stays on
        # the record -- the original reason is not overwritten.
        assert original_reason in reason
        assert "read on a second attempt" in reason

    def test_a_recovered_entry_no_longer_breaks_coverage(self) -> None:
        ledger = _unread_ledger("batch:a")
        assert skip_breaks_coverage(ledger[0]) is True
        mark_recovered(ledger, identity="batch:a", note="re-read")
        assert skip_breaks_coverage(ledger[0]) is False

    def test_it_refuses_to_touch_a_judgement(self) -> None:
        ledger: list[dict] = []
        record_skip(
            ledger,
            item="clauses:a",
            reason="rule_type 'non_normative' carries no policy rule",
            kind=SKIP_NOT_EXTRACTED,
            identity="clauses:a",
        )
        assert mark_recovered(ledger, identity="clauses:a", note="re-read") is False
        assert ledger[0]["kind"] == SKIP_NOT_EXTRACTED

    def test_it_returns_false_when_the_identity_is_absent(self) -> None:
        assert mark_recovered([], identity="batch:missing", note="re-read") is False


class TestTheRetryPass:
    """One pass over the unread batches, driven through the real orchestrator.

    The orchestrator is handed a stubbed reader so the drafting path is not run
    for real (that costs model time over hundreds of pages). The stub stands in
    for the second attempt only; the first attempt is the failure that already
    put the batch in the ledger.
    """

    async def test_a_batch_read_on_the_retry_becomes_covered(self) -> None:
        ledger = _unread_ledger("batch:a")
        read: list[object] = []

        async def read_batch(item: object) -> bool:
            read.append(item)
            return True

        recovered = await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "payload-a"},
            read_batch=read_batch,
            recovery_note="re-read",
        )

        assert read == ["payload-a"]
        assert recovered == ["batch:a"]
        assert _still_unread(ledger) == []

    async def test_a_batch_that_fails_again_stays_unread(self) -> None:
        ledger = _unread_ledger("batch:a")
        read: list[object] = []

        async def read_batch(item: object) -> bool:
            read.append(item)
            return False

        recovered = await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "payload-a"},
            read_batch=read_batch,
            recovery_note="re-read",
        )

        assert recovered == []
        assert len(read) == 1  # one pass, not a loop
        assert _still_unread(ledger) == ledger

    async def test_the_retry_is_not_itself_retried(self) -> None:
        """A stub that would succeed on a *second* re-read must never be reached.

        The batch failed once (that is why it is in the ledger). This models a
        reader that fails the first re-read and would pass the next one: a single
        pass calls it once and leaves the batch unread, where a loop would reach
        the success and wrongly recover it.
        """

        ledger = _unread_ledger("batch:a")
        outcomes = [False, True]
        read: list[object] = []

        async def read_batch(item: object) -> bool:
            read.append(item)
            return outcomes.pop(0)

        recovered = await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "payload-a"},
            read_batch=read_batch,
            recovery_note="re-read",
        )

        assert recovered == []
        assert len(read) == 1
        assert _still_unread(ledger) == ledger

    async def test_a_judgement_is_never_re_read(self) -> None:
        """The guard this whole change exists to earn.

        A ``batch_unread`` and a ``not_extracted`` are both present, and *both*
        have a payload in the batch map -- so nothing but the retryable-kind
        filter stops the judgement being re-sent to the model. If the reader is
        ever called with the judgement's payload, a judgement was re-rolled.
        """

        ledger = _unread_ledger("batch:a")
        record_skip(
            ledger,
            item="clauses:j",
            reason="rule_type 'non_normative' carries no policy rule",
            kind=SKIP_NOT_EXTRACTED,
            identity="clauses:j",
        )
        read: list[object] = []

        async def read_batch(item: object) -> bool:
            read.append(item)
            return True

        await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "batch-payload", "clauses:j": "judgement-payload"},
            read_batch=read_batch,
            recovery_note="re-read",
        )

        assert "judgement-payload" not in read
        assert read == ["batch-payload"]
        judgement = next(skip for skip in ledger if skip["identity"] == "clauses:j")
        assert judgement["kind"] == SKIP_NOT_EXTRACTED

    async def test_a_raising_reader_neither_propagates_nor_recovers(self) -> None:
        """Requirement 6: the recovery attempt must not become a new failure mode.

        If the re-read raises, the run must still finish and report what it has,
        and the batch stays honestly unread.
        """

        ledger = _unread_ledger("batch:a")

        async def read_batch(item: object) -> bool:
            raise RuntimeError("network still down")

        recovered = await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "payload-a"},
            read_batch=read_batch,
            recovery_note="re-read",
        )

        assert recovered == []
        assert _still_unread(ledger) == ledger

    async def test_an_unread_batch_with_no_stashed_payload_is_left_alone(self) -> None:
        ledger = _unread_ledger("batch:a")
        read: list[object] = []

        async def read_batch(item: object) -> bool:
            read.append(item)
            return True

        recovered = await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={},  # nothing was stashed for this identity
            read_batch=read_batch,
            recovery_note="re-read",
        )

        assert recovered == []
        assert read == []
        assert _still_unread(ledger) == ledger


class TestTheRunSummaryReadsCorrectly:
    """The sentence a reviewer reads after each state, via the real note composer."""

    @staticmethod
    def _asks_for_a_repeat(notes: list[str]) -> bool:
        return any("should be repeated" in note for note in notes)

    def test_a_whole_run_says_nothing_extra(self) -> None:
        assert _coverage_notes([]) == []

    def test_an_unread_batch_asks_for_a_repeat(self) -> None:
        assert self._asks_for_a_repeat(_coverage_notes(_unread_ledger("batch:a")))

    def test_a_recovered_batch_does_not_ask_for_a_repeat(self) -> None:
        ledger = _unread_ledger("batch:a")
        mark_recovered(ledger, identity="batch:a", note="re-read")
        notes = _coverage_notes(ledger)
        assert not self._asks_for_a_repeat(notes)
        # The recovery is still reported: a summary that recovered a batch is not
        # allowed to look identical to one that never lost it (constraint 11).
        assert notes, "a recovered batch must still be reported, not silently dropped"

    def test_a_recovered_batch_is_not_reported_as_a_judgement(self) -> None:
        # A recovered batch WAS read and extracted, so it must not be described
        # with the 'read and not extracted' judgement wording.
        ledger = _unread_ledger("batch:a")
        mark_recovered(ledger, identity="batch:a", note="re-read")
        assert not any("not extracted" in note for note in _coverage_notes(ledger))

    def test_a_recovered_and_a_still_unread_batch_read_as_two_things(self) -> None:
        ledger = _unread_ledger("batch:a", "batch:b")
        mark_recovered(ledger, identity="batch:a", note="re-read")
        notes = _coverage_notes(ledger)
        # One batch is still unread, so a repeat is still asked for; the other
        # recovered, so its recovery is stated -- two distinct sentences.
        assert self._asks_for_a_repeat(notes)
        assert len(notes) >= 2

    async def test_a_transient_failure_recovered_reads_as_full_coverage(self) -> None:
        """First coverage case, end to end through the real helpers.

        A batch failed once (it is in the ledger unread); the recovery pass reads
        it on the second attempt; the summary the reviewer then reads no longer
        asks for a repeat -- but still reports that a recovery happened.
        """

        ledger = _unread_ledger("batch:a")

        async def read_batch(item: object) -> bool:
            return True

        await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "payload-a"},
            read_batch=read_batch,
            recovery_note="re-read",
        )
        notes = _coverage_notes(ledger)
        assert not self._asks_for_a_repeat(notes)
        assert notes, "the recovery must still be reported, not erased into a plain success"

    async def test_a_failure_that_recurs_keeps_asking_for_a_repeat(self) -> None:
        """Second coverage case, end to end: a batch unread on both attempts."""

        ledger = _unread_ledger("batch:a")

        async def read_batch(item: object) -> bool:
            return False

        await _retry_unread_batches(
            skipped=ledger,
            batch_by_identity={"batch:a": "payload-a"},
            read_batch=read_batch,
            recovery_note="re-read",
        )
        assert self._asks_for_a_repeat(_coverage_notes(ledger))


class TestTheForwardLoopFeedsTheRetry:
    """Structural guard that the run actually feeds the retry (this repo's §4.1).

    ``extract_candidate_rules`` cannot be unit-run without a database and live
    agents, so -- exactly as ``test_coverage_shortfall_is_visible`` does for the
    coverage ledger -- the wiring is asserted on the parsed source: the
    collection the retry consumes is the collection the batch loop fills when a
    batch goes unread, and the retry runs before the run's coverage verdict.
    """

    def _module(self) -> ast.Module:
        tree = ast.parse(_AI_EXTRACTION_SOURCE)
        # Detector-still-sees: an empty parse would pass every check below.
        assert any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.walk(tree)
        ), "parsed the extraction module but found no functions in it"
        return tree

    def _retry_call(self, tree: ast.Module) -> ast.Call | None:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_retry_unread_batches"
            ):
                return node
        return None

    def test_the_retry_pass_is_called(self) -> None:
        assert self._retry_call(self._module()) is not None, (
            "the run never calls _retry_unread_batches, so recovering a transient "
            "failure could not happen no matter how the helper behaves."
        )

    def test_the_retry_consumes_the_collection_the_batch_loop_fills(self) -> None:
        tree = self._module()
        call = self._retry_call(tree)
        assert call is not None
        feed = next(
            (kw.value for kw in call.keywords if kw.arg == "batch_by_identity"), None
        )
        assert isinstance(feed, ast.Name), "batch_by_identity must be passed a named collection"
        feed_name = feed.id

        filled_in_loop_under_if = False
        for loop in ast.walk(tree):
            if not isinstance(loop, ast.For):
                continue
            for branch in ast.walk(loop):
                if not isinstance(branch, ast.If):
                    continue
                for assign in ast.walk(branch):
                    if not isinstance(assign, ast.Assign):
                        continue
                    for target in assign.targets:
                        if (
                            isinstance(target, ast.Subscript)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == feed_name
                        ):
                            filled_in_loop_under_if = True
        assert filled_in_loop_under_if, (
            f"{feed_name!r} is passed to the retry but is never written inside the "
            "batch loop under the branch that sees a batch go unread, so the retry "
            "would be handed an empty collection."
        )

    def test_the_retry_runs_before_the_coverage_verdict(self) -> None:
        tree = self._module()
        retry = self._retry_call(tree)
        assert retry is not None
        completion = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "mark_completed"
                and any(kw.arg == "coverage_complete" for kw in node.keywords)
            ):
                completion = node
        assert completion is not None, "the run must still write a coverage verdict"
        assert retry.lineno < completion.lineno, (
            "the re-read has to run before coverage is judged, or a batch it "
            "recovers is still counted against coverage."
        )
