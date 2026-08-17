"""A batch recovered on the end-of-run retry leaves the live strip honest.

The recovery pass (see ``test_a_transient_failure_gets_one_re_read``) re-reads a
batch lost to a transient failure and turns it into rules. But the *live*
progress strip had counted that batch as skipped on the forward pass -- one
``advance(skipped=1)`` -- and until now that count was never undone. So a
finished strip would show the batch in its dropout box, labelled as not turned
into rules, while that very batch's rules sit in the review queue and the run
reports full coverage: a readout contradicting itself.

The correction moves a recovered batch out of the live ``skipped`` counter and
into a ``recovered`` counter, so the ephemeral count agrees with the durable
ledger (where ``mark_recovered`` already relabelled the entry) and a run that
recovered from a blip still reads differently from one that never hit it -- the
fourth of the four states this feature draws (constraint 5).

Every expectation here is a relationship over what the test itself put in -- the
size of a ledger it built, the batches its own stub chose to read back -- never a
count copied from a real run (constraint 1). The arithmetic runs through the
real recovery helper ``extract_candidate_rules`` calls, so a green is the run's
own recovery logic reaching the live counter, not integers proved to add (this
repo's §4.1); the wiring that the drafting site performs that same pair of steps
is pinned structurally below, as ``test_a_transient_failure_gets_one_re_read``
pins the pass itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

from policy_platform.infrastructure.extraction import ai_extraction, extraction_progress
from policy_platform.infrastructure.extraction.ai_extraction import _retry_unread_batches
from policy_platform.infrastructure.extraction.formulation_mapping import (
    SKIP_BATCH_UNREAD,
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


def _reader_reading(*readable: str):
    """A stub reader that reads back exactly the payloads named, and no others.

    Models the retry pass on a recovering network: some batches come back, the
    rest are still unreachable. What it returns is what the *real*
    ``_retry_unread_batches`` acts on, so the recovered set is the helper's
    decision, not a set the test asserts into existence.
    """

    async def read_batch(item: object) -> bool:
        return item in readable

    return read_batch


async def _forward_then_recover(
    key: str,
    ledger: list[dict],
    batch_by_identity: dict[str, object],
    reader,
) -> list[str]:
    """Replay the run's own sequence: forward-pass skips, then one recovery pass.

    On the forward pass each unread batch records a durable skip *and* one
    ``advance(skipped=1)`` on the live strip -- modelled here by advancing once
    per entry the ledger already holds. Then the run's real recovery helper runs,
    and the site's correction is applied exactly as ``extract_candidate_rules``
    applies it: the number recovered is moved out of the live ``skipped`` counter.
    Returns the recovered identities the helper produced.
    """

    for _entry in ledger:
        extraction_progress.advance(key, skipped=1)

    recovered = await _retry_unread_batches(
        skipped=ledger,
        batch_by_identity=batch_by_identity,
        read_batch=reader,
        recovery_note="re-read",
    )
    if recovered:
        extraction_progress.recover(key, count=len(recovered))
    return recovered


def teardown_function() -> None:
    extraction_progress.clear()


class TestTheLiveSkippedCountFollowsTheLedgerThroughRecovery:
    async def test_before_recovery_the_forward_pass_counts_every_unread_batch(self) -> None:
        """Baseline: the state the correction acts on.

        After the forward pass the live strip counts every unread batch as
        skipped, matching the ledger exactly. It is the *recovery* that would
        then make the two disagree unless the count is corrected -- which the
        next test checks. Nothing is recovered here.
        """

        key = "doc-forward"
        extraction_progress.start(key, total_clauses=10, total_batches=2, total_pages=2)
        ledger = _unread_ledger("batch:a", "batch:b")
        for _entry in ledger:
            extraction_progress.advance(key, skipped=1)

        record = extraction_progress.get(key)
        assert record is not None
        assert record["skipped"] == len(_still_unread(ledger)) == len(ledger)
        assert record["recovered"] == 0

    async def test_a_recovered_batch_leaves_the_live_count_matching_the_ledger(self) -> None:
        key = "doc-recover"
        extraction_progress.start(key, total_clauses=10, total_batches=3, total_pages=3)
        ledger = _unread_ledger("batch:a", "batch:b", "batch:c")

        recovered = await _forward_then_recover(
            key,
            ledger,
            {"batch:a": "payload-a", "batch:b": "payload-b", "batch:c": "payload-c"},
            _reader_reading("payload-a"),  # only a's endpoint has come back
        )

        record = extraction_progress.get(key)
        assert record is not None
        # The real recovery helper decided which batch came back; the test did not.
        assert recovered == ["batch:a"]
        # The live skipped count now equals the durable ledger's remaining skips:
        # the recovered batch is in neither. This is the whole point -- the strip
        # agrees with the ledger rather than over-counting a batch that was read.
        assert record["skipped"] == len(_still_unread(ledger))
        # And the recovery is visible, not erased: exactly the batches recovered.
        assert record["recovered"] == len(recovered)
        # The two together still account for every batch the forward pass skipped,
        # so nothing was lost in the move. A relationship over the built ledger,
        # never a written-in count.
        assert record["skipped"] + record["recovered"] == len(ledger)

    async def test_every_batch_recovering_empties_the_dropout_box(self) -> None:
        """When the network is fully back, no batch is left in the skipped box."""

        key = "doc-all-back"
        extraction_progress.start(key, total_clauses=10, total_batches=2, total_pages=2)
        ledger = _unread_ledger("batch:a", "batch:b")

        recovered = await _forward_then_recover(
            key,
            ledger,
            {"batch:a": "payload-a", "batch:b": "payload-b"},
            _reader_reading("payload-a", "payload-b"),
        )

        record = extraction_progress.get(key)
        assert len(recovered) == len(ledger)
        assert _still_unread(ledger) == []
        assert record["skipped"] == len(_still_unread(ledger)) == 0
        assert record["recovered"] == len(ledger)

    async def test_a_batch_that_fails_its_re_read_stays_counted_as_skipped(self) -> None:
        """The correction fires only on a recovery, not merely on running the pass."""

        key = "doc-still-unread"
        extraction_progress.start(key, total_clauses=10, total_batches=1, total_pages=1)
        ledger = _unread_ledger("batch:a")

        recovered = await _forward_then_recover(
            key,
            ledger,
            {"batch:a": "payload-a"},
            _reader_reading(),  # nothing comes back
        )

        record = extraction_progress.get(key)
        assert recovered == []
        # No recovery, so nothing moves: still skipped on the strip and still
        # unread in the ledger, and the honest "should be repeated" stands.
        assert record["skipped"] == len(_still_unread(ledger)) == len(ledger)
        assert record["recovered"] == 0


class TestARecoveredRunReadsDifferentlyFromOneThatNeverFailed:
    async def test_recovered_is_a_distinct_state_not_collapsed_into_never_skipped(self) -> None:
        """Constraint 5: failed-and-recovered must not read as never-failed.

        Once the count is corrected, a batch that failed transiently and came
        back ends with the same live ``skipped`` as a batch that never failed:
        zero. If ``skipped`` were the only signal, the two runs would be
        indistinguishable on the strip. ``recovered`` is what keeps them apart.
        """

        clean = "doc-clean"
        extraction_progress.start(clean, total_clauses=10, total_batches=1, total_pages=1)
        clean_record = extraction_progress.get(clean)

        recovered_key = "doc-recovered"
        extraction_progress.start(
            recovered_key, total_clauses=10, total_batches=1, total_pages=1
        )
        ledger = _unread_ledger("batch:a")
        await _forward_then_recover(
            recovered_key, ledger, {"batch:a": "payload-a"}, _reader_reading("payload-a")
        )
        recovered_record = extraction_progress.get(recovered_key)

        # Same skipped count on both -- recovery brought it back down to the clean
        # run's value...
        assert recovered_record["skipped"] == clean_record["skipped"]
        # ...so skipped alone cannot tell the two runs apart. recovered can: the
        # run that hit a blip and got past it does not read as one that never did.
        assert recovered_record["recovered"] > clean_record["recovered"]
        assert clean_record["recovered"] == 0


class TestRecoverIsTotalLikeTheRestOfTheModule:
    def test_recover_ignores_an_unknown_run(self) -> None:
        # No run started under this key. A reporting call must never raise or
        # invent a record -- this module's invariant that progress cannot fail a
        # run. Mirrors ``test_advance_ignores_unknown_run``.
        extraction_progress.recover("never-started", count=3)
        assert extraction_progress.get("never-started") is None


class TestTheRecoveryPassCorrectsTheLiveCount:
    """Structural guard (§4.1): the site moves the recovered count off the strip.

    ``extract_candidate_rules`` cannot be unit-run without a database and live
    agents, so -- as ``test_a_transient_failure_gets_one_re_read`` does for the
    pass itself -- the wiring is asserted on the parsed source: the recovery
    helper's result is captured, and the live counter is corrected by exactly the
    number of batches it recovered, so a regression that drops the correction or
    hard-codes it fails here rather than only in a live run.
    """

    def _module(self) -> ast.Module:
        tree = ast.parse(_AI_EXTRACTION_SOURCE)
        # Detector-still-sees: an empty parse would pass every check below.
        assert any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.walk(tree)
        ), "parsed the extraction module but found no functions in it"
        return tree

    def _retry_result_name(self, tree: ast.Module) -> str:
        """The name the run binds ``_retry_unread_batches``'s result to."""

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            if not isinstance(node.targets[0], ast.Name):
                continue
            value = node.value
            if isinstance(value, ast.Await):  # the call is awaited
                value = value.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "_retry_unread_batches"
            ):
                return node.targets[0].id
        raise AssertionError(
            "the run does not capture _retry_unread_batches' result, so it cannot "
            "know how many batches recovered and the live count cannot be corrected."
        )

    def _recover_call(self, tree: ast.Module) -> ast.Call:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "recover"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "extraction_progress"
            ):
                return node
        raise AssertionError(
            "nothing calls extraction_progress.recover(...), so a recovered batch "
            "stays counted as skipped on the live strip."
        )

    def test_the_run_captures_the_recovered_batches(self) -> None:
        self._retry_result_name(self._module())

    def test_the_live_count_is_corrected_by_the_number_recovered(self) -> None:
        tree = self._module()
        result_name = self._retry_result_name(tree)
        call = self._recover_call(tree)
        count = next((kw.value for kw in call.keywords if kw.arg == "count"), None)
        assert (
            isinstance(count, ast.Call)
            and isinstance(count.func, ast.Name)
            and count.func.id == "len"
            and len(count.args) == 1
            and isinstance(count.args[0], ast.Name)
            and count.args[0].id == result_name
        ), (
            "the recovery correction is not len(<the recovered batches>); it is fed "
            "by something other than what the retry pass recovered, so it could "
            "over- or under-correct the live skipped count."
        )

    def test_the_correction_runs_after_the_retry(self) -> None:
        tree = self._module()
        retry = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_retry_unread_batches"
        )
        recover = self._recover_call(tree)
        assert retry.lineno < recover.lineno, (
            "the correction must run after the retry that produced the count it "
            "moves; before it, there is nothing recovered to move."
        )
