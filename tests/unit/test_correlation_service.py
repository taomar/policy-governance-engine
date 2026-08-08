"""Tests for how a correlation run is driven and persisted.

The agent's judgement is tested in `test_correlation_agent`. What is under test
here is the orchestration around it, and specifically its durability: a run over
the statutory sets is seventeen hundred model calls and better than two hours,
so the question "what survives if this stops halfway" is a correctness question,
not an operational nicety.

Grouping, rule loading and the agent itself are stubbed out. They have their own
tests, and leaving them in would make these tests fail for reasons that have
nothing to do with the chunking and commit boundaries being pinned here.
"""

from __future__ import annotations

import uuid

import pytest

from policy_platform.contracts.correlation import CorrelationFinding
from policy_platform.infrastructure import correlation_service


class _FakeSession:
    """Records what was staged, and what had been staged at each commit.

    `commits` is the point of the class: it captures a snapshot of how many
    findings were durable at each commit boundary, which is exactly the property
    that distinguishes "written progressively" from "written once at the end".
    """

    def __init__(self) -> None:
        self.added: list = []
        self.commits: list[int] = []
        self.rollbacks = 0
        self.executed: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits.append(len(self.added))

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def execute(self, statement):
        self.executed.append(statement)
        return None


class _FakePolicySet:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.key = "test-set"


def _finding(
    classification: str = "DIRECT_CONTRADICTION",
    reason: str = "",
    rule_ids: tuple[str, str] = ("R-1", "R-2"),
) -> CorrelationFinding:
    return CorrelationFinding(
        classification=classification,
        severity="high",
        rule_ids=list(rule_ids),
        reason=reason,
    )


@pytest.fixture
def wired(monkeypatch):
    """Stub everything around the drive-and-persist loop.

    Returns a callable that installs a given set of groups and a given
    per-group agent behaviour, so each test states only what it varies.
    """

    policy_set = _FakePolicySet()

    class _Settings:
        ai_enabled = True
        azure_openai_deployment = "test-deployment"

    monkeypatch.setattr(correlation_service, "get_settings", lambda: _Settings())

    class _Repo:
        def __init__(self, session) -> None:
            self._session = session

        async def get_by_key(self, key):
            return policy_set

    monkeypatch.setattr(correlation_service, "PolicySetRepository", _Repo)
    monkeypatch.setattr(correlation_service, "AzureOpenAIClient", lambda settings: object())

    def install(groups, analyze):
        rules = [(f"R-{i}", {"rule_id": f"R-{i}"}) for i in range(max(2, len(groups)))]

        async def _load_rules(session, policy_set_id, *, statuses):
            return rules

        monkeypatch.setattr(correlation_service, "_load_rules", _load_rules)
        monkeypatch.setattr(
            correlation_service,
            "group_rules_for_comparison",
            lambda r, **kwargs: list(groups),
        )
        monkeypatch.setattr(
            correlation_service, "groupable_rule_ids", lambda r: {rid for rid, _ in r}
        )

        calls: list[int] = []

        class _Agent:
            def __init__(self, client, settings) -> None:
                pass

            async def analyze_group(self, group):
                index = int(group[0][0].split("-")[1])
                calls.append(index)
                return analyze(index), None

        monkeypatch.setattr(correlation_service, "CorrelationAgent", _Agent)
        return calls

    return install


def _groups(count: int) -> list[list[tuple[str, dict]]]:
    """`count` two-rule groups, each tagged with its own index."""

    return [[(f"G-{i}", {"rule_id": f"G-{i}"}), ("R-x", {"rule_id": "R-x"})] for i in range(count)]


@pytest.mark.asyncio
async def test_the_run_row_is_committed_before_any_analysis_begins(wired) -> None:
    """A run in progress must be observable, not merely declared.

    `status="running"` was previously flushed but not committed until the run
    finished, so no other connection could ever see it: a two-hour job left the
    database looking idle. The first commit must therefore land before the first
    model call.
    """

    session = _FakeSession()
    order: list[str] = []

    original_commit = session.commit

    async def tracking_commit() -> None:
        order.append("commit")
        await original_commit()

    session.commit = tracking_commit  # type: ignore[method-assign]

    def analyze(index):
        order.append(f"analyze-{index}")
        return []

    wired(_groups(2), analyze)

    await correlation_service.run_correlation_analysis(session, policy_set_key="test-set")

    assert order[0] == "commit", f"analysis ran before the run row was durable: {order}"


@pytest.mark.asyncio
async def test_every_group_is_analysed_exactly_once_across_chunk_boundaries(
    wired, monkeypatch
) -> None:
    """The chunk arithmetic must not skip or repeat a group.

    Driving in chunks introduces an offset calculation that did not exist when
    every group was gathered at once; a slip there would silently drop groups
    from a run that still reports itself complete.
    """

    monkeypatch.setattr(correlation_service, "PERSIST_CHUNK_GROUPS", 7)
    session = _FakeSession()
    calls = wired(_groups(23), lambda index: [])

    result = await correlation_service.run_correlation_analysis(
        session, policy_set_key="test-set"
    )

    assert sorted(calls) == list(range(23))
    assert result["groups_analyzed"] == 23


@pytest.mark.asyncio
async def test_findings_are_durable_before_the_run_finishes(wired, monkeypatch) -> None:
    """Findings must reach the database as the run proceeds.

    Held in memory to the end, a failure at group 1,700 of 1,763 discarded every
    finding the run had produced. The observable form of the fix is that the
    count of staged rows grows across successive commits rather than jumping
    from zero to everything at the last one.
    """

    monkeypatch.setattr(correlation_service, "PERSIST_CHUNK_GROUPS", 5)
    session = _FakeSession()
    wired(
        _groups(20),
        lambda index: [_finding(reason=f"group {index}", rule_ids=(f"R-{index}a", f"R-{index}b"))],
    )

    await correlation_service.run_correlation_analysis(session, policy_set_key="test-set")

    # First commit is the run row alone; the rest each carry that chunk's work.
    assert session.commits[0] == 1
    growth = [b - a for a, b in zip(session.commits, session.commits[1:], strict=False)]
    assert sum(1 for step in growth if step > 0) >= 4, (
        f"findings did not accumulate progressively: {session.commits}"
    )


@pytest.mark.asyncio
async def test_a_failure_keeps_the_findings_already_committed(wired, monkeypatch) -> None:
    """Work completed before a failure must survive it.

    This is the whole point of the chunking. The run is additionally marked
    failed, so a reviewer sees a run that stopped rather than a run that never
    existed.
    """

    monkeypatch.setattr(correlation_service, "PERSIST_CHUNK_GROUPS", 4)
    session = _FakeSession()

    def analyze(index):
        if index >= 8:
            raise RuntimeError("connection lost")
        return [_finding(reason=f"group {index}", rule_ids=(f"R-{index}a", f"R-{index}b"))]

    # The per-group guard swallows agent errors, so fail at the commit instead —
    # the class of failure the chunking exists to survive.
    real_commit = session.commit
    state = {"chunks": 0}

    async def failing_commit() -> None:
        state["chunks"] += 1
        if state["chunks"] == 4:
            raise RuntimeError("connection lost")
        await real_commit()

    session.commit = failing_commit  # type: ignore[method-assign]
    wired(_groups(16), analyze)

    with pytest.raises(RuntimeError):
        await correlation_service.run_correlation_analysis(session, policy_set_key="test-set")

    assert session.commits[-1] > 1, "no findings were durable when the run failed"
    assert session.rollbacks == 1
    assert session.executed, "the run was not marked failed"


@pytest.mark.asyncio
async def test_duplicate_findings_are_suppressed_across_chunks(wired, monkeypatch) -> None:
    """Deduplication is by identity over the whole run, not within a chunk.

    Groups overlap by design, so the same contradiction is reached more than
    once. Committing in chunks must not let the second sighting through simply
    because the first was already written.
    """

    monkeypatch.setattr(correlation_service, "PERSIST_CHUNK_GROUPS", 2)
    session = _FakeSession()
    wired(_groups(8), lambda index: [_finding(reason="the same finding every time")])

    result = await correlation_service.run_correlation_analysis(
        session, policy_set_key="test-set"
    )

    assert result["findings_stored"] == 1
    assert result["duplicates_suppressed"] == 7
