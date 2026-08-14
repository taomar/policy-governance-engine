"""SQLAlchemy ORM entities (Section 23 subset — see docs/data-model.md).

Design notes:
- Approved, versioned artifacts (`approved_policy_versions`, `approved_rules`)
  are immutable once created (Rule 5.3): the repository layer only inserts new
  rows, it never issues UPDATE statements against these tables' substantive
  columns.
- Structurally complex fields that mirror the canonical contracts
  (`policy_platform.contracts`) — condition trees, exceptions, lineage — are
  stored as JSONB alongside relational metadata used for querying/lifecycle.
  This keeps the relational schema focused on what SQL needs to filter/join on
  (ids, status, dates, authority rank) while the JSONB payload is the
  source of truth the evaluator reconstructs into `ApprovedPolicyPackage`.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from policy_platform.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PolicySet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named collection of policies for one business domain (e.g. 'expense-policy')."""

    __tablename__ = "policy_sets"

    key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    # Coarse business-domain classification (HR, Finance, IT, Legal, ...) used to
    # organize the Projects list and seed category-appropriate templates; a free
    # string rather than a DB enum so new domains never require a migration.
    category: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    tags_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Periodic review / recertification (ISO 37301 §9.3, ISO 27001) — ADR-0009.
    # `review_due_date` is set by a Policy Manager (directly, or via `.../review`
    # bumping it to a next cycle); "overdue" is computed at API-response time
    # (today > review_due_date), the same pattern already used for
    # `PolicyException.is_expired`, since this codebase has no background
    # scheduler to flip a stored status. `last_reviewed_at` is a pure audit
    # trail of when a human last attested the policy set was reviewed.
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Ownership / RACI metadata (ISO 37301, standard GRC practice) — ADR-0013.
    # `owner` above is deliberately kept as-is (the owning department/team,
    # e.g. "hr-team"); these fields add the *individual*-level accountability
    # a RACI model requires without overloading that existing field's meaning:
    #   - accountable_owner: the single named person/role ultimately
    #     answerable for this policy set (RACI "A").
    #   - delegate_approver: backup who can approve on the accountable
    #     owner's behalf (e.g. while they are out); distinct from the
    #     per-rule/version `approved_by` audit field, which just records who
    #     actually clicked approve.
    #   - escalation_contact: who overdue reviews/exceptions should be
    #     routed to if the accountable owner is unresponsive.
    #   - consulted_parties_json / informed_parties_json: free-form lists of
    #     stakeholders (RACI "C" / "I") — subject-matter experts consulted
    #     before a change, and parties merely informed once one lands.
    # All five are optional free text/lists (no new workflow/routing engine
    # exists yet to *use* escalation_contact automatically — see
    # docs/known-limitations.md); they are persisted metadata a human reads.
    accountable_owner: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    delegate_approver: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    escalation_contact: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    consulted_parties_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    informed_parties_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # The specification's Section 83 trusted configuration (`fact_model`,
    # `output_model`, `value_normalization`, ...) for this policy set.
    #
    # This is the *only* sanctioned source of technical detail that is not
    # present in the source text. Without it the formulator agent must not
    # invent FEEL fact paths and instead returns `enrichment_required` with
    # `FACT_MODEL_REQUIRED`, which makes every rule it produces
    # `machine_executable=False`. Non-executable rules are then skipped by
    # `evaluator.engine`, which in turn means no rule can contribute to an
    # aggregate limit and every policy test evaluates to NOT_APPLICABLE.
    #
    # The config lives on the policy set rather than on a single extraction
    # request because it is the *domain's* vocabulary: the same terms recur
    # across every document and every re-run in the set, and a reviewer needs
    # to see the mapping that made a rule executable. Previously it could only
    # be supplied per-request, and no caller ever did, so every extraction in
    # this platform's history took the empty-config path.
    trusted_config_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    approved_versions: Mapped[list["ApprovedPolicyVersion"]] = relationship(
        back_populates="policy_set", order_by="ApprovedPolicyVersion.created_at"
    )
    documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="policy_set", order_by="SourceDocument.created_at"
    )
    aggregate_limits: Mapped[list["PolicyAggregateLimit"]] = relationship(
        back_populates="policy_set", order_by="PolicyAggregateLimit.aggregate_key"
    )


class PolicyAggregateLimit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mutable draft definition of a cross-rule aggregate limit.

    Structural configuration (which rules contribute, how they combine, the
    cap), not prose subject to per-candidate human review — so a Policy
    Manager edits these directly via CRUD, the same way `PolicySet.tags_json`
    is edited directly. Snapshotted into `ApprovedAggregateLimit` at publish
    time.
    """

    __tablename__ = "policy_aggregate_limits"
    __table_args__ = (
        UniqueConstraint("policy_set_id", "aggregate_key", name="uq_policy_aggregate_limits_set_key"),
    )

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False)
    aggregate_key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    contributing_rules_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    aggregator: Mapped[str] = mapped_column(String(20), default="SUM", nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str | None] = mapped_column(String(50), nullable=True)

    policy_set: Mapped["PolicySet"] = relationship(back_populates="aggregate_limits")


class PolicyAuthority(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authority level + owner + rank used for deterministic precedence (Section 15.4)."""

    __tablename__ = "policy_authorities"
    __table_args__ = (UniqueConstraint("level", "owner", name="uq_policy_authorities_level_owner"),)

    level: Mapped[str] = mapped_column(String(100), nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)


class SourceDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A registered source document (metadata, ownership).

    `policy_set_id` is nullable: documents can be uploaded directly into a
    project (the common path) or uploaded unassigned via the global Document
    Inbox and filed into a project afterwards. This is what lets a document
    belong to a "project" end-to-end without breaking documents that predate
    this relationship.
    """

    __tablename__ = "source_documents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_system: Mapped[str] = mapped_column(String(200), default="manual_upload", nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    policy_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_sets.id"), nullable=True, index=True
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", order_by="DocumentVersion.created_at")
    policy_set: Mapped["PolicySet | None"] = relationship(back_populates="documents")


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An immutable version of a source document (hash, storage pointer)."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "content_hash", name="uq_document_versions_doc_hash"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), default="application/octet-stream", nullable=False)

    document: Mapped["SourceDocument"] = relationship(back_populates="versions")
    clauses: Mapped[list["Clause"]] = relationship(back_populates="document_version")


class Clause(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A stable clause within a document version."""

    __tablename__ = "clauses"

    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    clause_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    section: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Explicit position within the document, 0-based, set at extraction time from the
    # already-in-order Python list `extract_clauses()` returns. Deliberately NOT inferred
    # from `created_at`: bulk_create() inserts every clause for a document in one flush,
    # and depending on OS clock resolution, many rows can share an identical timestamp —
    # `created_at` is not a reliable total order. `sequence` is the only field a "read this
    # document from top to bottom" view (or anything else needing true original order) may
    # sort by.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Canonical-document provenance (see infrastructure/ingestion/document_ingestion.py).
    # `element_id` is the stable identity of this clause inside its document,
    # and `source_fragments` records the exact page + character offsets it was
    # built from — one entry per page, so a clause reconstructed across a page
    # break still resolves. Spec section 25: an extraction is identified by its
    # source position, not by its text, because the same sentence can
    # legitimately appear more than once in a document.
    element_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    element_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_fragments: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    document_version: Mapped["DocumentVersion"] = relationship(back_populates="clauses")


class ExtractionRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Record of an extraction attempt (fingerprint, status) — persisted for future MAF use."""

    __tablename__ = "extraction_runs"

    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    deployment_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    skipped_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    """What this run passed over: [{item, reason, kind}].

    Kept because a coverage review asks what was *not* extracted, and that
    question had no answer once the extraction response was gone. `kind`
    separates material never read from material read and declined; the two are
    different facts about the document and only the first is a coverage gap.

    NULL means no record was kept, which is weaker than an empty list. An empty
    list asserts the run skipped nothing.
    """

    candidate_rules: Mapped[list["CandidateRule"]] = relationship(
        back_populates="extraction_run",
        foreign_keys="CandidateRule.extraction_run_id",
    )

    @property
    def reference(self) -> str | None:
        """Short, stable, human-quotable reference for this run.

        A run is the unit a reviewer reasons about — "these 44 rules came from
        that run", "re-run and compare". A raw UUID is unusable for that in
        conversation or a ticket, so this derives a compact form from it.
        Deliberately derived rather than stored: it needs no column, no
        migration and no sequence, and it round-trips back to the row because
        the UUID prefix is preserved verbatim.

        Returns None before the row has an id. A reference is a promise that
        the run can be looked up; emitting "RUN-NONE" for an unflushed object
        would hand a reviewer a citation that resolves to nothing.
        """
        if self.id is None:
            return None
        return f"RUN-{str(self.id)[:8].upper()}"


class CandidateRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A non-authoritative candidate rule produced by extraction.

    Schema present; population deferred until the MAF extraction workflow
    (ADR-0004) is implemented in a later phase.
    """

    __tablename__ = "candidate_rules"

    extraction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_runs.id"), nullable=False)
    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    review_status: Mapped[str] = mapped_column(String(50), default="candidate", nullable=False)

    # Review-audit trail (Section 5/human-review requirements). Mutable in
    # place, unlike approved_rules — a candidate is explicitly not yet
    # authoritative, so tracking who reviewed it and when is bookkeeping,
    # not a violation of Rule 5.3 immutability.
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approved_policy_versions.id"), nullable=True
    )

    extraction_run: Mapped["ExtractionRun"] = relationship(
        back_populates="candidate_rules",
        foreign_keys=[extraction_run_id],
    )

    # --- Cross-run identity (Milestone 51) -------------------------------
    # Re-extracting a document must show only what changed. Neither `rule_id`
    # (a fresh random per rule) nor the prose (regenerated every run) is stable
    # enough to answer "have we seen this before", so identity is derived and
    # stored here at insert time. Stored rather than computed on read because
    # the comparison is against runs that may be months old, and recomputing it
    # would silently re-interpret history if the fingerprint definition ever
    # changes.
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    anchor_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: 'baseline' (first run of this document), 'new', 'changed', 'unchanged'.
    delta_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    #: The rule in the previous run that this one continues, when matched.
    baseline_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_rules.id"), nullable=True
    )
    #: Semantics identical to the baseline but the model reworded it. Not a
    #: change, but a reviewer comparing text side by side will notice, so it is
    #: recorded rather than silently discarded.
    reworded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Soft supersession ------------------------------------------------
    # A later run of the same document replaces this row's *currency*, not its
    # existence. Deleting superseded candidates (the previous behaviour) made
    # three things impossible: computing a delta against the prior run, telling
    # a reviewer that a rule is no longer being extracted, and filtering the
    # review queue by run. Consumers that want "the current set" filter on
    # `superseded_at IS NULL`, which is what every existing read already means.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=True
    )


class CorrelationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One cross-rule correlation analysis over a policy set.

    Kept as a run rather than a single mutable result set because findings are
    only true of the rules that existed when the analysis ran. Overwriting the
    previous result would make a finding look current when the rule it accuses
    may since have been rewritten, and a reviewer cannot tell a stale
    contradiction from a live one.
    """

    __tablename__ = "correlation_runs"

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    deployment_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rules_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    groups_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Rules never examined by this run, for any reason. Recorded because
    #: Section 86 grouping trades completeness for tractability, and a coverage
    #: figure the reviewer cannot see is a coverage figure they will assume is
    #: 100%. This is the total; `rules_budget_skipped` says how much of it was
    #: the group budget rather than the rule genuinely standing alone, which are
    #: very different facts for a reviewer deciding whether to trust the result.
    rules_uncompared: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: The subset of `rules_uncompared` that *could* have been compared — the
    #: rule shared a usable signal with another rule — but whose groups fell
    #: outside the group budget. A non-zero value means the analysis was
    #: truncated and re-running with a larger budget would examine more.
    #: Nullable so runs recorded before this was tracked read as "unknown"
    #: rather than falsely claiming zero truncation.
    rules_budget_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: Total groups this corpus yields, against which `groups_analyzed` is the
    #: portion the budget allowed. Recorded so a truncated run can say how much
    #: it left behind, not merely that it left something: without it an operator
    #: told their run was truncated has to guess a larger budget and re-run
    #: blind. Nullable for runs recorded before this was tracked.
    groups_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings: Mapped[list["CorrelationFindingRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CorrelationFindingRow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One relationship the correlation agent found between rules."""

    __tablename__ = "correlation_findings"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("correlation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    analysis_status: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Business rule_ids, not candidate row ids: a finding is about the rule, and
    #: the rule outlives the candidate row it was drafted in.
    rule_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    #: Reviewer disposition. A finding is a question put to a human, so it needs
    #: somewhere for the human's answer to live; without it the same
    #: contradiction is re-surfaced after every run and reviewers learn to
    #: ignore the list.
    disposition: Mapped[str] = mapped_column(String(30), default="open", nullable=False)
    disposition_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    disposition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disposition_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["CorrelationRun"] = relationship(back_populates="findings")


class ApprovedPolicyVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An immutable, approved, versioned policy package — the unit the evaluator consumes.

    Rows in this table are never updated in place after creation (Rule 5.3);
    a new approved change is always a new row with an incremented
    `version_number`.
    """

    __tablename__ = "approved_policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_set_id", "version_number", name="uq_approved_policy_versions_set_version"),
    )

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(200), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    policy_set: Mapped["PolicySet"] = relationship(back_populates="approved_versions")
    rules: Mapped[list["ApprovedRule"]] = relationship(back_populates="policy_version", order_by="ApprovedRule.rule_id")
    aggregate_limits: Mapped[list["ApprovedAggregateLimit"]] = relationship(
        back_populates="policy_version", order_by="ApprovedAggregateLimit.aggregate_key"
    )


class ApprovedAggregateLimit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable snapshot of an aggregate limit as of one published version.

    Aggregate limits (e.g. "combined family-care leave capped at 70
    days/year across rules R1+R2") are structural policy-set configuration,
    not per-candidate prose subject to review — so unlike `ApprovedRule` they
    have no review workflow of their own. At publish time the current full
    set of `PolicyAggregateLimit` draft rows for the policy set is snapshotted
    verbatim into this table (Rule 5.3: this table itself is insert-only).
    """

    __tablename__ = "approved_aggregate_limits"
    __table_args__ = (
        UniqueConstraint(
            "policy_version_id", "aggregate_key", name="uq_approved_aggregate_limits_version_key"
        ),
    )

    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approved_policy_versions.id"), nullable=False
    )
    aggregate_key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # List of {"rule_id": str, "amount_fact": str} — the contributing rules and
    # which fact on each supplies the amount to sum (mirrors the JSONB-list
    # convention used for `related_rule_ids_json` elsewhere in this module).
    contributing_rules_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    aggregator: Mapped[str] = mapped_column(String(20), default="SUM", nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str | None] = mapped_column(String(50), nullable=True)

    policy_version: Mapped["ApprovedPolicyVersion"] = relationship(back_populates="aggregate_limits")


class ApprovedRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single approved, versioned rule belonging to an `ApprovedPolicyVersion`.

    Immutable once created (Rule 5.3): a change to a rule creates a new
    `ApprovedRule` row (new `revision`) under a new `ApprovedPolicyVersion`,
    never an UPDATE to an existing row's substantive columns.
    """

    __tablename__ = "approved_rules"
    __table_args__ = (
        UniqueConstraint("policy_version_id", "rule_id", "revision", name="uq_approved_rules_version_rule_revision"),
    )

    policy_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approved_policy_versions.id"), nullable=False)
    authority_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_authorities.id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    machine_executable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ambiguity_status: Mapped[str] = mapped_column(String(50), default="none", nullable=False)
    review_status: Mapped[str] = mapped_column(String(50), default="approved", nullable=False)
    # Business-domain classification and free-form labels, set by extraction or
    # a reviewer, used to filter/organize rules across a project independent of
    # rule_type (which describes evaluator behavior, not business meaning).
    category: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    tags_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Groups together rules that are variations/scenarios of the same underlying
    # policy topic (e.g. "Parental & Family Leave" spanning maternity, paternity
    # and sick-family-member rules) so the UI can present them as one cluster
    # instead of unrelated flat rows.
    group_label: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    related_rule_ids_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Section 15.4 precedence dimensions (ADR-0008). Added to the canonical
    # contract and manual-authoring/AI-extraction UI before these columns
    # existed here, which silently dropped both values at publish time — see
    # ADR-0009's "related discovery" section. Backfilled via migration
    # c9a1d4e0f2b3 with safe defaults so existing rows are unaffected.
    is_explicit_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supersedes_rule_ids_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Canonical contract payload (Section 14.1 condition tree, scope, effect,
    # required facts, lineage) stored verbatim as JSONB. This JSON is what
    # gets deserialized into `policy_platform.contracts.policy.CanonicalRule`
    # for the evaluator; the relational columns above exist for querying and
    # lifecycle/audit purposes.
    scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    condition_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effect_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    required_facts_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    lineage_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # XACML Obligations/Advice gap (ADR-0011): list of {"advice_id": str,
    # "text": str} — non-blocking supplementary guidance attached to this
    # rule's decision, distinct from `effect_json` (the mandatory
    # Obligation-equivalent action). See `contracts.policy.Advice`.
    advice_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # The policy-formulator agent's record (canonical decomposition + DMN
    # projection) for this rule, carried verbatim from the candidate row. The
    # columns above are a *lossy* executable projection of it, so the contract
    # (`CanonicalRule.formulation`) requires it be retained rather than
    # regenerated. Omitting this column silently destroyed the record at
    # publish time — the same defect ADR-0009 records for the precedence
    # fields; see migration e4c7a2b8d190. Nullable because it is genuinely
    # absent for hand-authored rules and rules drafted before the agent.
    formulation_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    policy_version: Mapped["ApprovedPolicyVersion"] = relationship(back_populates="rules")
    authority: Mapped["PolicyAuthority"] = relationship()
    exceptions: Mapped[list["RuleException"]] = relationship(back_populates="rule")
    evidence: Mapped[list["EvidenceReference"]] = relationship(back_populates="rule")


class RuleException(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An approved exception attached to a rule."""

    __tablename__ = "rule_exceptions"

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approved_rules.id"), nullable=False)
    exception_key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    condition_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    effect_override_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Structured magnitude (e.g. "up to 15 days/year"). Added to the canonical
    # contract before this column existed — see ADR-0009. Optional: a pure
    # carve-out exception with no numeric limit leaves both None.
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)

    rule: Mapped["ApprovedRule"] = relationship(back_populates="exceptions")


class PolicyException(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An ad hoc, human-requested, time-bounded waiver of a rule or an
    entire policy set for one particular case (ADR-0009).

    Distinct from `RuleException` above: a `RuleException` is an
    authoring-time carve-out baked into one specific `ApprovedRule`'s own
    definition (e.g. "employees under 2 years get a reduced limit") that
    the deterministic engine evaluates automatically for every matching
    case. A `PolicyException` is the opposite kind of thing — someone
    requests a one-off waiver of an otherwise-applicable rule for their
    specific situation (e.g. "waive the 3-day advance-notice rule for this
    request due to a family emergency"), and a human reviewer grants or
    denies it. It is never evaluated automatically by the engine.

    Fits inside the existing 3-actor model per ADR-0009: a composer or
    reviewer requests/reviews it, a policy manager decides. No new actor,
    no multi-level approval chain.

    `rule_id` is the STRING business key (`ApprovedRule.rule_id`, e.g.
    "AI-cb7b4a41c6"), the same convention `PolicyAggregateLimit
    .contributing_rules_json` and `ApprovedRule.related_rule_ids_json` use
    to reference rules — not a UUID FK, since it must stay stable across
    rule revisions and is never itself validated against a currently
    published revision (mirrors `PolicyTest.expected_rule_id`). Nullable:
    a null `rule_id` means the exception applies to the whole policy set
    rather than one specific rule.

    Mutable in place for the decide step (`decision`/`decided_by`
    /`decided_at`/`decision_notes`) — same posture as `PolicyTest`: a
    request record, not an immutable governance artifact like
    `ApprovedRule`, so updating it in place is not a Rule 5.3 violation.

    `is_expired` is deliberately NOT a stored column: this codebase has no
    background job/scheduler to flip a stale status, so expiry is computed
    at API-response time from `expiry_date < today AND decision ==
    "granted"` (see api/routers/policy_exceptions.py). Keeping `decision`
    limited to the actual human decision values (`pending`/`granted`
    /`denied`) avoids a fourth pseudo-state that would need to be kept in
    sync by something that doesn't exist.
    """

    __tablename__ = "policy_exceptions"

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    rule_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requester: Mapped[str] = mapped_column(String(200), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    policy_set: Mapped["PolicySet"] = relationship()


class EvidenceReference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Source lineage for a rule (document version, page, section, clause, offsets)."""

    __tablename__ = "evidence_references"

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approved_rules.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    clause_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clauses.id"), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rule: Mapped["ApprovedRule"] = relationship(back_populates="evidence")


class Evaluation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A recorded runtime evaluation request/response pair with result hash.

    Append-only audit record of runtime evaluator calls (never updated). Read
    back through the "Decision Log" (see `api/routers/evaluations.py`'s
    `list_evaluation_log`/`get_evaluation_log_detail`) — the query pattern is
    always "most recent calls for this policy set", hence the composite index.
    """

    __tablename__ = "evaluations"
    __table_args__ = (Index("ix_evaluations_policy_set_timestamp", "policy_set_id", "evaluation_timestamp"),)

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approved_policy_versions.id"), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    calling_system_identity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_facts_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    overall_status: Mapped[str] = mapped_column(String(50), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evaluation_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QualityRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An immutable record of one quality evaluation of a policy set.

    Append-only, mirroring `PolicyTestRun` and `Evaluation`: a re-run is always
    a new row, never an update, so quality can be compared over time ("did the
    high-severity count drop after we fixed those rules?") instead of only ever
    showing the latest result.

    Severity counts are stored denormalised alongside `findings_json` on
    purpose: the history list renders counts for every past run, and deriving
    them would mean deserialising every findings blob just to draw a list row.
    `version_number` is null for candidate-scope runs, which evaluate
    pre-publish drafts that belong to no published version.
    """

    __tablename__ = "quality_runs"

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # "published" | "candidates"
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_review_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    methodology_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    findings_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    triggered_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable audit trail record for authoritative actions (approvals, publications, etc.)."""

    __tablename__ = "audit_events"

    event_type: Mapped[str] = mapped_column(String(150), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(150), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class OutboxMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Reserved table for future transactional outbox publishing (not yet consumed)."""

    __tablename__ = "outbox_messages"

    message_type: Mapped[str] = mapped_column(String(150), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtractionStage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One recorded stage of a document-extraction run.

    Extraction is long and multi-phase: PDF conversion alone takes roughly three
    minutes before any model is called. A run that reports only a final value
    tells an operator nothing when it dies in the middle, and gives no basis for
    deciding whether a retry is safe. Each stage therefore records what it
    consumed, what it produced, and how it ended.

    `input_hash` and `output_hash` are what make a retry decidable rather than
    hopeful: a stage whose inputs hash the same as a previous successful run
    produced the same output, so it can be skipped instead of repeated.

    `idempotency_key` is the run-level key derived from the source bytes,
    canonical artifact, template and configuration. It is stored on every stage
    of the run so a partially completed run can be found by key alone, without
    first knowing which stage it reached.

    Deliberately *not* a second review or approval state machine. These rows
    describe extraction bookkeeping; the stages that observe the application's
    own decisions record references to them rather than duplicating their state.
    """

    __tablename__ = "extraction_stages"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", "stage_name", "attempt", name="uq_extraction_stages_key_stage_attempt"
        ),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False, index=True
    )
    #: Nullable: the early stages run before an ExtractionRun row exists, and
    #: forcing one to be created first would mean recording a run that may never
    #: get past conversion.
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Position in the pipeline, stored rather than inferred from `created_at`:
    #: several stages of one run routinely complete inside the same clock tick.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Note(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A human-authored, append-only note attached to a governed entity.

    Deliberately polymorphic (`entity_type` + `entity_id`) rather than a set
    of FK columns, because notes are a cross-cutting collaboration feature
    that must attach to several unrelated tables (a policy set, a specific
    rule lineage, a candidate under review, a published version) without
    forcing a schema change per entity type. `entity_id` is stored as text
    rather than a typed FK because it sometimes holds a stable business key
    (`CanonicalRule.rule_id`, which is meant to outlive any single revision
    or version) and sometimes a row UUID (`PolicySet.id`,
    `CandidateRule.id`, `ApprovedPolicyVersion.id`) — see
    `entity_type` values below for which is which:

    - "policy_set"     -> entity_id = PolicySet.id (UUID)
    - "policy_version" -> entity_id = ApprovedPolicyVersion.id (UUID);
                           used for release notes / publish sign-off remarks.
    - "candidate_rule" -> entity_id = CandidateRule.id (UUID)
    - "rule"           -> entity_id = CanonicalRule.rule_id (business key);
                           intentionally keyed by the stable rule id (not a
                           row id) so notes persist across a rule's
                           candidate -> approved -> superseded lifecycle.

    Notes are never edited in place (no update endpoint) — only appended or
    deleted by their author/an admin — so this table is an append-mostly
    audit-style log, consistent with the rest of the domain's governance
    posture.
    """

    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    author_role: Mapped[str] = mapped_column(String(50), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class PolicyTestBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One persisted blind-validation generation and execution set."""

    __tablename__ = "policy_test_batches"

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approved_policy_versions.id"), nullable=False, index=True
    )
    grounding_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_rule_ids_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    grounding_context_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    scenario_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(20), nullable=False)
    guidance: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    policy_set: Mapped["PolicySet"] = relationship()
    policy_version: Mapped["ApprovedPolicyVersion"] = relationship()
    tests: Mapped[list["PolicyTest"]] = relationship(
        back_populates="generation_batch", order_by="PolicyTest.created_at"
    )


class PolicyTest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named, saved test case for a policy set (Section 21.6 / 11.6).

    Distinct from the ad hoc `EvaluatePage`/`/api/evaluations` simulation
    feature: a `PolicyTest` is a persisted, re-runnable assertion about how
    the deterministic evaluator should behave, scoped to `policy_set_id`
    (NOT to one specific `ApprovedPolicyVersion`) so the same test can be
    re-executed against every future published version — see Section 9.11
    step 6 ("run deterministic tests" on publish).

    Mutable in place (`is_active`, `review_status`, and the definition
    fields themselves) — a test's own definition is not the kind of
    authoritative governance artifact `ApprovedRule` is, so editing/retiring
    a test is not a Rule 5.3 violation. Only `PolicyTestRun` (the recorded
    result of actually executing a test) is append-only.

    Review workflow: AI-proposed tests (`proposed_by="ai"`) start with
    `review_status="pending_review"` and `is_active=False` — they cannot be
    auto-run on publish until a human accepts them, because an AI can
    mis-predict `expected_overall_status`/`expected_rule_status` and a
    wrong-but-active test would generate misleading "failing test" noise in
    the Findings/Quality view. This is a deliberately *lighter-weight*
    review than `CandidateRule`'s (no `changes_requested`/manager-override
    escalation path) because a wrong PolicyTest cannot itself misconfigure
    production policy the way a wrong `ApprovedRule` can — the worst case is
    a spurious pass/fail in a test report, not an incorrect real-world
    decision. Human-authored tests (`proposed_by="human"`) skip review
    entirely (`review_status="active"`, `is_active=True` immediately) since
    a human is directly asserting what they already intend.
    """

    __tablename__ = "policy_tests"

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # One of: positive, negative, boundary, missing_fact, scope,
    # effective_date, exception, precedence (Section 21.6).
    test_kind: Mapped[str] = mapped_column(String(50), nullable=False)

    # Same shape as EvaluationRequest.facts (dict[str, object | None]).
    input_facts_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Nullable override for "effective_date" tests that must simulate
    # evaluating on a specific date rather than "now".
    evaluation_timestamp_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Expected assertions, checked against the real EvaluationResponse the
    # deterministic evaluator returns (see evaluator/test_runner.py). Kept
    # deliberately minimal per-field rather than a full expected-response
    # blob: expected_overall_status covers most test kinds on its own;
    # expected_rule_id/expected_rule_status let a test pin down one specific
    # rule's outcome (useful for precedence/exception tests where several
    # rules apply); expected_missing_facts_json lets a missing_fact test
    # assert exactly which fact(s) were flagged absent.
    expected_overall_status: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_rule_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expected_rule_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_missing_facts_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    generation_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_test_batches.id"), nullable=True, index=True
    )
    scenario_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expectation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    proposed_by: Mapped[str] = mapped_column(String(20), default="human", nullable=False)  # "ai" | "human"
    review_status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether this test is picked up by the on-publish auto-rerun (Section
    # 9.11 step 6) and counted in the Findings/Quality "failed tests" view.
    # A rejected or retired test is kept (never deleted) but excluded from
    # both by is_active=False.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    policy_set: Mapped["PolicySet"] = relationship()
    generation_batch: Mapped["PolicyTestBatch | None"] = relationship(back_populates="tests")
    runs: Mapped[list["PolicyTestRun"]] = relationship(
        back_populates="policy_test", order_by="PolicyTestRun.run_at.desc()"
    )


class PolicyTestRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An immutable record of one execution of a `PolicyTest` against one
    specific `ApprovedPolicyVersion`.

    Append-only (Rule 5.3-style, mirroring `Evaluation`/`ApprovedRule`): a
    re-run is always a new row, never an update to a prior run, so the full
    pass/fail history for a test over time and across published versions is
    preserved. `actual_response_json` stores the full real
    `EvaluationResponse` the deterministic evaluator returned, so a reviewer
    can inspect exactly what happened without re-running anything.
    """

    __tablename__ = "policy_test_runs"

    policy_test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_tests.id"), nullable=False, index=True)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approved_policy_versions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # "pass" | "fail" | "error"
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actual_response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expected_assertions_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expectation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # "manual" | "on_publish"
    triggered_by: Mapped[str] = mapped_column(String(200), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    policy_test: Mapped["PolicyTest"] = relationship(back_populates="runs")
    policy_version: Mapped["ApprovedPolicyVersion"] = relationship()


class PolicyAttestation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One employee's obligation to acknowledge one published policy version
    (ISO 37301 §7.3 "personnel shall be made aware of ... and shall be
    required to demonstrate their awareness of, and commitment to comply
    with" — ADR-0012).

    Bound to `policy_version_id` (not just `policy_set_id`), the same
    choice `PolicyTestRun` makes: the whole point is recording that a
    specific person acknowledged the specific obligations that were in
    force at a specific time, so the audit trail stays meaningful even
    after the policy set republishes under a new version. Republishing
    does NOT auto-create new attestation rows against the new version —
    that would silently invent an obligation nobody actually assigned. A
    Policy Manager launches a new campaign against the new version
    explicitly, the same way they must explicitly decide `PolicySet
    .review_due_date` rather than have it auto-recompute.

    `employee_name`/`employee_identifier` are free strings, not a FK to a
    user/employee table — this codebase has no personnel directory or
    authentication system (see `ActorContext.tsx`: only 3 governance
    actors — system_admin/policy_composer/policy_manager — are modeled at
    all, and personnel acknowledging a policy are explicitly NOT one of
    those actors). This mirrors the existing convention of `requester`
    (`PolicyException`) and `approved_by`/`reviewed_by` elsewhere: identity
    is asserted, not authenticated, consistent with this platform's local,
    trust-based posture end to end. `employee_identifier` (typically an
    email) is optional but is what the no-login self-service "find my
    attestations" lookup matches against in addition to name, so an
    employee can find their own pending items without a policy-set-scoped
    login.

    Mutable in place for the acknowledge step (`acknowledged_at`
    /`acknowledgment_notes`) — a request/assignment record, not an
    immutable governance artifact, the same posture as `PolicyException`
    /`PolicyTest`.

    `status` (pending/acknowledged/overdue) is deliberately NOT a stored
    column, for the same reason `PolicyException.is_expired` and
    `PolicySet.is_review_overdue` aren't: this codebase has no background
    scheduler to flip a stale value, so it's computed at API-response time
    from `acknowledged_at`/`due_date` (see
    api/routers/policy_attestations.py). This also means "escalation" here
    is a computed, queryable, always-fresh Overdue view a Policy Manager
    checks and acts on manually — there is no email/notification
    integration in this platform (see docs/known-limitations.md), so
    automatic escalation delivery is explicitly out of scope, not an
    oversight.
    """

    __tablename__ = "policy_attestations"

    policy_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_sets.id"), nullable=False, index=True)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approved_policy_versions.id"), nullable=False, index=True
    )
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    employee_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(200), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    policy_set: Mapped["PolicySet"] = relationship()
    policy_version: Mapped["ApprovedPolicyVersion"] = relationship()
