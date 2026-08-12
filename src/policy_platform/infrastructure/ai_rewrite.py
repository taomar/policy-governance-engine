"""AI-assisted rewrite: given a candidate rule's current payload and a
human's plain-English instruction (e.g. "raise the threshold to $750",
"make the wording less ambiguous"), draft an updated `CanonicalRule` for a
human to review and accept/reject. This service never applies a rewrite by
itself — `apply_rewrite` is a separate, explicit step the API only calls
after the reviewer accepts the suggestion.
"""
from __future__ import annotations

import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.repositories import CandidateRuleRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-rewrite-v1"

_SYSTEM_PROMPT = """You edit a single governance rule for a policy administrator, following their \
instruction. You are given the rule as JSON (matching a strict schema) and a plain-English \
instruction. Return ONLY a JSON object: {"rule": <the full updated rule JSON, same schema as input>, \
"explanation": "<1-3 sentence plain-English summary of what you changed and why>"}.

Rules:
- Keep "rule_id", "policy_set_id", "policy_version_id", "schema_version" unchanged.
- You may change title, description, condition, effect, required_facts, scope, priority, \
effective_from/effective_to, ambiguity_status, machine_executable, exceptions.
- If the instruction asks you to change a concrete number/threshold/date, make sure the "condition" \
field's "value" (if it is a factComparison node) is updated consistently with description/title.
- If you are not fully confident the resulting condition is precise and unambiguous, set \
"ambiguity_status" to "human_judgment_required" and "machine_executable" to false rather than \
guessing at exact logic.
- Do not remove existing "evidence" or "lineage" entries.
- The output rule JSON must be syntactically complete and match the same field names as the input.

The "condition" field is a discriminated union — it MUST be exactly one of these four shapes \
(nested recursively; there are no other field names allowed):
- Leaf comparison: {"type": "factComparison", "fact": "<fact_name>", "operator": "<op>", "value": <literal>} \
where <op> is one of: equals, notEquals, greaterThan, greaterThanOrEqual, lessThan, lessThanOrEqual, \
in, notIn, contains, startsWith, endsWith, exists, isNull, before, after, onOrBefore, onOrAfter, \
withinDuration, countEquals, countGreaterThan.
- Logical AND: {"type": "all", "all": [<ConditionNode>, <ConditionNode>, ...]}
- Logical OR: {"type": "any", "any": [<ConditionNode>, <ConditionNode>, ...]}
- Logical NOT: {"type": "not", "not": <ConditionNode>}
Example of "if device_returned is true OR employee_transferred is true": \
{"type": "any", "any": [{"type": "factComparison", "fact": "device_returned", "operator": "equals", \
"value": true}, {"type": "factComparison", "fact": "employee_transferred", "operator": "equals", "value": true}]}. \
Never invent field names like "conditions" or "condition" inside a boolean node — the list/child MUST be \
keyed under the same name as "type" (i.e. an "any" node's children live under the key "any", an "all" \
node's children live under the key "all")."""


async def _suggest_rewrite_for_rule(current_rule: CanonicalRule, *, instruction: str) -> dict:
    """Core AI call shared by both the candidate-based and raw-payload entry
    points below. Returns {"current": dict, "suggested": dict, "explanation": str}
    without persisting anything."""

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)

    user_content = (
        f"Current rule JSON:\n{json.dumps(current_rule.model_dump(mode='json'), indent=2)}\n\n"
        f"Instruction: {instruction}"
    )

    last_error: str | None = None
    last_raw_rule: dict | None = None
    last_explanation = ""
    condition_only_failure = False

    for attempt in range(2):
        prompt = user_content
        if last_error:
            prompt += f"\n\nYour previous response was invalid: {last_error}\nPlease correct it and retry."
        raw = await ai_client.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            deployment=settings.azure_openai_deployment,
            json_mode=True,
            # See openai_client.chat() docstring: gpt-5.6-sol is a reasoning model
            # and needs a generous budget or it returns empty content.
            max_tokens=8000,
            timeout=180.0,
        )
        try:
            parsed = json.loads(raw)
            suggested_raw = parsed["rule"]
            # Force-preserve identity fields — never trust the model to keep them stable.
            suggested_raw["rule_id"] = current_rule.rule_id
            suggested_raw["policy_set_id"] = current_rule.policy_set_id
            suggested_raw["policy_version_id"] = current_rule.policy_version_id
            suggested_raw["rule_revision"] = current_rule.rule_revision + 1
            suggested = CanonicalRule.model_validate(suggested_raw)
            return {
                "current": current_rule.model_dump(mode="json"),
                "suggested": suggested.model_dump(mode="json"),
                "explanation": str(parsed.get("explanation") or ""),
            }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("AI rewrite attempt %s failed validation: %s", attempt, exc)
            if isinstance(locals().get("suggested_raw"), dict):
                last_raw_rule = suggested_raw
                last_explanation = str((locals().get("parsed") or {}).get("explanation") or "")
                condition_only_failure = isinstance(exc, ValidationError) and all(
                    err["loc"] and err["loc"][0] == "condition" for err in exc.errors()
                )

    # Safety fallback (mirrors ai_extraction.py's rule): if every retry's failure was
    # confined to the "condition" subtree — i.e. the model couldn't reliably encode
    # compound all/any/not logic — don't hard-fail the whole rewrite. Keep the AI's other
    # proposed changes but fall back the condition to the rule's CURRENT (unchanged) one,
    # and force machine_executable=False / ambiguity_status=human_judgment_required, the
    # same "never silently machine-executable without a human formalizing the condition"
    # invariant extraction already relies on. This guarantees the suggestion never implies
    # logic (via description/effect) that the machine condition doesn't actually encode.
    if condition_only_failure and last_raw_rule is not None:
        try:
            fallback_raw = dict(last_raw_rule)
            fallback_raw["condition"] = current_rule.condition.model_dump(mode="json")
            fallback_raw["machine_executable"] = False
            fallback_raw["ambiguity_status"] = "human_judgment_required"
            suggested = CanonicalRule.model_validate(fallback_raw)
            note = (
                "⚠ AI could not safely encode the requested condition logic as valid structured "
                "logic, so the condition was left unchanged from the current policy and this "
                "suggestion is marked as requiring human judgment before it can be decided by "
                "comparison. "
            )
            return {
                "current": current_rule.model_dump(mode="json"),
                "suggested": suggested.model_dump(mode="json"),
                "explanation": note + last_explanation,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI rewrite condition-fallback also failed validation: %s", exc)

    raise RuntimeError(f"AI rewrite did not produce a schema-valid rule after retry: {last_error}")


async def suggest_rewrite(session: AsyncSession, *, candidate_id: uuid.UUID, instruction: str) -> dict:
    """Return {"current": dict, "suggested": dict, "explanation": str} without persisting anything."""

    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.get_by_id(candidate_id)
    if candidate is None:
        raise ValueError(f"candidate rule '{candidate_id}' not found")

    current_rule = CanonicalRule.model_validate(candidate.payload_json)
    return await _suggest_rewrite_for_rule(current_rule, instruction=instruction)


async def suggest_rewrite_for_payload(rule_payload: dict, *, instruction: str) -> dict:
    """Same as `suggest_rewrite`, but for a rule that has no `CandidateRule` row
    yet — e.g. the "Revise this rule" flow, which pre-fills an edit form from a
    *published* rule and only creates the candidate once the user submits.
    Lets the "Populate with AI" button in that form work before any candidate
    exists."""

    current_rule = CanonicalRule.model_validate(rule_payload)
    return await _suggest_rewrite_for_rule(current_rule, instruction=instruction)


async def apply_rewrite(session: AsyncSession, *, candidate_id: uuid.UUID, suggested_payload: dict) -> dict:
    """Persist an accepted suggestion onto the candidate (still pre-approval only)."""

    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.get_by_id(candidate_id)
    if candidate is None:
        raise ValueError(f"candidate rule '{candidate_id}' not found")
    if candidate.review_status not in ("candidate", "rejected", "changes_requested"):
        raise ValueError(f"candidate rule '{candidate_id}' is '{candidate.review_status}' and cannot be rewritten")

    # Re-validate before persisting — never trust a client-supplied payload blindly.
    validated = CanonicalRule.model_validate(suggested_payload)
    candidate = await candidate_repo.update_payload(candidate, payload_json=validated.model_dump(mode="json"))
    await session.commit()
    return {"id": str(candidate.id), "revision": candidate.revision}
