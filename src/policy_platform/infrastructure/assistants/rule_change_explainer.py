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

- **semantic changes** — every top-level field on which `semantic_core` found
  the two rules to differ, i.e. exactly what made the system call this rule
  changed. `rule_delta.SEMANTIC_FIELDS` orders the ones a reviewer usually
  wants first; anything else the core distinguished follows, in a stable
  order. The list drives *sequence*, never *inclusion* — a display list can
  safely be partial, but a display list used as a filter is a way of hiding
  the reason a rule was flagged.
- **wording changes** — title, description and the other presentational
  fields. The model rewords freely between runs, so these are reported but
  explicitly marked as not affecting behaviour. Presenting them in the same
  list as a changed threshold would be misleading.

Identity and display are deliberately not the same list, and this module does
not try to make them one. Identity answers *is this the same rule*; this
answers *what should a human look at*. What is not defensible is the second
being silent about something the first counted: if the system decided two
rules differ, the reviewer is shown why. So the floor is identity and the
ceiling is higher — prose changes appear here and are ignored by identity.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, ExtractionRun
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.projection.rule_delta import (
    NON_SEMANTIC_PROSE,
    SEMANTIC_FIELDS,
    semantic_core,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Presentational fields. Reported, but never counted as a behavioural change.
#: Derived from the prose set identity excludes rather than restated, so the
#: two cannot drift apart and leave a field reported by neither side. Title and
#: description lead because they are what a reviewer reads first.
PROSE_FIELDS: tuple[str, ...] = ("title", "description") + tuple(
    sorted(NON_SEMANTIC_PROSE - {"title", "description"})
)

_EXPLAIN_SYSTEM_PROMPT = """You help a policy reviewer understand what changed \
between two extractions of the same policy rule from a source document.

You are given a deterministic JSON diff with two sections:
- "semantic_changes": fields that make this a different rule from its predecessor.
- "wording_changes": presentational rewording that does NOT change behaviour.

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


def semantic_diff(before: dict, after: dict) -> list[dict]:
    """Every field on which the two rules' cores differ, in reading order.

    Computed from `semantic_core` rather than from the raw payloads, which is
    what makes the reported set exactly the set the system used to decide the
    rules differ — not a subset of it, and not a superset containing churn the
    identity deliberately ignores. A rule whose only difference is its position
    in the model's output array is the same rule, and shows nothing here.

    Before this, the diff walked `SEMANTIC_FIELDS` alone. Seven of those ten
    fields are constant across the live corpus, while the fields carrying what
    a rule actually decides — its trigger, its subject, its temporal constraint
    — sit inside `formulation` and `attributes` and were walked by nothing. A
    reviewer shown a `Changed` badge and an empty diff concludes the tool is
    confused, and on that code they were right.
    """
    core_before, core_after = semantic_core(before), semantic_core(after)
    present = set(core_before) | set(core_after)
    ordered = [name for name in SEMANTIC_FIELDS if name in present]
    ordered += sorted(present.difference(SEMANTIC_FIELDS))
    return _diff_fields(core_before, core_after, tuple(ordered))


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
    semantic_changes = semantic_diff(before, after)
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
