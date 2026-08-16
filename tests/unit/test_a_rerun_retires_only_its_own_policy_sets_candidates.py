"""Re-extracting a document must retire only the candidates of the set it ran in.

A document can be extracted into more than one policy set — the same handbook
read once for HR and once for Legal, or a working copy alongside a live one.
Extraction run history, however, is a property of the *document*, and
`_supersede_prior_candidates` walks up to the owning `SourceDocument` on purpose
so that a re-uploaded variant still supersedes rules drawn from the original.

Those two facts together are a trap. Without a policy-set filter, extracting a
document into a second policy set marks the *first* set's live candidates as
superseded: a reviewer's queue emptied by a run they cannot see, launched in a
set they were not working in. Nothing is deleted and it is recoverable, but it
is silent, and a review queue that empties itself looks exactly like one that
was never filled.

This was found while measuring extraction stability, before it had happened to
anyone. The investigation deliberately called the extraction agents directly
rather than running the pipeline, precisely to keep a measurement run from
touching the working set — which is a fine precaution for a one-off and no
substitute for the query being right.
"""

from __future__ import annotations

import uuid

import pytest

from policy_platform.infrastructure.extraction.ai_extraction import _supersede_prior_candidates


class _Recorder:
    """Captures the WHERE clause of the supersession UPDATE without a database.

    Compiling the statement to SQL text and reading the literals back is the
    cheapest way to assert on a query that spans three tables. It is a
    structural check, so it is paired with an argument-level check below that
    would fail on a filter that was accepted and then ignored.
    """

    def __init__(self) -> None:
        self.statements: list = []

    async def flush(self) -> None:
        return None

    async def execute(self, statement):
        self.statements.append(statement)

        class _Result:
            rowcount = 0

            @staticmethod
            def scalars():
                class _S:
                    @staticmethod
                    def all():
                        return []

                return _S()

        return _Result()


@pytest.fixture
def document_version_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def policy_set_id() -> uuid.UUID:
    return uuid.uuid4()


async def _capture(monkeypatch, document_version_id, policy_set_id):
    prior = [uuid.uuid4()]
    monkeypatch.setattr(
        "policy_platform.infrastructure.extraction.ai_extraction._document_run_ids",
        lambda *args, **kwargs: _async(prior),
    )
    session = _Recorder()
    await _supersede_prior_candidates(
        session, document_version_id, policy_set_id, exclude_run_id=uuid.uuid4()
    )
    assert session.statements, "the supersession issued no statement at all"
    return session.statements[-1]


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_supersession_is_scoped_to_one_policy_set(
    monkeypatch, document_version_id, policy_set_id
) -> None:
    """The filter that stops one policy set retiring another's review queue."""

    statement = await _capture(monkeypatch, document_version_id, policy_set_id)
    rendered = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "policy_set_id" in rendered, (
        "the supersession UPDATE does not mention policy_set_id, so extracting this "
        f"document into any other policy set would retire the live candidates of every "
        f"set that shares it. Rendered SQL: {rendered}"
    )
    assert policy_set_id.hex in rendered.replace("-", ""), (
        "policy_set_id appears in the UPDATE but not the one this run belongs to, so the "
        f"filter is not doing what its name says. Rendered SQL: {rendered}"
    )


@pytest.mark.asyncio
async def test_supersession_still_retires_the_running_sets_own_candidates(
    monkeypatch, document_version_id, policy_set_id
) -> None:
    """The positive control: scoping must not have disabled supersession.

    A filter that matched nothing would pass the test above for the wrong
    reason and leave every prior generation live, which is the failure this
    function exists to prevent.
    """

    statement = await _capture(monkeypatch, document_version_id, policy_set_id)
    rendered = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "superseded_at" in rendered, (
        f"the UPDATE no longer sets superseded_at. Rendered SQL: {rendered}"
    )
    assert "review_status" in rendered, (
        "the UPDATE no longer restricts itself to rules still awaiting review, so it may "
        f"be retiring decisions a human already made. Rendered SQL: {rendered}"
    )


@pytest.mark.asyncio
async def test_the_policy_set_cannot_be_forgotten_at_the_call_site(
    document_version_id, policy_set_id
) -> None:
    """Passing the set must be mandatory, not merely available.

    An optional argument defaulting to "all sets" would reintroduce the bug for
    any caller that did not think about it, and the caller most likely not to
    think about it is the one written next.
    """

    with pytest.raises(TypeError):
        await _supersede_prior_candidates(
            _Recorder(), document_version_id, exclude_run_id=uuid.uuid4()
        )
