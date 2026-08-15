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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from policy_platform.contracts.passage import PolicyPassage
from policy_platform.contracts.provision_grouping import Provision, raw_groups
from policy_platform.contracts.reading_plan import DividedProvision, render_table_columns
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.contracts.policy import (
    AmbiguityStatus,
    CandidateRelationship,
    CanonicalRule,
)
from policy_platform.domain.models import (
    CandidateRule,
    Clause,
    DocumentProvision,
    DocumentVersion,
    ExtractionRun,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.extraction import extraction_progress
from policy_platform.infrastructure.extraction.provision_linking import (
    provision_for,
    provision_index as build_provision_index,
    provision_row,
)
from policy_platform.infrastructure.projection import rule_delta
from policy_platform.infrastructure.extraction.formulation_mapping import (
    SKIP_BATCH_UNREAD,
    SKIP_DISCARDED,
    SKIP_NOT_EXTRACTED,
    formulation_to_candidate_rules,
    record_skip,
    skip_breaks_coverage,
    skip_counts,
)
from policy_platform.infrastructure.ingestion import source_structure
from policy_platform.infrastructure.ingestion.canonical_rebuild import (
    canonical_from_clauses,
)
from policy_platform.infrastructure.extraction.continuation_adjudicator import (
    ClauseWindow,
    discover_continuations,
)
from policy_platform.infrastructure.quality.policy_faithfulness import validate_rules
from policy_platform.infrastructure.correlation.relationship_discovery import (
    RuleAnchor,
    discover_enumeration_relationships,
    discover_referent_relationships,
    discover_semantic_role_relationships,
    discover_split_decision_relationships,
    discover_structural_relationships,
    stems_needing_adjudication,
)
from policy_platform.infrastructure.extraction.evaluability import dangling_referents
from policy_platform.infrastructure.extraction.passage_extractor import (
    PASSAGE_PROMPT_VERSION,
    PassageExtractionError,
    PassageExtractorAgent,
    clean_clause_ref,
    span_clause_refs,
)
from policy_platform.infrastructure.extraction.policy_formulator import (
    FORMULATOR_PROMPT_VERSION,
    PolicyFormulationError,
    PolicyFormulatorAgent,
)
from policy_platform.infrastructure.persistence.repositories import (
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


def _provisions(clauses: list[Clause], document_id: str) -> list[list[Clause]] | None:
    """Group clauses into provisions, or None if the structure will not support it.

    Returns runs in document order. Measured on every document stored here, a
    provision key never reappears after a different one has intervened, so a run
    is always contiguous and grouping never reorders a clause.

    Returns None rather than raising when the graph cannot be built. Batching is
    a resource decision, and a document whose structure defeats it is still
    worth extracting by the plain character walk -- failing the whole run
    because the *grouping* failed would trade a better reading for no reading.

    The rebuild is a seam that already existed: it reconstructs the canonical
    document from exactly the clause list this module already loads, which is
    what keeps this a small change rather than a second parallel parse.

    The grouping itself now lives in `contracts.provision_grouping`, because the
    same computation also decides which rules a reviewer sees as one policy. Two
    copies of it would have drifted the moment either question changed. This
    caller takes the *raw* runs -- keyed by heading element id, never merged --
    so where a batch breaks is exactly what it has always been.
    """

    try:
        document = canonical_from_clauses(document_id, clauses)
        graph = build_structural_graph(document)
    except Exception:  # noqa: BLE001 - see docstring; degrade, never fail the run
        logger.warning("provision grouping unavailable; batching by character count", exc_info=True)
        return None

    by_element = {clause.sequence: clause for clause in clauses}
    order_of = {
        element.element_id: element.logical_order for element in document.elements
    }
    runs: list[list[Clause]] = []
    for group in raw_groups(document, graph):
        run = [
            by_element[order_of[element_id]]
            for element_id in group.element_ids
            if element_id in order_of and order_of[element_id] in by_element
        ]
        if len(run) != len(group.element_ids):
            return None
        runs.append(run)
    return runs



def _rendered_size(clause: Clause) -> int:
    """What one clause costs in a batch, including anything rendered around it.

    The flat allowance covers the addressing marker and the section line. The
    column marker is added on top rather than folded into it, because it is
    present on table rows only: charging every clause for a line most of them
    never carry would shrink batches for no reason, and charging none of them
    for it would let a table-heavy batch overrun the window it was packed to
    fit.
    """

    return len(clause.text) + 40 + len(_column_marker(clause))


def _column_marker(clause: Clause) -> str:
    """The column-names line for a table row, or "" for anything else."""

    return render_table_columns(clause.table_headers)


def _pack(run: list[Clause], budget: int) -> list[list[Clause]]:
    """Split one provision that does not fit, in document order."""

    pieces: list[list[Clause]] = [[]]
    used = 0
    for clause in run:
        size = _rendered_size(clause)
        if pieces[-1] and used + size > budget:
            pieces.append([])
            used = 0
        pieces[-1].append(clause)
        used += size
    return pieces


def _batch_clauses(
    clauses: list[Clause], document_id: str = ""
) -> tuple[list[list[Clause]], list[DividedProvision]]:
    """Pack clauses into batches that never split a provision.

    The batch is a processing unit: it exists because a context window is
    finite. It had also become a semantic one, because where it broke decided
    what the model read together -- and it broke on a running character count,
    which knows nothing about where a policy ends. A rule landed in one batch
    and the sentence qualifying it in the next, and the model could only read
    them as two unrelated statements.

    So the walk is the same, but the atom is now the provision rather than the
    clause. A provision is added whole or starts a new batch. Only a provision
    that cannot fit alone is divided, and every division is returned so the run
    can say it happened.

    Every clause lands in exactly one batch, in document order, headings
    included -- the grouping decides where batches *break*, never which clauses
    are sent.
    """

    runs = _provisions(clauses, document_id)
    if runs is None:
        runs = [[clause] for clause in clauses]

    batches: list[list[Clause]] = []
    divided: list[DividedProvision] = []
    current: list[Clause] = []
    current_len = 0

    for run in runs:
        run_len = sum(_rendered_size(c) for c in run)
        if run_len > _MAX_CHARS_PER_BATCH:
            if current:
                batches.append(current)
                current = []
                current_len = 0
            pieces = _pack(run, _MAX_CHARS_PER_BATCH)
            if len(pieces) > 1:
                # The run's own heading is its first clause when it has one, and
                # a heading carries no `section` of its own -- reading `section`
                # blindly labels every division with an empty path.
                head = run[0]
                label = head.text if head.element_type == "heading" else (head.section or "")
                divided.append(
                    DividedProvision(
                        heading_path=[label.strip()] if label.strip() else [],
                        element_ids=[c.clause_ref for c in run],
                        characters=run_len,
                        unit_count=len(pieces),
                    )
                )
            batches.extend(pieces)
            continue
        if current and current_len + run_len > _MAX_CHARS_PER_BATCH:
            batches.append(current)
            current = []
            current_len = 0
        current.extend(run)
        current_len += run_len

    if current:
        batches.append(current)
    return batches, divided


def _page_label(clauses: list[Clause]) -> str:
    """A `" · page 7"` / `" · pages 7–9"` suffix for the progress stage line.

    Clause pages are optional (a DOCX has no fixed pagination), so this returns
    an empty string rather than a misleading "page 0" when they are absent.
    """
    pages = sorted({c.page for c in clauses if c.page is not None})
    if not pages:
        return ""
    if len(pages) == 1 or pages[0] == pages[-1]:
        return f" · page {pages[0]}"
    return f" · pages {pages[0]}–{pages[-1]}"


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

    A row of a table also gets its table's column names, on their own line and
    for the same reason the section gets one: `"Engineering | Performance
    laptop, 16-inch | Included | USD 2,400"` is unreadable as policy without
    knowing the grid names role profiles, device classes, monitors and costs.
    The line names the columns and explicitly refuses to align them with the
    values, because that alignment is not recorded anywhere — see
    `reading_plan.table_column_names`. Rows from a table that stated no column
    labels get no line at all: absence is left absent rather than announced.
    """

    parts = []
    for c in clauses:
        header = f"[clause_ref={c.clause_ref}]"
        if c.section:
            header += f"\n(section: {c.section})"
        columns = _column_marker(c)
        if columns:
            header += f"\n{columns}"
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




async def _document_run_ids(
    session: AsyncSession, document_version_id: uuid.UUID, *, exclude_run_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every prior extraction run for the *document*, not just this version.

    A document is a container and its versions are variants of it. Re-uploading
    a revised contract creates a new `DocumentVersion` (they are unique on
    content hash), so scoping run history to one version would treat the second
    variant as a first-ever extraction and present all of its rules as new —
    exactly the situation a delta is supposed to eliminate. Walking up to the
    owning `SourceDocument` keeps the comparison across variants.
    """

    document_id = (
        await session.execute(
            select(DocumentVersion.document_id).where(DocumentVersion.id == document_version_id)
        )
    ).scalar_one_or_none()
    if document_id is None:
        return []

    return list(
        (
            await session.execute(
                select(ExtractionRun.id)
                .join(DocumentVersion, DocumentVersion.id == ExtractionRun.document_version_id)
                .where(
                    DocumentVersion.document_id == document_id,
                    ExtractionRun.id != exclude_run_id,
                )
            )
        )
        .scalars()
        .all()
    )


async def _load_baseline_candidates(
    session: AsyncSession,
    document_version_id: uuid.UUID,
    policy_set_id: uuid.UUID,
    *,
    exclude_run_id: uuid.UUID,
) -> list[CandidateRule]:
    """The previous generation of rules for this document, to compare against.

    "Previous generation" is the most recent prior run that actually produced
    rules — not simply the most recent run, because a run that failed or found
    nothing must not become a baseline of zero rules and make the whole document
    look brand new.

    Reviewed rules are included. They are the ones whose decisions are most
    worth carrying forward: a rule the reviewer already approved and that this
    run reproduces identically should not be asked about a second time.
    """

    prior_runs = await _document_run_ids(session, document_version_id, exclude_run_id=exclude_run_id)
    if not prior_runs:
        return []

    latest_run_id = (
        await session.execute(
            select(CandidateRule.extraction_run_id)
            .join(ExtractionRun, ExtractionRun.id == CandidateRule.extraction_run_id)
            .where(
                CandidateRule.extraction_run_id.in_(prior_runs),
                CandidateRule.policy_set_id == policy_set_id,
                # Only a run that finished is a trustworthy reference. A run that
                # failed or was interrupted holds however many rules it managed
                # to commit before it stopped, and comparing against that partial
                # set would report every rule it never reached as brand new —
                # the exact noise this is meant to remove.
                ExtractionRun.status == "completed",
            )
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run_id is None:
        return []

    return list(
        (
            await session.execute(
                select(CandidateRule).where(CandidateRule.extraction_run_id == latest_run_id)
            )
        )
        .scalars()
        .all()
    )


async def _supersede_prior_candidates(
    session: AsyncSession,
    document_version_id: uuid.UUID,
    *,
    exclude_run_id: uuid.UUID,
) -> int:
    """Retire machine output from earlier extractions of the same document.

    Extraction was previously append-only, so re-running it on a document — a
    retry after a crash, a rerun with a better prompt, or a user clicking
    Extract twice — silently doubled every rule. Duplicates are not a cosmetic
    problem here: `group_rules_for_comparison` would pair a rule with its own
    copy and the correlation agent would dutifully report them as DUPLICATE,
    burying real findings under noise the system created itself.

    This used to DELETE those rows. It no longer does, and that change is the
    foundation of delta extraction: you cannot compute what changed against a
    set you destroyed, you cannot tell a reviewer a rule is *no longer* being
    extracted if its only record is gone, and filtering the review queue by run
    is meaningless when only one run's rows ever survive. Superseded rows are
    marked, not removed, and every existing read that means "the current set"
    now says `superseded_at IS NULL` — which is what it already meant.

    Only rows still in `candidate` status are retired. A candidate a human has
    approved, rejected or annotated is that person's decision and part of the
    audit trail; a re-run is a machine action and must never bury it. An
    approved-but-unpublished rule in particular has to stay in the queue or the
    reviewer loses the ability to publish work they already accepted.

    `exclude_run_id` is the run currently writing. It is mandatory because this
    is called *after* that run's row exists and mid-way through its inserts, so
    an unfiltered "all prior runs for this document" would match the caller's
    own output and retire the rules it just wrote.

    Returns the number of rows retired.
    """

    prior_runs = await _document_run_ids(session, document_version_id, exclude_run_id=exclude_run_id)
    if not prior_runs:
        return 0

    result = await session.execute(
        update(CandidateRule)
        .where(
            CandidateRule.extraction_run_id.in_(prior_runs),
            CandidateRule.review_status == "candidate",
            CandidateRule.published_version_id.is_(None),
            CandidateRule.superseded_at.is_(None),
        )
        .values(superseded_at=datetime.now(UTC), superseded_by_run_id=exclude_run_id)
    )
    await session.flush()
    return int(result.rowcount or 0)


def _relationship_anchors(
    rules: list[CanonicalRule], clause_texts_by_id: dict[str, str] | None = None
) -> list[RuleAnchor]:
    """Describe drafted rules in the terms relationship discovery compares.

    Every field is read from what the rule already carries — its evidence, its
    scope, its canonical decomposition — so an anchor asserts nothing the
    extraction did not already record. Rules that failed to compile are
    included deliberately: a table row belongs to its table whether or not it
    became executable, and dropping them here is how orphaned rows appear.

    `clause_texts_by_id` supplies the clause's original text, which still
    carries the outline number the canonical decomposition strips ("3.2.1." is
    structure, not part of the rule's statement). Without it the enumeration
    tier is blind to numbering and every stem falls through to adjudication.
    """

    clause_texts_by_id = clause_texts_by_id or {}
    anchors: list[RuleAnchor] = []
    for order, rule in enumerate(rules):
        canonical = rule.formulation.canonical if rule.formulation else None
        policy_rule = canonical.rule if canonical else None
        # Section comes from evidence, not `rule.scope`. `scope` is the
        # targeting scope — jurisdictions, personas, processes — and carries no
        # document position at all; reading it here silently produced an empty
        # section path, so the hierarchy detector could never fire.
        section_path: list[str] = []
        for ev in rule.evidence:
            if ev.section and ev.section not in section_path:
                section_path.append(ev.section)
        # Outline number and enumeration promise are read from the clause's own
        # text, which keeps the numbering the canonical decomposition strips.
        clause_text = clause_texts_by_id.get(
            rule.evidence[0].clause_id if rule.evidence else "", ""
        )
        anchor_text = (canonical.source_text if canonical else "") or rule.description
        # The decomposition, and whatever of it points outside this record.
        # Both are read from what the rule already carries, so the anchor still
        # asserts nothing the extraction did not record.
        canonical_fields = (
            {
                name: value
                for name in type(policy_rule).model_fields
                if isinstance(value := getattr(policy_rule, name, None), str)
                or hasattr(value, "value")
            }
            if policy_rule is not None
            else {}
        )
        unresolved = [
            item.phrase for item in dangling_referents(policy_rule, anchor_text)
        ]
        anchors.append(
            RuleAnchor(
                rule_id=rule.rule_id,
                element_ids=[ev.clause_id for ev in rule.evidence if ev.clause_id],
                text=anchor_text,
                section_path=section_path,
                fact_paths=sorted({fact.path for fact in rule.required_facts}),
                actor=(policy_rule.subject if policy_rule else "") or "",
                action=(policy_rule.predicate if policy_rule else "") or "",
                rule_kind=(rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type)).lower(),
                order=order,
                outline_path=source_structure.outline_path(clause_text or anchor_text),
                promises_enumeration=source_structure.promises_enumeration(
                    clause_text or anchor_text
                ),
                canonical_fields=canonical_fields,
                unresolved_phrases=unresolved,
            )
        )
    return anchors


async def _classify_run_delta(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    document_version_id: uuid.UUID,
    policy_set_id: uuid.UUID,
) -> dict[str, int]:
    """Record how this run's rules differ from the previous generation.

    Runs once at the end of the run rather than per batch. Matching is
    one-to-one — each prior rule can be continued by exactly one new rule — and
    that constraint is only correct when the whole run is compared at once; a
    per-batch pass would let an early batch claim a prior rule that a later
    batch matched far better.

    Decisions carry forward on an exact match. If a reviewer approved a rule and
    this run produced the identical rule from the same passage, re-asking is
    pure friction, and the carried decision is annotated with the run that
    inherited it so the audit trail still shows where it came from.
    """

    current = list(
        (
            await session.execute(select(CandidateRule).where(CandidateRule.extraction_run_id == run_id))
        )
        .scalars()
        .all()
    )
    if not current:
        return {"new": 0, "changed": 0, "unchanged": 0, "baseline": 0, "removed": 0, "reworded": 0}

    baseline = await _load_baseline_candidates(
        session, document_version_id, policy_set_id, exclude_run_id=run_id
    )
    baseline_by_id = {str(row.id): row for row in baseline}

    result = rule_delta.diff_runs(
        [(str(row.id), row.payload_json or {}) for row in current],
        [(str(row.id), row.payload_json or {}) for row in baseline],
    )

    for row in current:
        match = result.matches[str(row.id)]
        identity = rule_delta.identify(row.payload_json or {})
        row.content_fingerprint = identity.content_fingerprint
        row.anchor_fingerprint = identity.anchor_fingerprint
        row.delta_status = match.delta_status
        row.reworded = match.reworded
        row.baseline_candidate_id = (
            uuid.UUID(match.baseline_key) if match.baseline_key is not None else None
        )

        prior = baseline_by_id.get(match.baseline_key or "")
        if match.delta_status != "unchanged" or prior is None:
            continue
        if prior.review_status in {"approved", "rejected"}:
            # The reviewer already decided this exact rule and the document has
            # not moved. Asking again is pure friction, so the decision follows
            # the rule forward — annotated, so the audit trail still shows that
            # a machine carried it rather than a human re-made it.
            row.review_status = prior.review_status
            row.reviewed_by = prior.reviewed_by
            row.reviewed_at = prior.reviewed_at
            carried = (
                f"Decision carried forward from {prior.id} — rule unchanged since the previous extraction."
            )
            row.review_notes = f"{prior.review_notes}\n\n{carried}" if prior.review_notes else carried
        elif prior.review_status == "published":
            # Deliberately NOT marked published: this row was never part of a
            # published version, and claiming otherwise would forge a link to a
            # version it does not belong to. It stays a candidate, but the note
            # tells the reviewer that approving it would duplicate a rule that is
            # already live.
            row.review_notes = (
                f"Identical to candidate {prior.id}, which is already published. "
                "Approving this again would duplicate a live rule."
            )

    await session.flush()
    return result.counts


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

    When omitted, the owning policy set's stored `trusted_config_json` is used.
    That default is what makes an executable extraction reproducible: the
    config is the *domain's* vocabulary, so it must apply to every document and
    every re-run in the set rather than having to be re-supplied by whichever
    caller happens to trigger extraction. An explicit argument still wins, so a
    caller can override for a one-off run; passing `{}` deliberately opts out
    and takes the empty-config path even when the set has one stored.

    `max_clauses` caps how many of the document's clauses (in document order)
    are sent to the agents this run. Intended for a small-batch validation
    pass — e.g. confirming a prompt change actually fixes the defects it was
    meant to fix — before committing to a full-document extraction, which is
    otherwise the only option and cannot be cheaply undone once hundreds of
    candidate rows exist. `None` (the default) processes every clause, exactly
    as before this parameter existed.

    Returns a summary dict: {extraction_run_id, created: [candidate ids],
    skipped: [{item, reason, kind, identity, occurrences}], coverage: {...},
    superseded, delta}.

    `skipped` mixes two unrelated events and `kind` is what tells them apart:
    `batch_unread` means content was never read and the document is not
    covered; `discarded` and `not_extracted` mean it was read and something was
    decided about it. `coverage` reports that split directly, because
    `status="completed"` says only that the run finished — never that it read
    the whole document.

    `skipped` holds one entry per declined *passage*, not per rejection event:
    the model can return the same sentence as two canonical policies and decline
    both, which is one passage the reviewer needs to look at. `occurrences`
    carries the event count so nothing is hidden. A passage declined for two
    different reasons stays two entries — those are two facts about it.

    Raises ValueError for not-found policy set/document/clauses (caller maps to HTTP 404/409).
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    # Fall back to the policy set's own fact model. `is None` rather than a
    # truthiness check on purpose: an explicit `{}` is a caller deliberately
    # requesting the empty-config path, which is a meaningful choice (it yields
    # honest non-executable projections) and must not be silently overridden by
    # the stored config.
    if trusted_config is None:
        trusted_config = policy_set.trusted_config_json or None

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
    run = await run_repo.create(
        document_version_id=document_version_id,
        deployment_name=settings.azure_openai_deployment,
        prompt_version=PROMPT_VERSION,
        parser_version=PARSER_VERSION,
    )
    # Superseding prior candidates is deferred until this run has rules to put
    # in their place (see the first-batch commit below). It used to happen here,
    # before a single model call — which meant a run where every batch failed
    # (expired credentials, a degraded endpoint, rate limiting) deleted the
    # previous run's output and replaced it with nothing. Those per-batch
    # failures are caught and recorded as skips, so the run still finished
    # "completed" and committed the delete. Re-running extraction could
    # therefore leave a reviewer with strictly less than they started with.
    superseded = 0
    superseded_done = False

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

    # Publish progress for the whole run up front. Totals are knowable here:
    # batching is deterministic and the clause list is already narrowed by
    # `max_clauses`, so the UI can show "batch 3 of 17" rather than an
    # open-ended spinner. See `extraction_progress` for why this is in-memory.
    batches, divided_provisions = _batch_clauses(clauses, str(document_version_id))
    if divided_provisions:
        logger.info(
            "%d provision(s) exceeded the batch budget and were read in pieces: %s",
            len(divided_provisions),
            "; ".join(
                f"{d.characters} chars over {d.unit_count} batches"
                for d in divided_provisions
            ),
        )
    progress_key = str(document_version_id)
    # Step 4a: which policy each clause belongs to, decided before any model
    # call and from the document alone. Separate from the batching above on
    # purpose — batching answers "what should the model read together", this
    # answers "what does a reviewer see as one policy", and merging a heading's
    # repeats is right for the second and wrong for the first.
    provision_index = build_provision_index(
        clauses, str(document_version_id), doc_version.content_hash or str(document_version_id)
    )
    provision_rows: dict[str, DocumentProvision] = {}
    clause_ref_by_id = {str(clause.id): clause.clause_ref for clause in clauses}
    all_pages = sorted({c.page for c in clauses if c.page is not None})
    extraction_progress.start(
        progress_key,
        total_clauses=len(clauses),
        total_batches=len(batches),
        total_pages=len(all_pages),
    )
    extraction_progress.update(progress_key, run_reference=run.reference)
    seen_pages: set[int] = set()

    try:
        for batch_index, batch in enumerate(batches, start=1):
            batch_ref = batch[0].clause_ref if batch else ""
            seen_pages.update(c.page for c in batch if c.page is not None)
            page_label = _page_label(batch)
            extraction_progress.update(
                progress_key,
                processed_batches=batch_index - 1,
                stage=f"Reading batch {batch_index} of {len(batches)}{page_label} — finding policy statements",
            )
            # Count the batch's clauses as processed here rather than at the end
            # of the body: several paths below `continue`, and a clause that was
            # sent to the agents has been processed regardless of whether it
            # yielded a rule.
            extraction_progress.advance(progress_key, clauses=len(batch), pages=len(seen_pages))

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
                record_skip(
                    skipped,
                    item=batch_ref,
                    reason=f"passage extractor failed for this batch: {exc}",
                    kind=SKIP_BATCH_UNREAD,
                    identity=f"batch:{batch_ref}",
                )
                extraction_progress.advance(progress_key, skipped=1)
                continue

            for bad in fabricated:
                # Identified by the clause it claimed to come from. Where it
                # named none there is nothing to be the same as, so it is left
                # unidentified and counted on its own rather than merged with
                # the other unattributed passages of this batch.
                record_skip(
                    skipped,
                    item=bad.source.clause_ref or batch_ref,
                    reason="passage discarded: not a verbatim substring of the source",
                    kind=SKIP_DISCARDED,
                    identity=(
                        f"clauses:{bad.source.clause_ref}" if bad.source.clause_ref else None
                    ),
                )
            extraction_progress.advance(progress_key, skipped=len(fabricated))

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
            extraction_progress.advance(progress_key, passages=len(passages))
            extraction_progress.update(
                progress_key,
                stage=(
                    f"Formulating rules from batch {batch_index} of {len(batches)}"
                    f"{page_label} — {len(passages)} policy statement(s) found"
                ),
            )
            try:
                formulation = await formulator.formulate(_render_passages(passages))
            except PolicyFormulationError as exc:
                record_skip(
                    skipped,
                    item=batch_ref,
                    reason=f"formulator agent failed for this batch: {exc}",
                    kind=SKIP_BATCH_UNREAD,
                    identity=f"batch:{batch_ref}",
                )
                extraction_progress.advance(progress_key, skipped=1)
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
                clause_texts_by_ref=clause_texts,
                source_note="; ".join(c.clause_ref for c in cited),
            )
            drafted.extend(rules)
            # Merged rather than extended: the ledger's "one entry per declined
            # passage" invariant belongs to the ledger, not to a single batch.
            # Extending would let the same passage appear twice if two batches
            # ever declined it, which is the defect this fixes reappearing at
            # the seam.
            for entry in batch_skipped:
                record_skip(
                    skipped,
                    item=entry["item"],
                    reason=entry["reason"],
                    kind=entry["kind"],
                    identity=entry.get("identity"),
                    occurrences=entry.get("occurrences", 1),
                )
            extraction_progress.advance(progress_key, drafted=len(rules), skipped=len(batch_skipped))

            # Persist and commit per batch rather than once at the end. These
            # runs are long (tens of model calls over tens of minutes), so an
            # all-or-nothing transaction would discard every completed batch on
            # a late failure and leave reviewers staring at an empty queue with
            # no way to tell progress from failure. Candidates are drafts under
            # review, not authoritative rules, so partial results are a valid
            # intermediate state.
            if rules and not superseded_done:
                # First real output of this run. Clear the previous run's
                # unreviewed candidates in the *same transaction* as this
                # batch's inserts, so the queue never contains both runs at once
                # and never loses the old set without gaining a new one.
                superseded = await _supersede_prior_candidates(
                    session, document_version_id, exclude_run_id=run.id
                )
                superseded_done = True
                extraction_progress.update(progress_key, superseded=superseded)
            for rule in rules:
                candidate = await candidate_repo.create(
                    policy_set_id=policy_set.id,
                    extraction_run_id=run.id,
                    rule_type=rule.rule_type.value,
                    payload_json=rule.model_dump(mode="json"),
                )
                # Step 13a: attach the rule to the policy its passage states, in
                # the same transaction as the insert, so a rule and its policy
                # link commit or roll back together. The provision row itself is
                # a fact about the document and is never superseded or deleted —
                # a run that fails after this point leaves it in place, and the
                # next run's upsert finds it unchanged.
                provision = provision_for(
                    rule.lineage.source_elements,
                    [
                        ref
                        for ref in (
                            clause_ref_by_id.get(str(reference.clause_id))
                            for reference in rule.evidence
                        )
                        if ref is not None
                    ],
                    provision_index,
                )
                if provision is not None:
                    row = await provision_row(
                        session,
                        provision_rows,
                        provision,
                        policy_set_id=policy_set.id,
                        document_version_id=document_version_id,
                    )
                    candidate.provision_id = row.id
                created_ids.append(str(candidate.id))
                persisted[rule.rule_id] = candidate
            await session.commit()
            # Published only after the commit succeeds: this counter is the
            # answer to "how many rules are in my review queue right now", and
            # a batch that drafts rules but fails to persist them must not
            # inflate it. It is deliberately distinct from `rules_drafted`.
            extraction_progress.update(progress_key, rules_committed=len(created_ids))

        extraction_progress.update(
            progress_key,
            processed_batches=len(batches),
            stage="Linking rule variations across the document…",
        )

        # Cross-batch linking: rules sharing a group_label (derived from a
        # shared DMN decision table, see formulation_mapping._group_labels) are
        # variations of one policy topic, so the review UI and Policies tab can
        # present them as a cluster. Re-run across ALL batches because a topic
        # can straddle the batch boundary, and per-batch links would then be
        # incomplete. Because rows are now committed per batch, this pass
        # rewrites the stored payloads instead of mutating objects pre-insert.
        #
        # This pass alone can only re-link rules a decision table already named,
        # so a rule that failed to compile carried no relationships at all —
        # precisely when a reviewer most needs to see what it depends on.
        # `relationship_discovery` supplies the rest from the document itself,
        # below, and its confirmed edges are merged in here.
        groups: dict[str, list[str]] = {}
        for rule in drafted:
            if rule.group_label:
                groups.setdefault(rule.group_label, []).append(rule.rule_id)

        # Relationships the source establishes: rows of one table, section
        # hierarchy, ordered steps, normative role, and the clauses that
        # complete a governing stem. Independent of whether either endpoint
        # compiled.
        #
        # Only `confirmed` edges reach `related_rule_ids`. Candidates — a role
        # edge whose target is positional rather than stated — are a proposal,
        # and writing a proposal into a field consumers read as established
        # fact is how a machine's guess ends up in the reviewer's record.
        confirmed_links: dict[str, list[str]] = {}
        candidate_links: dict[str, list[CandidateRelationship]] = {}
        unresolved_stems: list[str] = []
        try:
            clause_texts_by_id = {str(c.id): c.text for c in clauses}
            anchors = _relationship_anchors(drafted, clause_texts_by_id)
            edges = discover_structural_relationships(anchors)
            edges += discover_semantic_role_relationships(anchors)
            # Records cut out of one statement of one obligation, and records
            # cut away from wording they depend on. Both leave a fragment that
            # reads as a whole rule; the links are what let a reviewer see the
            # rest without the record having to quote text it never contained.
            edges += discover_split_decision_relationships(anchors)
            edges += discover_referent_relationships(anchors)
            # Governing stems and the clauses that complete them. Without this a
            # stem states an exhaustive limit with nothing to limit it to, and
            # every case is a rule that cannot say what it is a case of.
            enumeration_edges = discover_enumeration_relationships(anchors)
            edges += enumeration_edges
            # Stems whose extent the document does not state deterministically.
            # Reported rather than approximated: guessing where an unnumbered
            # promise ends is how an unrelated rule gets merged into a policy.
            unresolved_stems = [
                a.rule_id for a in stems_needing_adjudication(anchors, enumeration_edges)
            ]
            for edge in edges:
                if not edge.source_rule_id or not edge.target_rule_id:
                    continue
                if edge.state != "confirmed":
                    # Kept rather than dropped. A candidate must never enter
                    # `related_rule_ids` — that field states a relationship —
                    # but discarding it entirely reported a rule linked only by
                    # candidate evidence as isolated. On AD-103 that overstated
                    # isolation by 5 rules and lost 6 `definition_used_by`
                    # links, the very links a non-executable rule most needs:
                    # a definition has no facts to group by.
                    reason = ""
                    if edge.evidence is not None:
                        reason = getattr(edge.evidence, "detail", "") or getattr(
                            edge.evidence, "kind", ""
                        )
                    candidate_links.setdefault(edge.source_rule_id, []).append(
                        CandidateRelationship(
                            target_rule_id=edge.target_rule_id,
                            relationship_type=edge.relationship_type.value,
                            reason=str(reason),
                        )
                    )
                    continue
                confirmed_links.setdefault(edge.source_rule_id, []).append(edge.target_rule_id)
                confirmed_links.setdefault(edge.target_rule_id, []).append(edge.source_rule_id)
        except Exception:
            # Discovery is additive. A failure here must not lose a run's rules,
            # which are the expensive part; the rules simply keep the links the
            # decision tables gave them.
            logger.exception("relationship discovery failed for run %s", run.id)

        if unresolved_stems:
            logger.info(
                "run %s: %d governing stem(s) need continuation adjudication",
                run.id,
                len(unresolved_stems),
            )

        # Second pass: the model reviews what structure could not resolve.
        #
        # Runs after the deterministic tiers, over the clauses they left
        # unlinked, so it is asked only about material where numbering and
        # phrasing gave no answer — which keeps the cost proportional to the
        # difficulty of the document rather than its length.
        #
        # Its output is held to the same standard as everything else: the model
        # must quote the parent's own promise, the quote is checked verbatim
        # against the source, and only a verified quote produces a `confirmed`
        # edge eligible for `related_rule_ids`. An unverified one is recorded as
        # a candidate for a reviewer, never merged silently.
        if ai_client is not None and confirmed_links is not None:
            try:
                rule_by_clause = {
                    ev.clause_id: rule.rule_id
                    for rule in drafted
                    for ev in rule.evidence
                    if ev.clause_id
                }
                windows = [
                    ClauseWindow(
                        element_id=str(clause.element_id or clause.id),
                        rule_id=rule_by_clause[str(clause.id)],
                        text=clause.text or "",
                    )
                    for clause in clauses
                    if str(clause.id) in rule_by_clause
                ]
                linked_rule_ids = set(confirmed_links)
                resolved = {w.element_id for w in windows if w.rule_id in linked_rule_ids}
                adjudicated = await discover_continuations(
                    ai_client, settings, windows, resolved_element_ids=resolved
                )
                for edge in adjudicated:
                    if edge.state != "confirmed":
                        continue
                    if not edge.source_rule_id or not edge.target_rule_id:
                        continue
                    confirmed_links.setdefault(edge.source_rule_id, []).append(
                        edge.target_rule_id
                    )
                    confirmed_links.setdefault(edge.target_rule_id, []).append(
                        edge.source_rule_id
                    )
                if adjudicated:
                    logger.info(
                        "run %s: adjudicator proposed %d link(s), %d with a verified quote",
                        run.id,
                        len(adjudicated),
                        sum(1 for e in adjudicated if e.state == "confirmed"),
                    )
            except Exception:
                logger.exception("continuation adjudication failed for run %s", run.id)

        extraction_progress.advance(progress_key, linked=len(confirmed_links))

        for rule in drafted:
            related = list(rule.related_rule_ids)
            seen = set(related) | {rule.rule_id}
            if rule.group_label:
                for rid in groups[rule.group_label]:
                    if rid not in seen:
                        related.append(rid)
                        seen.add(rid)
            for rid in confirmed_links.get(rule.rule_id, []):
                if rid not in seen:
                    related.append(rid)
                    seen.add(rid)
            proposed = [
                edge
                for edge in candidate_links.get(rule.rule_id, [])
                # A candidate the confirmed graph already covers is noise.
                if edge.target_rule_id not in seen
            ]
            if related == rule.related_rule_ids and proposed == rule.candidate_relationships:
                continue
            rule.related_rule_ids = related
            rule.candidate_relationships = proposed
            candidate = persisted.get(rule.rule_id)
            if candidate is not None:
                candidate.payload_json = rule.model_dump(mode="json")

        # Second-pass validation: re-read every drafted rule against the source
        # it cites. Independent of the classification that produced it — the
        # chain from passage to effect is lossy at every step, and the result
        # always looks well-formed whether or not it survived intact.
        #
        # This is a check that the run produced something solid, and it is
        # reported as such. It deliberately does *not* mark rules for review.
        #
        # It used to: a blocking finding set `ambiguity_status` to
        # HUMAN_JUDGMENT_REQUIRED and a duplicate added a tag, so a check on the
        # extraction became a per-rule alarm in the reviewer's queue. That made
        # the interface argue with itself — a rule shown complete and correct
        # also carried a flag demanding attention — and it made the flag
        # meaningless, since it fired on most of the corpus. What the reader
        # asked for is the record the document supports; whether the extractor
        # is behaving is a question about the run, and belongs to the run.
        try:
            faithfulness = validate_rules(drafted)
            blocking = [f for f in faithfulness if f.severity == "blocking"]
            duplicates = [f for f in faithfulness if f.code == "duplicate_rule"]
            logger.info(
                "run %s: solidity check over %d rules — %d finding(s), %d blocking, %d duplicate",
                run.id,
                len(drafted),
                len(faithfulness),
                len(blocking),
                len(duplicates),
            )
            for finding in faithfulness:
                logger.info(
                    "  %s [%s] %s | source: %s",
                    finding.rule_id,
                    finding.code,
                    finding.message,
                    finding.source_quote[:80],
                )
        except Exception:
            # Validation is a check on the run, not part of producing it. A
            # failure here must not cost the rules that were extracted.
            logger.exception("faithfulness validation failed for run %s", run.id)

        # Delta last, after the linking pass has settled every payload. Related
        # rule ids are deliberately not part of a rule's fingerprint, but
        # classifying before linking would still mean fingerprinting a payload
        # the run had not finished writing.
        extraction_progress.update(progress_key, stage="Comparing against the previous extraction…")
        delta_counts = await _classify_run_delta(
            session,
            run_id=run.id,
            document_version_id=document_version_id,
            policy_set_id=policy_set.id,
        )
        extraction_progress.update(
            progress_key,
            delta_new=delta_counts.get("new", 0),
            delta_changed=delta_counts.get("changed", 0),
            delta_unchanged=delta_counts.get("unchanged", 0),
            delta_removed=delta_counts.get("removed", 0),
        )

        # `skipped` is the ledger every skip point appends to, and its entries
        # are not all the same kind of event. Only a batch that was never read
        # is a coverage shortfall; a sentence read and judged non-normative is a
        # recall fact, and counting it here announced a hole in a run that had
        # none. Deriving from the declared kind — rather than from a separate
        # flag each site has to remember to set — means a skip point added later
        # is counted whether or not its author thought about the run's status,
        # and `skip_breaks_coverage` treats an untagged skip as the alarming
        # case rather than the harmless one.
        unread = [s for s in skipped if skip_breaks_coverage(s)]
        await run_repo.mark_completed(run, coverage_complete=not unread, skipped=skipped)
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await run_repo.mark_failed(run, error_message=str(exc))
        await session.commit()
        extraction_progress.finish(
            progress_key, status="failed", stage="Extraction failed", error=str(exc)
        )
        raise

    await session.commit()
    # Report the delta, not the volume. "190 rules created" is technically true
    # on a re-run of an unchanged document and completely misleading: it reads
    # as 190 things to review when the answer is none. The headline is what
    # changed; the raw count stays available in the run record.
    changed_total = (
        delta_counts.get("new", 0) + delta_counts.get("changed", 0) + delta_counts.get("removed", 0)
    )
    if delta_counts.get("baseline", 0):
        summary = f"Done — {len(created_ids)} candidate rule(s) from {len(clauses)} clause(s). First extraction of this document."
    elif changed_total == 0:
        summary = f"Done — no changes. All {len(created_ids)} rule(s) match the previous extraction."
    else:
        parts = []
        if delta_counts.get("new"):
            parts.append(f"{delta_counts['new']} new")
        if delta_counts.get("changed"):
            parts.append(f"{delta_counts['changed']} changed")
        if delta_counts.get("removed"):
            parts.append(f"{delta_counts['removed']} no longer found")
        summary = f"Done — {', '.join(parts)} since the previous extraction."
    if skipped:
        # Every sentence built above describes the delta, and the delta is
        # computed only over what was actually read. Left alone, a partial
        # reading reports itself in the same words as a whole one — including
        # "no longer found", which reads as a statement about the document when
        # it is really a statement about how much of the document we reached.
        #
        # The two kinds are said separately because they ask the reviewer for
        # different things. An unread batch means the document was not covered
        # and the run should be repeated. A sentence read and not extracted
        # means coverage was complete and a judgement was made that the
        # reviewer may want to check. Reporting them in one number told a clean
        # run it had a hole in it, which is the fastest way to teach someone to
        # ignore the warning.
        unread_items = [s for s in skipped if skip_breaks_coverage(s)]
        read_but_dropped = [s for s in skipped if not skip_breaks_coverage(s)]
        notes = []
        if unread_items:
            notes.append(
                f"{len(unread_items)} batch(es) could not be read, so this run did not "
                "cover the whole document and should be repeated."
            )
        if read_but_dropped:
            notes.append(
                f"{len(read_but_dropped)} sentence(s) were read and not extracted; "
                "see the skip list to check that judgement."
            )
        summary = " ".join([summary, *notes])
    if divided_provisions:
        # Said outside the `skipped` block on purpose. A divided provision is
        # not a skip: nothing was missed, and the run needs no repeating. It is
        # the one thing this stage cannot do for the reader — a provision too
        # large for any single batch had to be read in pieces, so a rule in the
        # second piece was read without the sentence that qualifies it. That is
        # a property of the document meeting a finite context window rather than
        # a fault in the run, which is why it is reported and not counted as a
        # shortfall.
        summary = " ".join(
            [
                summary,
                f"{len(divided_provisions)} provision(s) were too long for one batch "
                "and were read in pieces; rules drawn from them may be missing "
                "context that sits in an adjacent piece.",
            ]
        )
    # The durable status on the run carries this distinction (see
    # ExtractionRunRepository.mark_completed). The in-flight progress record
    # cannot: its status is typed as "running" | "completed" | "failed" in
    # apps/web/src/api.ts, which belongs to another workstream, so widening it
    # here would emit a value the client does not know. The shortfall therefore
    # travels in `stage`, which is free text already shown to the reader.
    extraction_progress.finish(progress_key, status="completed", stage=summary)
    return {
        "extraction_run_id": str(run.id),
        "created": created_ids,
        "skipped": skipped,
        # Coverage as a fact, not as something a caller has to derive by
        # grepping reason strings. `status="completed"` answers "did the run
        # finish"; it has never answered "did the run read the document", and
        # reading it as though it did is what let a run that lost batches look
        # identical to one that lost nothing.
        "coverage": {
            # Counted in passages, not in rejection events. The ledger holds one
            # entry per declined passage (see `record_skip`), so a sentence the
            # model returned twice is one decline here — which is what is true of
            # the document. `occurrences` on the entry keeps the event count for
            # anyone diagnosing the model's output; `skip_counts` deliberately
            # does not sum it, because how many times something was rejected is
            # a fact about the run, not about the policy.
            "complete": not [s for s in skipped if skip_breaks_coverage(s)],
            **skip_counts(skipped),
        },
        "superseded": superseded,
        "delta": delta_counts,
    }
