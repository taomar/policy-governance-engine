"""Explaining *why* a candidate rule was classified as changed.

`rule_delta` decides that a rule this run produced continues one the previous
run produced, but its semantics differ. That verdict is only half the answer.
A reviewer facing a `Changed` badge still has to work out what actually moved
and whether it matters — and before this module the only way to do that was to
find the superseded predecessor by hand and read two payloads side by side.

The split of responsibility here is the same one `ai_compare` already uses for
approved versions, and for the same reason: **the diff is computed
deterministically from the two persisted payloads and is never asked of the
language model.** The model is given the already-correct diff and asked only to
say what it means in practice. If it is unavailable, misconfigured, or fails,
the reviewer still gets the exact field-level diff — the narrative is an aid to
reading it, never the source of it.

The diff separates two things a reviewer weighs differently:

- **semantic changes** — the fields the evaluator actually executes
  (`rule_delta.SEMANTIC_FIELDS`). These change what the policy *does*.
- **wording changes** — title and description. The model rewords freely between
  runs, so these are reported but explicitly marked as not affecting behaviour.
  Presenting them in the same list as a changed threshold would be misleading.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, ExtractionRun
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.projection.rule_delta import SEMANTIC_FIELDS
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Presentational fields. Reported, but never counted as a behavioural change.
PROSE_FIELDS = ("title", "description")

_EXPLAIN_SYSTEM_PROMPT = """You help a policy reviewer understand what changed \
between two extractions of the same policy rule from a source document.

You are given a deterministic JSON diff with two sections:
- "semantic_changes": fields that change what the rule actually does when evaluated.
- "wording_changes": title/description rewording that does NOT change behaviour.

Write a short plain-English explanation (2-5 sentences) covering:
1. what materially changed in the rule's behaviour, if anything;
2. who or what it now affects differently;
3. what the reviewer should check before approving it.

Rules:
- Do not invent any change that is not in the diff.
- If "semantic_changes" is empty, say plainly that only the wording changed and \
the rule's behaviour is unaffected.
- Do not restate the JSON field by field; explain the practical consequence.
- Do not tell the reviewer whether to approve. That decision is theirs."""


def _diff_fields(before: dict, after: dict, fields: tuple[str, ...]) -> list[dict]:
    """Field-level diff over an explicit field list, in a stable order.

    Ordered by `fields` rather than by dict iteration so that the same pair of
    payloads always produces the same diff — a reviewer comparing two rules
    should not see the reasons reshuffle between page loads.
    """
    out: list[dict] = []
    for name in fields:
        old, new = before.get(name), after.get(name)
        if old != new:
            out.append({"field": name, "before": old, "after": new})
    return out


async def explain_candidate_change(
    session: AsyncSession,
    *,
    candidate_id: uuid.UUID,
    use_ai_narrative: bool = True,
) -> dict:
    """Deterministic diff of a candidate against its predecessor, plus a narrative.

    Raises `ValueError` when the candidate does not exist. A candidate that
    simply has no predecessor is *not* an error — a first extraction or a
    hand-authored rule legitimately has nothing to compare against — so that
    returns a populated result with `comparable: False` rather than raising.
    """
    candidate = await session.get(CandidateRule, candidate_id)
    if candidate is None:
        raise ValueError(f"candidate rule '{candidate_id}' not found")

    after = candidate.payload_json or {}

    if candidate.baseline_candidate_id is None:
        return {
            "candidate_id": str(candidate_id),
            "comparable": False,
            "delta_status": candidate.delta_status,
            "reason": _no_baseline_reason(candidate.delta_status),
            "semantic_changes": [],
            "wording_changes": [],
            "narrative": None,
        }

    baseline = await session.get(CandidateRule, candidate.baseline_candidate_id)
    if baseline is None:
        # The self-FK is ON DELETE SET NULL, so this means the row was removed
        # between classification and now. Report it honestly rather than
        # presenting the rule as if it had never had a predecessor.
        return {
            "candidate_id": str(candidate_id),
            "comparable": False,
            "delta_status": candidate.delta_status,
            "reason": "The rule this one was compared against is no longer stored, so the change cannot be reconstructed.",
            "semantic_changes": [],
            "wording_changes": [],
            "narrative": None,
        }

    before = baseline.payload_json or {}
    semantic_changes = _diff_fields(before, after, SEMANTIC_FIELDS)
    wording_changes = _diff_fields(before, after, PROSE_FIELDS)

    baseline_reference = None
    if baseline.extraction_run_id:
        run = await session.get(ExtractionRun, baseline.extraction_run_id)
        baseline_reference = run.reference if run else None

    result = {
        "candidate_id": str(candidate_id),
        "comparable": True,
        "delta_status": candidate.delta_status,
        "reason": None,
        "baseline_candidate_id": str(baseline.id),
        "baseline_run_reference": baseline_reference,
        "baseline_review_status": baseline.review_status,
        "semantic_changes": semantic_changes,
        "wording_changes": wording_changes,
        "narrative": None,
    }

    settings = get_settings()
    if use_ai_narrative and settings.ai_enabled and (semantic_changes or wording_changes):
        try:
            ai_client = AzureOpenAIClient(settings)
            result["narrative"] = await ai_client.chat(
                [
                    {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "rule_title": after.get("title"),
                                "semantic_changes": semantic_changes,
                                "wording_changes": wording_changes,
                            },
                            indent=2,
                            default=str,
                        ),
                    },
                ],
                deployment=settings.azure_openai_fast_deployment,
                max_tokens=500,
            )
        except Exception as exc:  # noqa: BLE001 - the deterministic diff stands on its own
            logger.warning("AI change narrative failed for candidate %s: %s", candidate_id, exc)
            result["narrative"] = None

    return result


def _no_baseline_reason(delta_status: str | None) -> str:
    if delta_status == "new":
        return "This rule did not appear in the previous extraction of this document, so there is nothing to compare it against."
    if delta_status == "baseline":
        return "This came from the first extraction of this document — there was no previous run to compare against."
    return "This rule was not matched to a rule from a previous run, so no change can be shown."
