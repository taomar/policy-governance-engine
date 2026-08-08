"""Ask-AI: retrieval-augmented chat grounded in our own indexed clauses and
the currently-approved rules of a policy set.

Scoping: retrieval is restricted (via `policy_id` filter) to `SourceDocument`
ids we ourselves created — the shared `policy-authoring` index also holds
~4760 unrelated documents under `policy_id = "POL-HW-001"` from another
system; those are never included here. See infrastructure/search/indexing.py
for the write-side half of this scoping decision.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import SourceDocument
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    CandidateRuleRepository,
    PolicySetRepository,
)
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

# Structured-output contract (Section 3 verbatim-sourcing requirement): the
# model must separate (a) facts copied character-for-character from CONTEXT
# — grouped by topic so a long answer stays scannable — from (b) its own
# synthesis/interpretation of what the user specifically asked. Mixing the
# two in one free-text blob is exactly what made it impossible to tell
# whether a given sentence was real policy wording or an AI paraphrase, so
# the schema forces the split at the data level rather than relying on the
# model's prose to signal it.
_SYSTEM_PROMPT = """You are "Policy Assistant", an in-app AI helper for a policy administrator working \
in a policy governance platform. You help them understand source documents, currently-approved rules, \
and how to use the platform. Answer ONLY using the CONTEXT provided below (source document excerpts and \
approved rule summaries) plus the conversation history. Never invent policy content that is not present \
in CONTEXT.

You must reply with ONLY a single JSON object (no markdown code fences, no prose outside the JSON) with \
exactly this shape:

{
  "groups": [
    {
      "heading": "<short topic label for this cluster of facts, e.g. 'Approval Thresholds'>",
      "facts": [
        {
          "text": "<a VERBATIM excerpt copied character-for-character from CONTEXT>",
          "source_label": "<short citation, e.g. 'HR Guide Policy and Procedure Template — p33-para-5' or a rule id like 'RULE-HW-002'>"
        }
      ]
    }
  ],
  "reflection": "<your own words, clearly your synthesis/interpretation — see rules below>"
}

Hard rules:
1. Every "text" value must be copied EXACTLY from CONTEXT — do not paraphrase, reword, summarize, \
correct grammar/typos, or translate. You may truncate a long clause at a sentence boundary, but every \
word you keep must be unmodified. If you cannot find a verbatim excerpt that answers part of the \
question, leave it out of "facts" rather than inventing or rewording one.
2. Group related facts under one "heading" so the answer is easy to scan; use as many or as few groups \
as the material actually needs (at least one group if any relevant facts exist).
3. "reflection" is the ONLY place for your own words: directly answer what the user specifically asked, \
synthesize or compare across the facts above, flag gaps/ambiguity, and suggest next steps. Never put \
your own paraphrasing inside a "facts[].text" value.
4. If nothing in CONTEXT is relevant, return "groups": [] and use "reflection" to say so plainly and \
suggest what the user could check instead.
5. Be concise: prefer a small number of well-chosen facts over an exhaustive dump. Rich but not bloated."""


async def _all_our_document_ids(session: AsyncSession) -> list[str]:
    result = await session.execute(select(SourceDocument.id))
    return [str(row[0]) for row in result.all()]


async def ask(
    session: AsyncSession,
    *,
    question: str,
    policy_set_key: str | None = None,
    history: list[dict] | None = None,
    focus_candidate_rule_id: str | None = None,
) -> dict:
    """Answer `question`, grounded in indexed clauses (+ approved rules if a policy set is given).

    Returns {"groups": [{"heading": str, "facts": [{"text": str, "source_label": str|None}]}],
    "reflection": str, "sources": [...]}. Every fact "text" is verbatim from CONTEXT (never
    paraphrased); "reflection" is the model's own synthesis/answer in its own words. "sources"
    lists the raw search hits retrieved for grounding (unchanged provenance chips).
    Raises RuntimeError if AI is not configured.

    `focus_candidate_rule_id`, when given, pins the exact JSON of that one
    candidate rule (plus any other candidate/approved rules sharing its
    `group_label`, if set) at the front of CONTEXT — this is what powers the
    per-rule "Ask AI about this rule" action in the Review tab, so a reviewer
    can ask "does this conflict with anything?" or "explain this in plain
    English" and get an answer grounded in the *exact* rule they're looking
    at, not whatever the general retrieval happens to surface.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)
    context_blocks: list[str] = []
    sources: list[dict] = []

    if focus_candidate_rule_id:
        try:
            candidate_repo = CandidateRuleRepository(session)
            focus_candidate = await candidate_repo.get_by_id(uuid.UUID(focus_candidate_rule_id))
            if focus_candidate is not None:
                siblings: list[str] = []
                group_label = focus_candidate.payload_json.get("group_label")
                if group_label:
                    peers = await candidate_repo.list_by_policy_set(focus_candidate.policy_set_id)
                    for peer in peers:
                        if peer.id == focus_candidate.id:
                            continue
                        if peer.payload_json.get("group_label") == group_label:
                            siblings.append(
                                f"- [{peer.payload_json.get('rule_id')}] "
                                f"({peer.review_status}) {peer.payload_json.get('title')}: "
                                f"{json.dumps(peer.payload_json.get('condition'))} -> "
                                f"{json.dumps(peer.payload_json.get('effect'))}"
                            )
                focus_block = (
                    "THE RULE THE REVIEWER IS ASKING ABOUT (this is the primary subject of the "
                    "question — answer specifically about it):\n"
                    f"{json.dumps(focus_candidate.payload_json, indent=2, default=str)}"
                )
                if siblings:
                    focus_block += (
                        "\n\nOther rules in the same variation group "
                        f"('{group_label}') — check these for consistency/conflicts:\n" + "\n".join(siblings)
                    )
                context_blocks.append(focus_block)
        except Exception as exc:  # noqa: BLE001 - chat should still answer without the focus rule
            logger.warning("failed to load focus candidate rule during ask(): %s", exc)

    if settings.search_enabled:
        try:
            doc_ids = await _all_our_document_ids(session)
            if doc_ids:
                [vector] = await ai_client.embed([question])
                search_client = AzureSearchClient(settings)
                hits = await search_client.vector_search(
                    settings.azure_search_authoring_index,
                    query_text=question,
                    vector=vector,
                    policy_ids=doc_ids,
                    top=6,
                )
                for hit in hits:
                    heading = hit.get("heading") or ""
                    section = hit.get("section_heading") or hit.get("clause_number") or ""
                    body = hit.get("body") or ""
                    context_blocks.append(f"[{heading} — {section}]\n{body}")
                    sources.append(
                        {
                            "heading": heading,
                            "section": section,
                            "clause_id": hit.get("clause_id"),
                            "document_id": hit.get("document_id"),
                        }
                    )
        except Exception as exc:  # noqa: BLE001 - chat should still answer from rules alone
            logger.warning("search retrieval failed during ask(): %s", exc)

    if policy_set_key:
        try:
            policy_set_repo = PolicySetRepository(session)
            policy_set = await policy_set_repo.get_by_key(policy_set_key)
            if policy_set is not None:
                version_repo = ApprovedPolicyVersionRepository(session)
                active = await version_repo.get_active_version(policy_set.id)
                if active is not None:
                    package = approved_policy_version_to_package(active)
                    rule_lines = [
                        f"- [{r.rule_id}] ({r.rule_type.value}, {r.effect.type.value}) {r.title}: {r.description}"
                        for r in package.rules
                    ]
                    if rule_lines:
                        context_blocks.append(
                            f"Currently-approved rules for policy set '{policy_set_key}' "
                            f"(version {active.version_number}):\n" + "\n".join(rule_lines)
                        )
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to load approved rules context during ask(): %s", exc)

    context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no matching context found)"
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": f"CONTEXT:\n{context_text}\n\nQUESTION: {question}"})

    raw = await ai_client.chat(
        messages,
        deployment=settings.azure_openai_fast_deployment,
        json_mode=True,
        # Deterministic per the "AI should never change any words" requirement:
        # temperature=0 minimizes run-to-run drift in both wording choice and
        # which verbatim excerpts get selected.
        temperature=0,
        # Fast (non-reasoning) deployment; budget covers several fact groups
        # plus a reflection paragraph without the reasoning-model emptiness
        # quirk documented on AzureOpenAIClient.chat().
        max_tokens=1600,
    )
    groups, reflection = _parse_structured_answer(raw)
    return {"groups": groups, "reflection": reflection, "sources": sources}


def _parse_structured_answer(raw: str) -> tuple[list[dict], str]:
    """Defensively parse the model's structured JSON reply.

    Falls back to a single reflection-only shape (empty groups) if the model
    ever returns something that isn't the exact contract — so a formatting
    slip degrades gracefully instead of breaking the chat endpoint.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [], raw if isinstance(raw, str) else ""

    if not isinstance(parsed, dict):
        return [], raw

    groups: list[dict] = []
    for group in parsed.get("groups") or []:
        if not isinstance(group, dict):
            continue
        heading = str(group.get("heading") or "").strip()
        facts: list[dict] = []
        for fact in group.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            text = str(fact.get("text") or "").strip()
            if not text:
                continue
            source_label = fact.get("source_label")
            facts.append({"text": text, "source_label": str(source_label).strip() if source_label else None})
        if heading and facts:
            groups.append({"heading": heading, "facts": facts})

    reflection = str(parsed.get("reflection") or "").strip()
    return groups, reflection
