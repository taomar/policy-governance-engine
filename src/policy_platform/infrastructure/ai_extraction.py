"""AI-assisted rule extraction: turns a document's extracted `Clause` rows
into draft `CandidateRule` rows a human still has to review and approve.

This module owns the *scan* half of a two-stage pipeline and delegates the
*formulate* half to `infrastructure.policy_formulator`:

    document -> clauses  (scan: this module + document ingestion)
             -> canonical + DMN JSON  (formulate: the policy formulator agent)
             -> CanonicalRule  (deterministic derivation, no model involved)

Design decisions (see docs/known-limitations.md for the full writeup):

1. This module no longer carries its own extraction prompt. Clause text is
   piped to the policy formulator agent, whose system prompt is the
   "ENTERPRISE POLICY EXTRACTION AND DECISION ENGINE" specification (OMG
   DMN 1.5 / FEEL). Separating scanning from formulating means the standard
   governing policy structure lives in one reviewable place, and can be
   re-versioned without touching document handling.
2. The agent returns *description*, never platform internals. Turning its
   output into a schema-valid `CanonicalRule` — identifiers, rule-type
   mapping, condition derivation — is done in plain Python by
   `infrastructure.formulation_mapping`, per the specification's own
   Section 82 ("deterministic application responsibilities").
3. A drafted rule only becomes `machine_executable` when the agent reported a
   DMN mapping status of `executable` (meaning every fact path came from a
   trusted fact model rather than invention) *and* the platform could fully
   parse the resulting FEEL. Otherwise the rule is emitted with a
   vacuously-true placeholder condition, `machine_executable=False` and
   `ambiguity_status=human_judgment_required`. AI accelerates drafting; it
   never bypasses review or the deterministic evaluation core.
4. Every candidate's `evidence` list is populated with real
   `EvidenceReference`s (document_version_id/source_hash/page/section/
   clause_id) pointing back at the source clause(s) it was grounded in, and
   `lineage` records the deployment/run/prompt version that produced it.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from policy_platform.contracts.passage import PolicyPassage
from policy_platform.contracts.policy import CanonicalRule
from policy_platform.domain.models import (
    CandidateRule,
    Clause,
    DocumentVersion,
    ExtractionRun,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.formulation_mapping import formulation_to_candidate_rules
from policy_platform.infrastructure.passage_extractor import (
    PASSAGE_PROMPT_VERSION,
    PassageExtractionError,
    PassageExtractorAgent,
    clean_clause_ref,
    span_clause_refs,
)
from policy_platform.infrastructure.policy_formulator import (
    FORMULATOR_PROMPT_VERSION,
    PolicyFormulationError,
    PolicyFormulatorAgent,
)
from policy_platform.infrastructure.repositories import (
    CandidateRuleRepository,
    ClauseRepository,
    ExtractionRunRepository,
    PolicySetRepository,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Recorded on every drafted rule's `lineage`. Tracks BOTH prompts, because a
#: rule is now the product of two agents in sequence: Stage 1 decides which
#: source text is policy-bearing, Stage 2 decides what it means. A change to
#: either can change the output, so either alone is an incomplete provenance
#: record.
PROMPT_VERSION = f"{PASSAGE_PROMPT_VERSION}+{FORMULATOR_PROMPT_VERSION}"
PARSER_VERSION = "formulation-mapping-v1"

#: Clause batch size, in characters. Sized so a batch plus the ~42k-character
#: formulator specification stays comfortably inside the model's context while
#: leaving room for the reasoning pass and the JSON reply. Deliberately small:
#: a measured 1,525-char batch of dense definitions yielded 13 canonical
#: policies plus 13 DMN decisions, so output volume — not input size — is the
#: binding constraint. Losing a whole batch to truncation costs far more than
#: the extra calls a smaller batch requires.
_MAX_CHARS_PER_BATCH = 4000


def _batch_clauses(clauses: list[Clause]) -> list[list[Clause]]:
    batches: list[list[Clause]] = []
    current: list[Clause] = []
    current_len = 0
    for clause in clauses:
        clause_len = len(clause.text) + 40
        if current and current_len + clause_len > _MAX_CHARS_PER_BATCH:
            batches.append(current)
            current = []
            current_len = 0
        current.append(clause)
        current_len += clause_len
    if current:
        batches.append(current)
    return batches


def _render_batch(clauses: list[Clause]) -> str:
    """Render clauses with an unambiguous addressing marker.

    The section label is deliberately on its own line rather than inside the
    marker. When it was rendered as `[clause_ref=p3-E000016 (Article 2)]`, the
    "identifier exactly as supplied" that the agent was told to echo back was
    genuinely ambiguous — the ref and the section were one undelimited string —
    and the agent returned the decorated form, which matched no clause. That
    was survivable while verbatim verification did all the work, but a span
    reference is only useful if it resolves, so the label must contain exactly
    one identifier and nothing else.
    """

    parts = []
    for c in clauses:
        header = f"[clause_ref={c.clause_ref}]"
        if c.section:
            header += f"\n(section: {c.section})"
        parts.append(f"{header}\n{c.text}")
    return "\n\n".join(parts)


def _render_passages(passages: list[PolicyPassage]) -> str:
    """Render Stage 1's verbatim passages as Stage 2's source text.

    Only the passage text is passed through. The clause markers are dropped
    here on purpose: Stage 1 has already decided *which* text is policy-bearing
    and recorded where each span came from, so re-supplying addressing labels
    would only give Stage 2 more non-policy strings to misread as content.
    """

    return "\n\n".join(p.text.strip() for p in passages if p.text.strip())




async def _supersede_prior_candidates(
    session: AsyncSession, document_version_id: uuid.UUID
) -> int:
    """Clear machine output from earlier extractions of the same document.

    Extraction was previously append-only, so re-running it on a document — a
    retry after a crash, a rerun with a better prompt, or a user clicking
    Extract twice — silently doubled every rule. Duplicates are not a cosmetic
    problem here: `group_rules_for_comparison` would pair a rule with its own
    copy and the correlation agent would dutifully report them as DUPLICATE,
    burying real findings under noise the system created itself.

    Only rows still in `candidate` status are removed. A candidate a human has
    approved, rejected or annotated is that person's decision and part of the
    audit trail; a re-run is a machine action and must never erase it. Those
    rows are left alone, which means a re-run after review can still produce a
    near-duplicate of a reviewed rule — that is the correct trade, because the
    alternative destroys evidence.

    Returns the number of rows removed.
    """

    prior_runs = (
        await session.execute(
            select(ExtractionRun.id).where(
                ExtractionRun.document_version_id == document_version_id
            )
        )
    ).scalars().all()
    if not prior_runs:
        return 0

    stale = (
        await session.execute(
            select(CandidateRule).where(
                CandidateRule.extraction_run_id.in_(prior_runs),
                CandidateRule.review_status == "candidate",
                CandidateRule.published_version_id.is_(None),
            )
        )
    ).scalars().all()
    if not stale:
        return 0

    stale_ids = [row.id for row in stale]
    # Nothing holds a foreign key to candidate_rules (evidence rows are written
    # against approved_rules at publish time, and a candidate's provenance lives
    # inside its own payload_json), so the delete needs no cascade.
    await session.execute(delete(CandidateRule).where(CandidateRule.id.in_(stale_ids)))
    await session.flush()
    return len(stale_ids)


async def extract_candidate_rules(
    session: AsyncSession,
    *,
    policy_set_key: str,
    document_version_id: uuid.UUID,
    trusted_config: dict[str, Any] | None = None,
    max_clauses: int | None = None,
) -> dict:
    """Run AI extraction over one document version's clauses for one policy set.

    `trusted_config` is the specification's Section 83 configuration
    (`fact_model`, `output_model`, `value_normalization`, …). It is the only
    sanctioned source of technical detail absent from the source text. Omitting
    it is valid: the agent then returns faithful canonical records with
    candidly non-executable DMN projections carrying requirement codes, rather
    than inventing fact paths to look complete.

    `max_clauses` caps how many of the document's clauses (in document order)
    are sent to the agents this run. Intended for a small-batch validation
    pass — e.g. confirming a prompt change actually fixes the defects it was
    meant to fix — before committing to a full-document extraction, which is
    otherwise the only option and cannot be cheaply undone once hundreds of
    candidate rows exist. `None` (the default) processes every clause, exactly
    as before this parameter existed.

    Returns a summary dict: {extraction_run_id, created: [candidate ids], skipped: [{item, reason}]}.
    Raises ValueError for not-found policy set/document/clauses (caller maps to HTTP 404/409).
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    doc_version_result = await session.execute(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.document))
        .where(DocumentVersion.id == document_version_id)
    )
    doc_version = doc_version_result.scalar_one_or_none()
    if doc_version is None:
        raise ValueError(f"document version '{document_version_id}' not found")

    # The agents are told the document's name so they can distinguish "this
    # document" from documents it cites. `DocumentVersion` stores only a
    # storage path (a UUID-prefixed filename), so the human title on the parent
    # `SourceDocument` is the right source; the stored filename is the fallback
    # for versions whose parent title is blank.
    document_name = (doc_version.document.title if doc_version.document else "") or Path(
        doc_version.storage_path
    ).name

    clause_repo = ClauseRepository(session)
    clauses = await clause_repo.list_by_document_version(document_version_id)
    if not clauses:
        raise ValueError(f"document version '{document_version_id}' has no extracted clauses")
    if max_clauses is not None:
        clauses = clauses[:max_clauses]
    clauses_by_ref = {c.clause_ref: c for c in clauses}

    run_repo = ExtractionRunRepository(session)
    superseded = await _supersede_prior_candidates(session, document_version_id)
    run = await run_repo.create(
        document_version_id=document_version_id,
        deployment_name=settings.azure_openai_deployment,
        prompt_version=PROMPT_VERSION,
        parser_version=PARSER_VERSION,
    )

    ai_client = AzureOpenAIClient(settings)
    candidate_repo = CandidateRuleRepository(session)
    passage_agent = PassageExtractorAgent(ai_client, settings)
    formulator = PolicyFormulatorAgent(ai_client, settings, trusted_config=trusted_config)

    drafted: list[CanonicalRule] = []
    skipped: list[dict] = []
    created_ids: list[str] = []
    #: rule_id -> persisted CandidateRule, so the cross-batch linking pass below
    #: can update rows that were already committed.
    persisted: dict[str, object] = {}

    try:
        for batch in _batch_clauses(clauses):
            batch_ref = batch[0].clause_ref if batch else ""

            clause_texts = {c.clause_ref: c.text for c in batch}
            clause_order = [c.clause_ref for c in batch]

            # Stage 1 (identify): decide which spans of this batch are actually
            # policy-bearing and copy them verbatim. Without this the formulator
            # sees every sentence in the document and, having no instruction to
            # reject anything, turns contents pages, translation conventions and
            # legislative amendment instructions into obligations.
            try:
                passages, fabricated = await passage_agent.extract(
                    _render_batch(batch),
                    document_id=str(document_version_id),
                    document_name=document_name,
                    # Hand the agent's own addressing table back to the extractor
                    # so a passage that points at a real clause but transcribes it
                    # imperfectly can be repaired by copying, rather than lost.
                    clause_texts=clause_texts,
                    clause_order=clause_order,
                )
            except PassageExtractionError as exc:
                skipped.append(
                    {"item": batch_ref, "reason": f"passage extractor failed for this batch: {exc}"}
                )
                continue

            for bad in fabricated:
                skipped.append(
                    {
                        "item": bad.source.clause_ref or batch_ref,
                        "reason": "passage discarded: not a verbatim substring of the source",
                    }
                )

            if not passages:
                # A batch of pure boilerplate legitimately yields nothing. This
                # is the desired outcome, not a failure, so it is not recorded
                # as a skip — it would otherwise bury real problems in noise.
                continue

            # Whole-batch evidence: the fallback used only when a specific rule
            # can't be matched back to the passage(s) it came from (see below).
            # Also drives `cited` for the human-facing note on that fallback
            # path.
            cited_refs = {clean_clause_ref(p.source.clause_ref) for p in passages}
            cited_refs |= {clean_clause_ref(p.source.end_clause_ref) for p in passages}
            cited_refs.discard(None)
            cited = [c for c in batch if c.clause_ref in cited_refs] or batch

            # Per-clause evidence lookup, keyed by ref, covering every clause in
            # the batch (not just `cited`) so a multi-clause passage span
            # resolves fully even when its middle clauses cited no passage
            # boundary directly.
            clause_evidence_by_ref = {
                c.clause_ref: {
                    "document_version_id": str(document_version_id),
                    "source_hash": doc_version.content_hash,
                    "page": c.page,
                    "section": c.section,
                    "clause_id": str(c.id),
                }
                for c in batch
            }

            # Per-passage clause spans: which clause(s) each individual Stage-1
            # passage actually came from. A batch commonly bundles passages
            # from several unrelated clauses (a document is walked in
            # fixed-size windows, not one topic at a time), so this is what
            # lets each rule below cite only the clause(s) it was actually
            # formulated from, instead of every clause anywhere in the batch.
            passage_clause_refs = [
                span_clause_refs(p.source, clause_texts, clause_order) or [] for p in passages
            ]

            # Stage 2 (formulate): the agent's job. Only the verbatim policy
            # text is piped to it. Extraction owns no prompt.
            try:
                formulation = await formulator.formulate(_render_passages(passages))
            except PolicyFormulationError as exc:
                skipped.append(
                    {
                        "item": batch_ref,
                        "reason": f"formulator agent failed for this batch: {exc}",
                    }
                )
                continue

            batch_evidence = [
                {
                    "document_version_id": str(document_version_id),
                    "source_hash": doc_version.content_hash,
                    "page": clause.page,
                    "section": clause.section,
                    "clause_id": str(clause.id),
                }
                for clause in cited
            ]
            rules, batch_skipped = formulation_to_candidate_rules(
                formulation,
                policy_set_id=str(policy_set.id),
                extraction_run_id=str(run.id),
                deployment_name=settings.azure_openai_deployment,
                prompt_version=PROMPT_VERSION,
                parser_version=PARSER_VERSION,
                evidence=batch_evidence,
                passages=passages,
                passage_clause_refs=passage_clause_refs,
                clause_evidence_by_ref=clause_evidence_by_ref,
                source_note="; ".join(c.clause_ref for c in cited),
            )
            drafted.extend(rules)
            skipped.extend(batch_skipped)

            # Persist and commit per batch rather than once at the end. These
            # runs are long (tens of model calls over tens of minutes), so an
            # all-or-nothing transaction would discard every completed batch on
            # a late failure and leave reviewers staring at an empty queue with
            # no way to tell progress from failure. Candidates are drafts under
            # review, not authoritative rules, so partial results are a valid
            # intermediate state.
            for rule in rules:
                candidate = await candidate_repo.create(
                    policy_set_id=policy_set.id,
                    extraction_run_id=run.id,
                    rule_type=rule.rule_type.value,
                    payload_json=rule.model_dump(mode="json"),
                )
                created_ids.append(str(candidate.id))
                persisted[rule.rule_id] = candidate
            await session.commit()

        # Cross-batch linking: rules sharing a group_label (derived from a
        # shared DMN decision table, see formulation_mapping._group_labels) are
        # variations of one policy topic, so the review UI and Policies tab can
        # present them as a cluster. Re-run across ALL batches because a topic
        # can straddle the batch boundary, and per-batch links would then be
        # incomplete. Because rows are now committed per batch, this pass
        # rewrites the stored payloads instead of mutating objects pre-insert.
        groups: dict[str, list[str]] = {}
        for rule in drafted:
            if rule.group_label:
                groups.setdefault(rule.group_label, []).append(rule.rule_id)
        for rule in drafted:
            if not rule.group_label:
                continue
            related = [rid for rid in groups[rule.group_label] if rid != rule.rule_id]
            if related == rule.related_rule_ids:
                continue
            rule.related_rule_ids = related
            candidate = persisted.get(rule.rule_id)
            if candidate is not None:
                candidate.payload_json = rule.model_dump(mode="json")

        await run_repo.mark_completed(run)
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await run_repo.mark_failed(run, error_message=str(exc))
        await session.commit()
        raise

    await session.commit()
    return {
        "extraction_run_id": str(run.id),
        "created": created_ids,
        "skipped": skipped,
        "superseded": superseded,
    }
