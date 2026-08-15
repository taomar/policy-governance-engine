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
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import SourceDocument
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.persistence.repositories import (
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


#: The shape of an IETF BCP-47 language tag, near enough to keep this out of the
#: business of enumerating languages.
#:
#: WHY A SHAPE AND NOT A LIST. A list of accepted languages here would be the
#: same mistake as a pair of branches in the interface: a language added to the
#: reader's control would then also need adding here before it worked, and the
#: two lists would disagree the first time one was edited. The reader's control
#: decides what is on offer; this decides only that what arrived is a tag.
#:
#: WHY IT IS CHECKED AT ALL. The value is written into a system prompt. An
#: unchecked string there is an instruction channel — "…and ignore the rule
#: about quoting" is a valid Python string and would be a valid sentence in the
#: prompt. A tag has no spaces, no punctuation beyond the hyphen and no
#: newlines, so requiring that shape closes the channel without knowing a single
#: language.
#:
#: Matched with `fullmatch`, not `match`: `$` in Python also matches immediately
#: before a trailing newline, so `"ar\n"` would pass an anchored `match` and
#: carry a line break into the prompt.
_LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,4}")


def _answer_language_directive(tag: str) -> str:
    """Ask for this app's own words in one language, and for nothing else to move.

    The instruction names no language and mentions no script or direction — the
    tag arrives from the reader's choice and is quoted into the sentence, so
    this text reads identically for a language nobody has asked for yet.

    The separation it insists on is the one the schema already draws. `facts[]`
    is the document speaking and is quoted, so it is not ours to render into
    another language; `reflection` and the group headings are this app speaking
    and are what the reader asked to receive in their own. A model told only
    "answer in X" will helpfully translate the quotations too, which is how a
    reviewer ends up approving a rule against a paraphrase of the source while
    believing they had checked the source.
    """

    return (
        "\n\nLANGUAGE OF YOUR OWN WORDS.\n"
        "The reader has asked for this answer in the language written as the IETF BCP-47 tag "
        f'"{tag}". Write every word that is yours in that language, using that language\'s own '
        'script: every "heading", and the whole of "reflection".\n'
        "Two things are not yours and do not move. Every \"text\" in \"facts\" stays exactly as it "
        "appears in CONTEXT — same characters, same language, same script as the document wrote "
        "it — and every \"source_label\" keeps the wording of the citation it names. Quoting a "
        "passage written in one language inside a reply written in another is correct here and is "
        "what is being asked of you. If an excerpt cannot be kept unchanged, leave it out of "
        '"facts" rather than restating it in another language.'
    )



async def _all_our_document_ids(session: AsyncSession) -> list[str]:
    result = await session.execute(select(SourceDocument.id))
    return [str(row[0]) for row in result.all()]


#: How much of a policy's rules the model reads when a question is asked about
#: the whole policy. A budget, so a section running to seventy-odd rules costs
#: one bounded request rather than an unbounded one. Larger than the explainer's
#: 6000 because these records carry the document's own words as well as this
#: app's reading of them, and the point of showing both is lost if the budget
#: only fits one. Spent on whole records and never on part of one: half a record
#: is a different record, and the model would be answering about something the
#: extraction does not hold.
MAX_POLICY_RECORD_CHARS = 24000

#: The fields of a record that answer a question about the policy.
#:
#: Measured on this corpus, a stored candidate record runs 2.6k-7.9k characters,
#: of which most is machinery — xacml projections, dmn mappings, lineage,
#: hashes, discovered relationships. Sent whole, a budget that fits a policy
#: fits two of its rules, and a reviewer asking about a six-rule policy is told
#: about two. Sent as these fields, the same budget fits twenty-odd, so the
#: coverage statement mostly has nothing to report.
#:
#: This is a projection, not a summary: every value here is copied out of the
#: record unchanged, and `source_text` in particular is the document's own
#: words untouched. Nothing is rewritten on the way in, for the same reason
#: nothing is translated on the way out.
_EXTRACTED_FIELDS = (
    "title",
    "rule_type",
    "evaluation_mode",
    "condition",
    "effect",
    "attributes",
    "exceptions",
    "required_facts",
    "machine_executable",
)

#: What the model is told the two halves of a record are.
#:
#: `policy_explainer` shows the model this app's extracted record and never the
#: document's verbatim text, because a model shown both silently reconciles them
#: and hides extraction defects — that choice caught this app's own extraction
#: inverting a prohibition. An ask surface cannot inherit it: its answer contract
#: requires every quoted fact to be copied character-for-character from CONTEXT,
#: so a context with no verbatim text yields nothing quotable and collapses the
#: answer to reflection alone. And "does this match the document?" is a question
#: a reviewer is entitled to ask here.
#:
#: What is inherited is the reason. The reconciliation the explainer avoids
#: happens when a model reads the two as one fact stated twice. So they are
#: named as two claims, and a disagreement between them is asked for as a
#: finding — which is the defect the explainer's rule was protecting, reported
#: rather than merely not obscured.
_POLICY_BLOCK_PREAMBLE = (
    "THE POLICY THE REVIEWER IS ASKING ABOUT (this is the primary subject of the question — "
    "answer specifically about it).\n"
    "Each record below has two parts, and they are two separate claims, not one fact stated twice:\n"
    "  - what_this_app_extracted: the fields this app read out of the document — condition, "
    "effect, attributes, evaluation mode.\n"
    "  - the_documents_own_words: the source text, exactly as the document wrote it.\n"
    "Quote only from the second when you quote. If the two disagree — if the extracted fields say "
    "something the quoted words do not — report that disagreement plainly as part of your answer. "
    "Do not reconcile them, and do not pick whichever reads better.\n"
)


#: Which table a grounded answer's records were read out of.
#:
#: Reported to the caller rather than left to be inferred from which arguments
#: were sent. A draft row and a published rule can carry the same `rule_id` and
#: say different things — the draft is where a revision is being written, the
#: published rule is what the version promised — so "grounded in this policy"
#: is two different claims depending on which was read, and a reader deciding
#: whether a record is faithful needs to know which one they were told about.
RECORDS_FROM_PUBLISHED_VERSION = "published_version"
RECORDS_FROM_DRAFT_ROWS = "draft_records"


async def _version_rule_payloads(
    session: AsyncSession, policy_set_id: uuid.UUID, policy_version_id: str
) -> dict[str, dict] | None:
    """Every rule of one published version, by its own rule id.

    `None` — distinct from an empty mapping — when the version does not exist
    or belongs to a different policy set. The caller must not fall back to the
    draft rows in that case: a published record and the draft that produced it
    are two records, and answering about the second while the reader is looking
    at the first is the one failure this surface cannot have. An answer that
    does not arrive is recoverable; an answer about the wrong record is not.
    """
    try:
        version_uuid = uuid.UUID(policy_version_id)
    except (ValueError, AttributeError, TypeError):
        return None
    version = await ApprovedPolicyVersionRepository(session).get_by_id(version_uuid)
    if version is None or version.policy_set_id != policy_set_id:
        return None

    # The contract objects rather than the columns: `CanonicalRule` already
    # names every field `_policy_rule_record` reads, including the
    # `formulation.canonical.source_text` that carries the document's own
    # words, and publishing copies that formulation across verbatim. Rebuilding
    # the shape by hand here would be a second reading of the same row, free to
    # drift from the one the evaluator consumes.
    package = approved_policy_version_to_package(version)
    by_rule_id: dict[str, dict] = {}
    for rule in package.rules:
        if rule.rule_id not in by_rule_id:
            by_rule_id[rule.rule_id] = rule.model_dump(mode="json")
    return by_rule_id


async def _policy_rule_payloads(
    session: AsyncSession,
    policy_set_key: str | None,
    rule_ids: list[str],
    *,
    policy_version_id: str | None = None,
) -> tuple[list[dict], str]:
    """The records for `rule_ids`, in the order asked for, and where they came from.

    The caller's order is the order the card shows, which is document order, so
    a coverage statement about "the first N" names a prefix a reader can point
    at rather than an arbitrary subset. Ids not found are skipped rather than
    guessed at.

    `policy_version_id` moves the lookup from the draft rows to that published
    version. It is not an optimisation: the published page shows sealed records,
    and resolving their ids against `candidate_rules` would answer about a draft
    that may have been revised since — or, where no draft survives, about
    nothing at all while still looking like an answer.
    """
    if not policy_set_key:
        return [], RECORDS_FROM_DRAFT_ROWS
    policy_set = await PolicySetRepository(session).get_by_key(policy_set_key)
    if policy_set is None:
        return [], RECORDS_FROM_DRAFT_ROWS

    if policy_version_id:
        published = await _version_rule_payloads(session, policy_set.id, policy_version_id)
        if published is None:
            return [], RECORDS_FROM_PUBLISHED_VERSION
        return (
            [published[rule_id] for rule_id in rule_ids if rule_id in published],
            RECORDS_FROM_PUBLISHED_VERSION,
        )

    rows = await CandidateRuleRepository(session).list_by_policy_set(policy_set.id)
    by_rule_id: dict[str, dict] = {}
    for row in rows:
        rule_id = row.payload_json.get("rule_id")
        if rule_id and rule_id not in by_rule_id:
            by_rule_id[rule_id] = row.payload_json
    return (
        [by_rule_id[rule_id] for rule_id in rule_ids if rule_id in by_rule_id],
        RECORDS_FROM_DRAFT_ROWS,
    )


def _policy_rule_record(payload: dict) -> dict:
    """One record, split into the two claims the preamble names.

    The split is structural rather than described. A record whose extracted
    fields and quoted words sit in one flat object invites a model to read them
    as one fact stated twice — which is the reconciliation `policy_explainer`
    avoids by withholding the source altogether. This surface cannot withhold
    it, so it names the halves instead: a disagreement between them has
    somewhere to be, and can be reported rather than smoothed over.
    """
    formulation = payload.get("formulation")
    canonical = formulation.get("canonical") if isinstance(formulation, dict) else None
    canonical = canonical if isinstance(canonical, dict) else {}
    extracted = {
        field: payload[field]
        for field in _EXTRACTED_FIELDS
        if payload.get(field) not in (None, "", [], {})
    }
    if canonical.get("rule"):
        extracted["parsed"] = canonical["rule"]

    evidence = payload.get("evidence")
    first = evidence[0] if isinstance(evidence, list) and evidence else {}
    where = first.get("section") if isinstance(first, dict) else None

    return {
        "rule_id": payload.get("rule_id"),
        "what_this_app_extracted": extracted,
        "the_documents_own_words": {
            "source_text": canonical.get("source_text"),
            "read_from": where,
        },
    }


def _policy_context_block(payloads: list[dict]) -> tuple[str, int]:
    """The policy block, and how many records went into it.

    `ensure_ascii=False` is not cosmetic. Escaped, an Arabic clause reaches the
    model as `\\u0627\\u0644...` rather than as its characters, and a model asked
    to copy a fact character-for-character would copy the escapes. The document's
    words have to arrive as the document's words for the no-translation rule to
    mean anything in a script that is not Latin.
    """
    rendered: list[str] = []
    spent = 0
    for payload in payloads:
        text = json.dumps(_policy_rule_record(payload), indent=2, default=str, ensure_ascii=False)
        # At least one whole record always goes in, even if it alone exceeds the
        # budget: an answer grounded in nothing is worse than one bounded request.
        if rendered and spent + len(text) > MAX_POLICY_RECORD_CHARS:
            break
        rendered.append(text)
        spent += len(text)
    return _POLICY_BLOCK_PREAMBLE + "\n" + "\n\n".join(rendered), len(rendered)


async def ask(
    session: AsyncSession,
    *,
    question: str,
    policy_set_key: str | None = None,
    history: list[dict] | None = None,
    focus_candidate_rule_id: str | None = None,
    focus_rule_ids: list[str] | None = None,
    answer_language: str | None = None,
    policy_version_id: str | None = None,
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

    `answer_language`, when given, is a BCP-47 tag naming the language the
    reader wants *this app's own words* in — the reflection and the group
    headings. It is asked for of the model rather than applied to the reply
    afterwards, because the reply carries quoted source text and a translation
    pass over it would rewrite the document. A tag that is not shaped like one
    is dropped: it would be reaching a system prompt as an instruction. Omitted,
    nothing about the request changes.

    `focus_rule_ids`, when given, grounds the answer on a whole policy: the
    records for those rule ids, in the order given, pinned at the front of
    CONTEXT. A policy can hold more rules than one request carries, so the reply
    adds a `grounding` object saying how many rules were asked about, how many
    were read, and which table they were read out of. It is reported rather than
    inferred — sending a subset silently would make "grounded in all of it" and
    "grounded in the first part of it" look identical to the reviewer relying on
    the answer, and the same is true of reading none of them: `grounding` is
    present whenever rule ids were asked for, including when nothing resolved,
    because an answer built from general retrieval alone and an answer built
    from the policy are otherwise indistinguishable on screen.

    `policy_version_id`, when given with `focus_rule_ids`, reads those records
    from that published version instead of from the draft rows. A published
    record and the draft that produced it share a `rule_id` and may say
    different things, so the id alone does not say which record a reader is
    looking at. Where the version does not exist, or belongs to another policy
    set, nothing is read and that is reported — this never falls back to the
    drafts, because an answer about the wrong record is worse than no answer.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)
    context_blocks: list[str] = []
    sources: list[dict] = []
    grounding: dict | None = None

    if focus_rule_ids:
        # Built before the load, and never conditional on it succeeding. The
        # failure this shape prevents is the quiet one: a request that named
        # nine rules, resolved none of them, and answered anyway from general
        # retrieval — which reads on screen exactly like an answer about the
        # policy. `covered_rule_count` of zero says so instead.
        record_source = RECORDS_FROM_PUBLISHED_VERSION if policy_version_id else RECORDS_FROM_DRAFT_ROWS
        covered = 0
        try:
            payloads, record_source = await _policy_rule_payloads(
                session,
                policy_set_key,
                list(focus_rule_ids),
                policy_version_id=policy_version_id,
            )
            if payloads:
                block, covered = _policy_context_block(payloads)
                context_blocks.append(block)
        except Exception as exc:  # noqa: BLE001 - chat should still answer without the policy block
            logger.warning("failed to load policy rules during ask(): %s", exc)
        grounding = {
            "rule_count": len(focus_rule_ids),
            "covered_rule_count": covered,
            "covers_every_rule": covered == len(focus_rule_ids),
            "record_source": record_source,
        }

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
                    # `ensure_ascii=False` for the reason given on
                    # `_policy_context_block`: escaped, a non-Latin clause reaches
                    # the model as `\u0627\u0644…` rather than as its characters,
                    # and a model asked to copy a fact character-for-character
                    # would copy the escapes into the answer.
                    f"{json.dumps(focus_candidate.payload_json, indent=2, default=str, ensure_ascii=False)}"
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
                # The version the reader is looking at, when they named one, and
                # the active one otherwise. A reader on a superseded version
                # asking what else the policy says must be told about that
                # version's other rules; listing the active version's under the
                # heading "currently-approved" beside a sealed record would put
                # two versions in one answer with nothing marking the seam.
                active = None
                if policy_version_id:
                    try:
                        named = await version_repo.get_by_id(uuid.UUID(policy_version_id))
                    except (ValueError, AttributeError, TypeError):
                        named = None
                    if named is not None and named.policy_set_id == policy_set.id:
                        active = named
                else:
                    active = await version_repo.get_active_version(policy_set.id)
                if active is not None:
                    package = approved_policy_version_to_package(active)
                    rule_lines = [
                        f"- [{r.rule_id}] ({r.rule_type.value}, {r.effect.type.value}) {r.title}: {r.description}"
                        for r in package.rules
                    ]
                    if rule_lines:
                        # Named by which version holds them rather than by
                        # whether that version is the live one: this block is
                        # pinned to the version the reader named when they named
                        # one, and calling a superseded version's rules
                        # "currently-approved" would be a claim about the policy
                        # set that the block does not support.
                        standing = "currently approved" if active.is_active else "superseded"
                        context_blocks.append(
                            f"Rules of policy set '{policy_set_key}' version {active.version_number} "
                            f"({standing}):\n" + "\n".join(rule_lines)
                        )
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to load approved rules context during ask(): %s", exc)

    context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no matching context found)"
    system_prompt = _SYSTEM_PROMPT
    if answer_language and _LANGUAGE_TAG.fullmatch(answer_language):
        system_prompt += _answer_language_directive(answer_language)
    messages = [{"role": "system", "content": system_prompt}]
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
        # quirk documented on AzureOpenAIClient.chat(). A policy-wide question
        # has more to quote from and gets more room: a reply cut off mid-JSON
        # parses as reflection-only, which looks like a thin answer rather than
        # a truncated one.
        max_tokens=2400 if grounding is not None else 1600,
    )
    groups, reflection = _parse_structured_answer(raw)
    reply: dict = {"groups": groups, "reflection": reflection, "sources": sources}
    if grounding is not None:
        reply["grounding"] = grounding
    return reply


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
