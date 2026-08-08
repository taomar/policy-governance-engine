"""AI-assisted "how would this rule be obeyed?" scenario evaluator.

This is a deliberately separate, clearly-labeled path from the real
deterministic evaluation engine (`policy_platform.evaluator.engine`). It lets
a reviewer describe a scenario in plain English against a rule that may not
even be saved yet (e.g. a rule still being edited/revised in a form) and get
an AI's *advisory* reasoning about whether the rule's condition would fire
and what the predicted effect would be — useful for sanity-checking wording
before a formal `PolicyTest`/`Evaluation` exists.

This must never be confused with, or substituted for, a real evaluation:
the AI has no access to the deterministic condition evaluator here, and its
verdict is not authoritative. Callers (API + UI) must always surface the
`reasoning_effort` used and a clear "AI advisory, not a real evaluation"
label alongside the result.
"""
from __future__ import annotations

import json
import logging

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-scenario-eval-v1"

VALID_REASONING_EFFORTS = ("low", "medium", "high")

_SYSTEM_PROMPT = """You are a policy-reasoning assistant helping a human reviewer sanity-check a \
governance rule. You are given one rule as JSON (title, condition, effect, required facts, \
exceptions, scope) and a plain-English scenario describing a hypothetical situation. Reason step \
by step about whether the rule's condition would be satisfied by that scenario, using only the \
facts stated or clearly implied by the scenario.

Return ONLY a JSON object with these keys:
- "applies": one of "yes", "no", or "uncertain" (use "uncertain" if the scenario is missing facts \
the condition needs, or the wording is genuinely ambiguous).
- "reasoning": 2-5 sentences walking through how the scenario's facts compare against the \
condition, in plain English a non-technical reviewer can follow.
- "predicted_outcome": one sentence stating what would happen if this rule fired (its effect/action), \
or "No effect — condition not met" / "Cannot determine — missing information" as appropriate.
- "missing_facts": a JSON array of fact names (strings) the scenario doesn't specify that the \
condition or required_facts need to reach a confident answer. Empty array if none.

This is advisory reasoning only, not a substitute for the deterministic evaluation engine — do \
not claim certainty you don't have; prefer "uncertain" over guessing."""


async def evaluate_scenario(rule_payload: dict, *, scenario: str, reasoning_effort: str = "medium") -> dict:
    """Return {"applies": str, "reasoning": str, "predicted_outcome": str,
    "missing_facts": list[str], "reasoning_effort": str} without persisting
    anything and without touching the deterministic engine."""

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    if reasoning_effort not in VALID_REASONING_EFFORTS:
        reasoning_effort = "medium"

    # Validate the rule shape up front so a malformed in-progress draft (e.g.
    # invalid JSON from the Advanced-mode textarea) fails clearly instead of
    # producing a confusing AI response about a broken schema.
    rule = CanonicalRule.model_validate(rule_payload)
    ai_client = AzureOpenAIClient(settings)

    user_content = (
        f"Rule JSON:\n{json.dumps(rule.model_dump(mode='json'), indent=2)}\n\n"
        f"Scenario: {scenario}"
    )

    # The reasoning_effort field isn't verified against every deployment —
    # if the API rejects it outright, drop it for all remaining attempts
    # rather than failing the whole feature.
    effort_to_send: str | None = reasoning_effort
    last_error: str | None = None
    for attempt in range(2):
        prompt = user_content
        if last_error:
            prompt += f"\n\nYour previous response was invalid: {last_error}\nPlease correct it and retry."
        try:
            raw = await ai_client.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                deployment=settings.azure_openai_deployment,
                json_mode=True,
                max_tokens=4000,
                timeout=180.0,
                reasoning_effort=effort_to_send,
            )
        except Exception as exc:  # noqa: BLE001
            if effort_to_send is not None:
                logger.warning(
                    "chat call with reasoning_effort=%s failed (%s); retrying without it", effort_to_send, exc
                )
                effort_to_send = None
                raw = await ai_client.chat(
                    [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    deployment=settings.azure_openai_deployment,
                    json_mode=True,
                    max_tokens=4000,
                    timeout=180.0,
                )
            else:
                raise
        try:
            parsed = json.loads(raw)
            applies = str(parsed.get("applies") or "uncertain").lower()
            if applies not in ("yes", "no", "uncertain"):
                applies = "uncertain"
            missing_facts = parsed.get("missing_facts") or []
            if not isinstance(missing_facts, list):
                missing_facts = []
            return {
                "applies": applies,
                "reasoning": str(parsed.get("reasoning") or ""),
                "predicted_outcome": str(parsed.get("predicted_outcome") or ""),
                "missing_facts": [str(f) for f in missing_facts],
                # Report what was actually accepted by the deployment, not just
                # what was requested — falls back to "default" if the
                # deployment rejected the reasoning_effort field entirely.
                "reasoning_effort": effort_to_send or "default",
            }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("AI scenario evaluation attempt %s failed to parse: %s", attempt, exc)

    raise RuntimeError(f"AI scenario evaluation did not produce a valid response after retry: {last_error}")
