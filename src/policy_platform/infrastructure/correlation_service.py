"""Orchestration for cross-rule correlation analysis.

The agent in `correlation_agent` analyses one small group of rules. This module
is what turns that into an analysis of a whole policy set: it selects the rules,
groups them, drives the calls, suppresses duplicates across overlapping groups,
and persists the result as a run.

Why a run and not a live query: a finding is a statement about the rules as they
stood at a moment. Rules get rewritten during review, so a finding stored without
a run would silently become a claim about text that no longer exists. Keeping
runs also lets a reviewer see whether a contradiction they fixed stayed fixed.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.correlation import (
    ACTIONABLE_CLASSIFICATIONS,
    CorrelationFinding,
)
from policy_platform.domain.models import (
    CandidateRule,
    CorrelationFindingRow,
    CorrelationRun,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.correlation_agent import (
    CORRELATION_PROMPT_VERSION,
    CorrelationAgent,
    CorrelationError,
    finding_key,
    group_rules_for_comparison,
    groupable_rule_ids,
)
from policy_platform.infrastructure.repositories import PolicySetRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Groups analysed at once. Each is a separate model call; a handful in flight
#: keeps a large policy set tractable without tripping rate limits. Concurrency
#: does not affect the result — findings are deduplicated by identity, not by
#: arrival order — so this is purely a throughput knob.
GROUP_CONCURRENCY = 3

#: Review states whose rules take part in correlation.
#:
#: Rejected rules are excluded because a contradiction with a rule someone
#: already threw out is noise, and surfacing it trains reviewers to skim the
#: findings list.
#:
#: Published rules are deliberately *included*. A contradiction does not
#: dissolve at publish — it goes live and starts being enforced, which makes it
#: the most consequential kind there is. Restricting analysis to pre-approval
#: candidates would leave the tool blind precisely where a compliance team most
#: needs it, and would mean a policy set that has been fully published can never
#: be analysed at all.
ANALYZABLE_STATUSES = ("candidate", "approved", "needs_changes", "published")


async def _load_rules(
    session: AsyncSession, policy_set_id: uuid.UUID, *, statuses: tuple[str, ...]
) -> list[tuple[str, dict]]:
    """Latest revision of each rule in the set, as `(rule_id, payload)`."""

    result = await session.execute(
        select(CandidateRule)
        .where(
            CandidateRule.policy_set_id == policy_set_id,
            CandidateRule.review_status.in_(statuses),
        )
        .order_by(CandidateRule.revision)
    )
    rows = list(result.scalars())

    # A rule can exist at several revisions. Comparing revision 1 against
    # revision 3 of the same rule would report the author's own edit as a
    # contradiction, so only the newest revision of each rule_id survives.
    latest: dict[str, dict] = {}
    for row in rows:
        payload = row.payload_json or {}
        rule_id = str(payload.get("rule_id") or row.id)
        latest[rule_id] = payload

    return sorted(latest.items())


def _persist_finding(
    run: CorrelationRun, policy_set_id: uuid.UUID, finding: CorrelationFinding
) -> CorrelationFindingRow:
    return CorrelationFindingRow(
        run_id=run.id,
        policy_set_id=policy_set_id,
        classification=finding.classification,
        analysis_status=finding.analysis_status,
        severity=finding.severity,
        rule_ids=list(finding.rule_ids),
        reason=finding.reason or "",
        payload_json=finding.model_dump(mode="json"),
    )


async def run_correlation_analysis(
    session: AsyncSession,
    *,
    policy_set_key: str,
    actionable_only: bool = True,
    max_groups: int | None = None,
) -> dict:
    """Analyse a policy set for contradictions and related relationships.

    `actionable_only` drops classifications the specification marks as
    non-actionable (`consistent`, `unrelated`, …). They are worth returning from
    the agent — they are evidence the pair was genuinely examined — but storing
    thousands of "these two rules are fine" rows would bury the findings that
    need a decision.

    Raises ValueError for an unknown policy set; RuntimeError when AI is not
    configured.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    policy_set = await PolicySetRepository(session).get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    rules = await _load_rules(session, policy_set.id, statuses=ANALYZABLE_STATUSES)
    if len(rules) < 2:
        raise ValueError(
            f"policy set '{policy_set_key}' has {len(rules)} analysable rule(s); "
            "correlation needs at least two"
        )

    # The cap is passed down rather than applied by slicing here: the grouping
    # function orders groups most-specific-first, so letting it enforce the
    # budget keeps the narrowest, highest-value comparisons. Slicing an
    # already-built list would work too, but only by accident of that ordering.
    groups = group_rules_for_comparison(
        rules,
        **({"max_groups": max_groups} if max_groups is not None else {}),
    )

    grouped_ids = {rule_id for group in groups for rule_id, _ in group}
    uncompared = len(rules) - len(grouped_ids)
    # Split the uncompared total by cause. A rule that shares no signal with any
    # other rule was never comparable and is nothing to act on; a rule that was
    # comparable but fell outside the group budget means this run is truncated.
    # Reporting only the total lets a reviewer read a budget-limited run as a
    # clean one, which is the more dangerous of the two misreadings.
    budget_skipped = len(groupable_rule_ids(rules) - grouped_ids)

    run = CorrelationRun(
        policy_set_id=policy_set.id,
        status="running",
        deployment_name=settings.azure_openai_deployment,
        prompt_version=CORRELATION_PROMPT_VERSION,
        rules_analyzed=len(rules),
        groups_analyzed=len(groups),
        rules_uncompared=uncompared,
        rules_budget_skipped=budget_skipped,
    )
    session.add(run)
    await session.flush()

    logger.info(
        "correlation: set=%s rules=%d groups=%d uncompared=%d (budget_skipped=%d)",
        policy_set_key,
        len(rules),
        len(groups),
        uncompared,
        budget_skipped,
    )

    agent = CorrelationAgent(AzureOpenAIClient(settings), settings)
    semaphore = asyncio.Semaphore(GROUP_CONCURRENCY)

    async def analyze(index: int, group: list[tuple[str, dict]]) -> list[CorrelationFinding]:
        async with semaphore:
            try:
                findings, _ = await agent.analyze_group(group)
                logger.info(
                    "correlation: group %d/%d (%d rules) -> %d findings",
                    index + 1,
                    len(groups),
                    len(group),
                    len(findings),
                )
                return findings
            except (CorrelationError, Exception) as exc:  # noqa: BLE001
                # One failed group must not lose the other groups' findings. A
                # partial analysis that says so is more useful than no analysis.
                logger.warning("correlation: group %d failed: %s", index + 1, exc)
                return []

    results = await asyncio.gather(*(analyze(i, g) for i, g in enumerate(groups)))

    seen: set[tuple] = set()
    stored = 0
    suppressed = 0
    by_classification: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    # Every classification the agent returned, including the benign ones that
    # `actionable_only` drops. Without this a run that examined a hundred pairs
    # and judged them all consistent is indistinguishable from a run where the
    # agent returned nothing at all, and the operator has no way to tell a
    # clean policy set from a broken analysis.
    examined_by_classification: dict[str, int] = {}
    non_actionable = 0

    for findings in results:
        for finding in findings:
            examined_by_classification[finding.classification] = (
                examined_by_classification.get(finding.classification, 0) + 1
            )
            if actionable_only and finding.classification not in ACTIONABLE_CLASSIFICATIONS:
                non_actionable += 1
                continue
            key = finding_key(finding)
            if key in seen:
                suppressed += 1
                continue
            seen.add(key)
            session.add(_persist_finding(run, policy_set.id, finding))
            stored += 1
            by_classification[finding.classification] = by_classification.get(finding.classification, 0) + 1
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    await session.commit()

    logger.info(
        "correlation: set=%s examined=%d stored=%d non_actionable=%d census=%s",
        policy_set_key,
        sum(examined_by_classification.values()),
        stored,
        non_actionable,
        examined_by_classification,
    )

    return {
        "correlation_run_id": str(run.id),
        "policy_set_key": policy_set_key,
        "rules_analyzed": len(rules),
        "groups_analyzed": len(groups),
        "rules_uncompared": uncompared,
        "rules_budget_skipped": budget_skipped,
        "findings_stored": stored,
        "duplicates_suppressed": suppressed,
        "findings_examined": sum(examined_by_classification.values()),
        "non_actionable_suppressed": non_actionable,
        "examined_by_classification": examined_by_classification,
        "by_classification": by_classification,
        "by_severity": by_severity,
    }
