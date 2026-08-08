"""Draft candidate rules from policy text a human typed, rather than from an
ingested document.

`ai_extraction` answers "what rules are in this document?". This module answers
"what rule is this sentence I just wrote?" — the same destination, reached from
a different starting point, and it deliberately reuses the same machinery:

    typed text -> canonical + DMN JSON  (formulate: the policy formulator agent)
               -> CanonicalRule         (deterministic derivation, no model)

Two design decisions are worth stating explicitly, because both are places
where a second, divergent implementation would have been easy and wrong.

1. **Stage 1 is skipped on purpose, not by omission.** Document extraction runs
   a passage extractor first, whose entire job is to locate the policy-bearing
   spans inside a large document and copy them out verbatim so the formulator
   never sees contents pages or boilerplate. A person typing a policy statement
   has already performed that selection by choosing what to type; their text
   *is* the passage. Running Stage 1 over it would ask an agent to re-derive a
   judgement the author already made, and could silently discard the author's
   own words. So the typed text goes straight to Stage 2.

   The cost of skipping Stage 1 is that the verbatim-copy guarantee no longer
   applies, because there is no source document to copy from and therefore
   nothing to verify against. That is honest for authored text — the author is
   the source of truth — but it does mean drafts produced here carry no
   `evidence`, and that absence is reported to the caller rather than papered
   over with a fabricated citation.

2. **Nothing is persisted.** This returns unsaved drafts. The human reviews
   them in the form, edits whatever they disagree with, and submits through the
   ordinary `POST /api/policy-sets/{key}/candidate-rules` draft endpoint, which
   is the single door into the review queue. Writing rows here would create a
   second door that bypasses the author's own review of the agent's work — the
   exact failure mode the review queue exists to prevent. `ai_rewrite`'s
   preview/apply split makes the same choice for the same reason.

The returned `trace` describes what the pipeline actually did, step by step, so
the drafting UI can show the derivation instead of a spinner. It is built from
the real formulation and the real mapper output — it is a report of work done,
never a scripted animation.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.formulation import PolicyFormulation
from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.ai_extraction import PARSER_VERSION, PROMPT_VERSION
from policy_platform.infrastructure.formulation_mapping import formulation_to_candidate_rules
from policy_platform.infrastructure.policy_formulator import (
    PolicyFormulationError,
    PolicyFormulatorAgent,
)
from policy_platform.infrastructure.repositories import PolicySetRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Upper bound on a single authored statement. Generous enough for a long
#: multi-clause policy, low enough that a pasted document is rejected with a
#: clear message instead of being quietly formulated as one giant rule — a
#: whole document belongs in the ingestion pipeline, which gives it clause
#: addressing, evidence and a re-runnable extraction record.
MAX_SOURCE_CHARS = 20_000

#: Recorded as each draft's source note. These rules cite no clause because
#: none exists; saying so is the point.
AUTHORED_SOURCE_NOTE = "authored directly by a user (no source document)"


def _excerpt(text: str, limit: int = 220) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _condition_summary(rule: CanonicalRule) -> str:
    """One-line, human-readable shape of a derived condition."""

    node: Any = rule.condition
    if node is None:
        return "none"
    node_type = getattr(node, "type", None)
    if node_type == "factComparison":
        return f"{node.fact} {node.operator} {node.value!r}"
    if node_type == "all":
        return f"all of {len(node.all)} comparison(s)"
    if node_type == "any":
        return f"any of {len(node.any)} comparison(s)"
    if node_type == "alwaysTrue":
        return "always true (placeholder — not machine executable)"
    return str(node_type or "unknown")


def _canonical_items(formulation: PolicyFormulation) -> list[dict]:
    """What the agent said it found, in its own vocabulary."""

    items: list[dict] = []
    for index, policy in enumerate(formulation.canonical_policies):
        rule = policy.rule
        items.append(
            {
                "index": index,
                "source_text": _excerpt(policy.source_text),
                "extraction_status": policy.extraction_status.value,
                "rule_type": rule.rule_type.value if rule else None,
                "subject": (rule.subject if rule else None) or "",
                "modality": (rule.modality if rule else None) or "",
                "predicate": (rule.predicate if rule else None) or "",
                "condition": (rule.condition if rule else None) or "",
                "ambiguity": [a.value for a in policy.ambiguity],
            }
        )
    return items


def _derived_items(rules: list[CanonicalRule]) -> list[dict]:
    """What the deterministic mapper produced from that, per rule."""

    return [
        {
            "rule_id": rule.rule_id,
            "title": rule.title,
            "rule_type": rule.rule_type.value,
            "effect_type": rule.effect.type.value,
            "effect_action": rule.effect.action,
            "condition": _condition_summary(rule),
            "machine_executable": rule.machine_executable,
            "ambiguity_status": rule.ambiguity_status.value,
            "required_facts": [f.name for f in rule.required_facts],
        }
        for rule in rules
    ]


async def draft_rules_from_text(
    session: AsyncSession,
    *,
    policy_set_key: str,
    text: str,
    trusted_config: dict[str, Any] | None = None,
) -> dict:
    """Formulate authored policy text into unsaved `CanonicalRule` drafts.

    Raises `LookupError` for an unknown policy set, `ValueError` for invalid
    input (empty or oversized text) and `RuntimeError` when the agent itself
    fails, which the router maps onto 404/422/503 respectively.
    """

    settings = get_settings()

    source_text = (text or "").strip()
    if not source_text:
        raise ValueError("describe the policy in your own words before generating a rule")
    if len(source_text) > MAX_SOURCE_CHARS:
        raise ValueError(
            f"statement is {len(source_text)} characters; the limit is {MAX_SOURCE_CHARS}. "
            "Upload it as a source document instead — that path gives every rule "
            "clause-level evidence, which authored text cannot have."
        )

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise LookupError(f"policy set '{policy_set_key}' not found")

    trace: list[dict] = [
        {
            "key": "read",
            "label": "Read your policy statement",
            "status": "done",
            "detail": f"{len(source_text)} characters, {len(source_text.split())} words",
            "items": [],
        }
    ]

    formulator = PolicyFormulatorAgent(
        AzureOpenAIClient(settings), settings, trusted_config=trusted_config
    )

    started = time.monotonic()
    try:
        formulation = await formulator.formulate(source_text)
    except PolicyFormulationError as exc:
        trace.append(
            {
                "key": "formulate",
                "label": "Formulate canonical policy",
                "status": "failed",
                "detail": str(exc),
                "items": [],
            }
        )
        logger.warning("authored-text formulation failed: %s", exc)
        raise RuntimeError(f"the policy formulator could not read that statement: {exc}") from exc
    formulate_ms = int((time.monotonic() - started) * 1000)

    trace.append(
        {
            "key": "formulate",
            "label": "Formulate canonical policy",
            "status": "done",
            "detail": (
                f"{settings.azure_openai_deployment} · {formulate_ms} ms · "
                f"{len(formulation.canonical_policies)} canonical "
                f"{'policy' if len(formulation.canonical_policies) == 1 else 'policies'}"
            ),
            "items": _canonical_items(formulation),
        }
    )

    rules, skipped = formulation_to_candidate_rules(
        formulation,
        policy_set_id=str(policy_set.id),
        # Preview only: no run row exists, so lineage records a synthetic id.
        # It is regenerated when the human actually submits the draft, which is
        # when a real (manual-entry) run is attached.
        extraction_run_id=str(uuid.uuid4()),
        deployment_name=settings.azure_openai_deployment,
        prompt_version=PROMPT_VERSION,
        parser_version=PARSER_VERSION,
        evidence=[],
        source_note=AUTHORED_SOURCE_NOTE,
    )

    trace.append(
        {
            "key": "derive",
            "label": "Derive executable rule",
            "status": "done" if rules else "skipped",
            "detail": (
                f"{len(rules)} rule{'' if len(rules) == 1 else 's'} derived"
                + (f", {len(skipped)} skipped" if skipped else "")
            ),
            "items": _derived_items(rules),
        }
    )

    if skipped:
        trace.append(
            {
                "key": "skipped",
                "label": "Not turned into rules",
                "status": "skipped",
                "detail": f"{len(skipped)} item{'' if len(skipped) == 1 else 's'}",
                "items": [
                    {"item": _excerpt(str(s.get("item", "")), 160), "reason": s.get("reason", "")}
                    for s in skipped
                ],
            }
        )

    return {
        "policy_set_key": policy_set_key,
        "source_text": source_text,
        "rules": [rule.model_dump(mode="json") for rule in rules],
        "skipped": skipped,
        "trace": trace,
        "extraction_statuses": sorted(
            {p.extraction_status.value for p in formulation.canonical_policies}
        ),
        # Authored text has no clause to cite. Stated as a first-class field so
        # the UI can show it as a known property of this path rather than
        # leaving a reviewer to wonder why the evidence panel is empty.
        "has_evidence": False,
    }
