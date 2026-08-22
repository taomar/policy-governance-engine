"""API-layer request/response DTOs (distinct from canonical contracts).

These shapes are for HTTP request bodies that don't map 1:1 onto the
canonical evaluator contracts (e.g. policy-set creation, version import).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from policy_platform.contracts.policy import CanonicalRule


class CreatePolicySetRequest(BaseModel):
    key: str
    name: str
    owner: str
    description: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    # RACI ownership metadata (ADR-0013) — optional at creation time, same
    # precedent as `review_due_date` (added later via update), since a new
    # project usually starts from just "what is it, who's the department".
    accountable_owner: str = ""
    delegate_approver: str = ""
    escalation_contact: str = ""
    consulted_parties: list[str] = Field(default_factory=list)
    informed_parties: list[str] = Field(default_factory=list)


class UpdatePolicySetRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    review_due_date: date | None = None
    # Explicit clear flag rather than overloading `review_due_date: None` —
    # unlike the fields above (which have sensible non-null "empty" states),
    # `None` is the meaningful "no due date set" value for this field, so
    # "not provided" and "clear it" must be distinguishable.
    clear_review_due_date: bool = False
    # RACI ownership metadata (ADR-0013). Like `owner`/`category`, these all
    # have a sensible non-null "empty" state ("") so plain `None` safely means
    # "not provided" — no clear-flag needed, unlike `review_due_date`.
    accountable_owner: str | None = None
    delegate_approver: str | None = None
    escalation_contact: str | None = None
    consulted_parties: list[str] | None = None
    informed_parties: list[str] | None = None


class MarkPolicySetReviewedRequest(BaseModel):
    """Attest that a human just reviewed this policy set (ISO 37301 §9.3)."""

    next_due_date: date | None = None


class UpdateTrustedConfigRequest(BaseModel):
    """Replace a policy set's Section 83 trusted configuration.

    Deliberately not `| None`: an omitted body and an explicit `{}` must mean
    the same thing here, because clearing the fact model is a legitimate action
    and the empty config is a valid operating mode (honest, non-executable
    projections) rather than an error state.
    """

    trusted_config: dict[str, Any] = Field(default_factory=dict)


class PolicySetResponse(BaseModel):
    id: str
    key: str
    name: str
    owner: str
    description: str
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    review_due_date: date | None = None
    last_reviewed_at: datetime | None = None
    is_review_overdue: bool = False
    accountable_owner: str = ""
    delegate_approver: str = ""
    escalation_contact: str = ""
    consulted_parties: list[str] = Field(default_factory=list)
    informed_parties: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


INGESTION_STATUS_OK = "ok"
INGESTION_STATUS_WARNING = "warning"
INGESTION_STATUS_ERROR = "error"
INGESTION_STATUS_UNRECORDED = "unrecorded"


def ingestion_status_of(diagnostics: list | None, error: str | None) -> str:
    """Summarise how a document version's ingestion went, from stored facts only.

    Derived at the response boundary rather than stored, deliberately. A stored
    summary is a second copy of a fact that can drift from the diagnostics it
    summarises; deriving it means there is one source of truth and no field to
    fall out of sync. (The run-status case went the other way for a reason that
    does not apply here: `status == "completed"` was ALREADY load-bearing as a
    trust predicate, so a new stored value made an existing query correct by
    construction. Nothing yet queries document ingestion health, so there is no
    wrong predicate to repair -- only a reader to inform.)

    `UNRECORDED` is not `OK`. A version ingested before diagnostics were
    persisted has NULL in both columns, and the honest thing to say about it is
    that nobody knows, not that it was clean. Collapsing the two would recreate
    the defect these columns exist to close, one layer up.
    """
    if error:
        return INGESTION_STATUS_ERROR
    if diagnostics is None:
        return INGESTION_STATUS_UNRECORDED
    severities = {str(d.get("severity", "")).lower() for d in diagnostics if isinstance(d, dict)}
    if INGESTION_STATUS_ERROR in severities:
        return INGESTION_STATUS_ERROR
    if INGESTION_STATUS_WARNING in severities:
        return INGESTION_STATUS_WARNING
    return INGESTION_STATUS_OK


class DocumentVersionResponse(BaseModel):
    id: str
    version_number: int
    content_hash: str
    storage_path: str
    mime_type: str
    created_at: datetime
    #: Problems observed while ingesting THIS version, verbatim from storage.
    #: Codes, not prose -- how to word them for a reader is the UI's decision.
    ingestion_diagnostics: list[dict] = Field(default_factory=list)
    #: Present when clause extraction raised; the upload still succeeded.
    ingestion_error: str | None = None
    #: Derived by `ingestion_status_of`; see that function for why it is not
    #: stored. Lets a list view mark a flawed version without reading details.
    ingestion_status: str = INGESTION_STATUS_UNRECORDED


class SourceDocumentResponse(BaseModel):
    id: str
    title: str
    owner: str
    source_system: str
    created_at: datetime
    versions: list[DocumentVersionResponse]
    policy_set_id: str | None = None
    policy_set_key: str | None = None
    policy_set_name: str | None = None


class AssignDocumentRequest(BaseModel):
    """Body for filing an (often pre-existing, unassigned) document into a project.

    `policy_set_key: None` explicitly un-assigns the document back to the
    global Document Inbox.
    """

    policy_set_key: str | None = None


class ClauseResponse(BaseModel):
    id: str
    document_version_id: str
    clause_ref: str
    section: str | None
    page: int | None
    text: str
    sequence: int
    element_id: str | None = None
    element_type: str | None = None
    search_document_id: str
    search_index: str


class ImportPolicyVersionRequest(BaseModel):
    """Manual import of an already-approved canonical policy version.

    This is an intentional stand-in for the full extraction -> review ->
    approval governance workflow (deferred; see docs/known-limitations.md).
    It lets a locally-approved `ApprovedPolicyPackage`-shaped payload be
    persisted so the evaluator has something real to run against.
    """

    version_number: int
    effective_from: date
    effective_to: date | None = None
    approved_by: str
    is_active: bool = True
    rules: list[CanonicalRule]


class PolicyIndexBuildResponse(BaseModel):
    state: str
    policy_set_key: str
    index_name: str
    version_number: int | None
    document_count: int
    indexed_at: datetime
    error: str | None = None


class PolicyIndexStateResponse(BaseModel):
    """Recorded per-project policy index state; this is not a live Search probe.

    The endpoint serving this model reads PostgreSQL only. It reports the app's
    own record of the last best-effort build attempt and derives freshness from
    that record plus the active approved version, so a project page can load
    cheaply even when Azure Search is unavailable. It does not verify that the
    Azure Search index exists or contains these documents at request time.
    """

    policy_set_key: str
    index_name: str
    last_attempt: Literal["built", "skipped", "failed", "never_attempted"]
    freshness: Literal["current", "stale", "nothing_to_index", "unknown"]
    active_version_number: int | None
    indexed_version_number: int | None
    attempted_version_number: int | None
    document_count: int
    built_at: datetime | None
    attempted_at: datetime | None
    error: str | None = None
    source: Literal["recorded_build_state"] = "recorded_build_state"
    live_probe: Literal[False] = False


class ApprovedPolicyVersionResponse(BaseModel):
    id: str
    policy_set_id: str
    version_number: int
    effective_from: date
    effective_to: date | None
    is_active: bool
    approved_by: str
    approved_at: datetime
    rule_count: int
    policy_index_build: PolicyIndexBuildResponse | None = None


class CandidateRuleDraftRequest(BaseModel):
    """A human- or extraction-drafted candidate rule awaiting review.

    Accepts a full `CanonicalRule` payload for convenience/reuse of the
    existing contract shape; the server overwrites `policy_set_id`,
    `policy_version_id`, and `schema_version` at both draft-creation and
    publish time, so any values submitted for those three fields are
    placeholders and are ignored.
    """

    rule: CanonicalRule


class CandidateRuleResponse(BaseModel):
    id: str
    policy_set_id: str
    extraction_run_id: str
    rule_type: str
    revision: int
    review_status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_notes: str | None
    published_version_id: str | None
    created_at: datetime
    # Cross-run delta. Optional because rules drafted before delta tracking
    # existed, and rules composed by hand, have no run to compare against.
    delta_status: str | None = None
    reworded: bool = False
    baseline_candidate_id: str | None = None
    superseded_at: datetime | None = None
    #: The record that replaced this one, when a later run produced a reading of
    #: the same sentence. Derived over the set being returned rather than
    #: stored: `superseded_at` is deliberately not set for a candidate a human
    #: has already published, because a re-run is a machine action and must not
    #: bury someone's decision — but the consequence is that publishing v1, then
    #: extracting again and publishing v2, leaves both in the queue, and a
    #: reader has no way to tell which is current.
    #:
    #: Absent means this is the latest reading of its sentence.
    superseded_by_candidate_id: str | None = None
    #: Which persisted provision states this rule — a reference, never the
    #: provision itself.
    #:
    #: Deliberately an identity and nothing more. `GET /policies` already
    #: composes the provision: which rules belong together, the heading chain,
    #: the passages. Repeating any of that here would put two answers to one
    #: question on the same page, free to disagree the moment a filter, a
    #: superseded row or a stale cache separates them — which is the defect
    #: persisting the grouping was meant to end. A reference cannot disagree
    #: with the thing it points at; it can only fail to resolve, and that is
    #: visible.
    #:
    #: Costs no query: the column is already on the row being serialised.
    #:
    #: Absent for a rule extracted before provisions existed, or one whose
    #: document defeated grouping. Absent means "not linked", never "no
    #: provisions here" — those rules are still reviewable, under the heading
    #: their evidence records.
    provision_id: str | None = None
    rule: CanonicalRule


class PaginatedCandidateRulesResponse(BaseModel):
    """Paginated wrapper returned when ``limit`` is supplied to the
    candidate-rules list endpoint.

    Without ``limit`` the endpoint returns a bare ``list[CandidateRuleResponse]``
    for backward compatibility.  The response type therefore changes based on a
    query parameter — a deliberate, documented trade-off to keep every existing
    caller working unchanged while new callers opt into pagination.
    """

    items: list[CandidateRuleResponse]
    next_cursor: str | None = None
    total: int


class CandidateRuleReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str
    notes: str | None = None


class CandidateRuleEditRequest(BaseModel):
    """A human's direct, manual correction to a candidate rule's content.

    Distinct from the AI "suggest rewrite" flow — this is the reviewer/composer
    typing an exact change themselves (wording, threshold, dates, condition)
    rather than asking the model to draft one. Only valid while the candidate
    is still editable (candidate/rejected/changes_requested); identity fields
    (rule_id, policy_set_id, policy_version_id) are server-owned and always
    overwritten regardless of what is submitted.
    """

    rule: CanonicalRule
    editor: str


class RequestChangesRequest(BaseModel):
    """A Policy Manager sending an already-approved-but-unpublished candidate
    back to the composer/reviewer for rework, before it can be published.
    """

    manager: str
    actor_role: str
    reason: str
    notes: str | None = None


class OverrideReviewRequest(BaseModel):
    """A Policy Manager directly forcing a review decision, bypassing the
    normal composer/reviewer step — e.g. approving something a reviewer
    rejected, or rejecting something a reviewer approved, with mandatory
    justification. Never usable on an already-published candidate; publishing
    is a one-way door (see ApprovedRule immutability, domain/models.py).
    """

    manager: str
    actor_role: str
    decision: Literal["approve", "reject"]
    reason: str
    notes: str | None = None


class BulkCandidateRuleReviewRequest(BaseModel):
    """Review many candidate rules in one call.

    Needed because a single AI extraction run over a real document can
    produce hundreds of candidates (e.g. 419 from the HR Guide) — reviewing
    one-by-one via individual POST /review calls does not scale for a human
    reviewer working through an extraction batch.
    """

    candidate_ids: list[str] = Field(default_factory=list, description="Empty means 'all pending candidates'")
    decision: Literal["approve", "reject"]
    reviewer: str
    notes: str | None = None


class BulkReviewResult(BaseModel):
    reviewed: int
    skipped: list[str] = Field(default_factory=list)


class PublishCandidatesRequest(BaseModel):
    approved_by: str
    effective_from: date
    effective_to: date | None = None
    version_number: int | None = None
    is_active: bool = True


class CreateNoteRequest(BaseModel):
    # "provision" keys on `DocumentProvision.provision_key`, not on the row id.
    # See `domain/models.py::Note` for why: the row is per document version and
    # is replaced by the next extraction run, which would take a policy's notes
    # out of view without deleting one.
    entity_type: Literal["policy_set", "policy_version", "candidate_rule", "rule", "provision"]
    entity_id: str
    author: str
    author_role: str
    body: str


class NoteResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    author: str
    author_role: str
    body: str
    created_at: datetime


class CreatePolicyTestRequest(BaseModel):
    """Manually author a `PolicyTest`. Human-authored tests skip the AI
    review step entirely (review_status="active", is_active=True
    immediately) — a human is already directly asserting the expectation,
    so there is nothing further to review."""

    name: str
    description: str = ""
    test_kind: Literal[
        "positive", "negative", "boundary", "missing_fact", "scope", "effective_date", "exception", "precedence"
    ]
    input_facts: dict[str, object | None] = Field(default_factory=dict)
    evaluation_timestamp: datetime | None = None
    expected_overall_status: Literal["SATISFIED", "NOT_SATISFIED", "NOT_APPLICABLE", "INDETERMINATE", "ERROR"]
    expected_rule_id: str | None = None
    expected_rule_status: Literal["SATISFIED", "NOT_SATISFIED", "NOT_APPLICABLE", "INDETERMINATE", "ERROR"] | None = (
        None
    )
    expected_missing_facts: list[str] | None = None


class ProposePolicyTestsRequest(BaseModel):
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    # Optional plain-English steer, e.g. "focus on overtime pay thresholds and
    # end-of-service benefits". It shapes which scenarios the model prioritises;
    # it never changes how pass/fail is judged, which stays with the
    # deterministic evaluator.
    guidance: str = ""


class GeneratePolicyValidationBatchRequest(BaseModel):
    rule_ids: list[str] = Field(min_length=1, max_length=12)
    tests_per_policy: int = Field(default=3, ge=0, le=10)
    policy_version_id: str | None = None
    scenario_text: str = ""
    grounding_mode: Literal["json_only", "json_search"] = "json_only"
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    guidance: str = ""
    created_by: str


class RunPolicyValidationBatchRequest(BaseModel):
    triggered_by: str
    policy_version_id: str | None = None


class PolicyTestReviewRequest(BaseModel):
    decision: Literal["accept", "reject"]
    reviewer: str
    notes: str | None = None


class RunPolicyTestRequest(BaseModel):
    triggered_by: str
    policy_version_id: str | None = None


class PolicyTestResponse(BaseModel):
    id: str
    policy_set_id: str
    name: str
    description: str
    test_kind: str
    input_facts: dict[str, object | None]
    evaluation_timestamp: datetime | None
    scenario_text: str = ""
    generation_batch_id: str | None = None
    expectation_hash: str | None = None
    expectation_revealed: bool = True
    expected_overall_status: str | None
    expected_rule_id: str | None
    expected_rule_status: str | None
    expected_missing_facts: list[str] | None
    proposed_by: str
    review_status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_notes: str | None
    is_active: bool
    created_at: datetime


class PolicyTestRunResponse(BaseModel):
    id: str
    policy_test_id: str
    policy_version_id: str
    status: str
    explanation: str
    actual_response_json: dict | None
    expected_assertions_json: dict | None = None
    expectation_hash: str | None = None
    run_trigger: str
    triggered_by: str
    run_at: datetime


class PolicyTestListItemResponse(BaseModel):
    """A test paired with its most recent run, if any — avoids embedding
    `latest_run` recursively inside `PolicyTestResponse` for the common
    list/failing-tests views."""

    test: PolicyTestResponse
    latest_run: PolicyTestRunResponse | None = None
    runs: list[PolicyTestRunResponse] = Field(default_factory=list)


class PolicyTestBatchResponse(BaseModel):
    id: str
    policy_set_id: str
    policy_version_id: str
    version_number: int
    grounding_mode: str
    selected_rule_ids: list[str]
    grounding_context: dict
    scenario_count: int
    tests_per_policy: int
    reasoning_effort: str
    guidance: str
    created_by: str
    status: str
    executed_at: datetime | None
    created_at: datetime
    tests: list[PolicyTestListItemResponse]


class ProposePolicyTestsResponse(BaseModel):
    policy_set_key: str
    version_number: int
    reasoning_effort: str
    proposed_tests: list[PolicyTestResponse]
    skipped: list[str]


class CreatePolicyExceptionRequest(BaseModel):
    """Request an ad hoc, time-bounded waiver of a rule (or the whole policy
    set, if `rule_id` is omitted) for one particular case (ADR-0009).

    Distinct from `RuleException` (domain model): that is a standing,
    automatically-evaluated carve-out baked into a rule's own definition;
    this is a one-off human request a policy manager grants or denies.
    """

    rule_id: str | None = None
    requester: str
    justification: str
    expiry_date: date | None = None


class DecidePolicyExceptionRequest(BaseModel):
    decision: Literal["granted", "denied"]
    decided_by: str
    decision_notes: str | None = None


class PolicyExceptionResponse(BaseModel):
    id: str
    policy_set_id: str
    rule_id: str | None
    requester: str
    justification: str
    decision: str
    expiry_date: date | None
    decided_by: str | None
    decided_at: datetime | None
    decision_notes: str | None
    # Computed at response time, not stored — see domain.models.PolicyException
    # docstring for why (no background job exists to flip a stored status).
    is_expired: bool
    created_at: datetime


class EvaluationLogSummary(BaseModel):
    """One row of the decision log (ADR-0009 "Adopt, incremental": OPA
    Decision-Log parity). Omits `request_facts`/`response` — the full
    input/output pair — to keep a page of history light; see
    `EvaluationLogDetail` for the single-record view that includes them.
    """

    id: str
    policy_set_id: str
    policy_version_id: str
    correlation_id: str | None
    calling_system_identity: str | None
    overall_status: str
    result_hash: str
    evaluation_timestamp: datetime


class EvaluationLogDetail(EvaluationLogSummary):
    request_facts: dict
    response: dict


class AttestationAssignee(BaseModel):
    """One recipient of an attestation campaign (ADR-0012). `identifier` is
    typically an email — optional, but is what the no-login self-service
    "find my attestations" search matches in addition to name.
    """

    name: str
    identifier: str | None = None


class CreatePolicyAttestationCampaignRequest(BaseModel):
    """Launch an attestation campaign: assign one published policy version's
    acknowledgment obligation to a batch of employees, all sharing one due
    date. Manager-only (see `_require_manager` in the router) — assigning a
    compliance obligation to personnel is a policy-manager decision, the
    same authority level `PolicySet.review_due_date` and `PolicyException
    .decide` already require.
    """

    policy_version_id: str
    employees: list[AttestationAssignee] = Field(min_length=1)
    due_date: date
    assigned_by: str
    actor_role: str


class AcknowledgePolicyAttestationRequest(BaseModel):
    acknowledgment_notes: str | None = None


class PolicyAttestationResponse(BaseModel):
    id: str
    policy_set_id: str
    policy_version_id: str
    version_number: int
    employee_name: str
    employee_identifier: str | None
    due_date: date
    assigned_by: str
    acknowledged_at: datetime | None
    acknowledgment_notes: str | None
    # Computed at response time, not stored — see
    # domain.models.PolicyAttestation docstring for why (no background job
    # exists to flip a stored status). One of: "pending", "acknowledged",
    # "overdue".
    status: Literal["pending", "acknowledged", "overdue"]
    created_at: datetime


# ── policy review requests (viewer feedback) ─────────────────────────


class CreatePolicyReviewRequestRequest(BaseModel):
    """Submit feedback on a published policy version. This is a viewer
    capability — it appends a record and never touches the policy."""

    policy_set_key: str
    approved_policy_version_id: str
    comment: str
    categories: list[str] | None = None
    submitted_by: str


class AcknowledgePolicyReviewRequestRequest(BaseModel):
    resolved_by: str


class ResolvePolicyReviewRequestRequest(BaseModel):
    disposition: Literal["actioned", "dismissed"]
    resolution_note: str | None = None
    resolved_by: str


class PolicyReviewRequestResponse(BaseModel):
    id: str
    policy_set_key: str
    approved_policy_version_id: str
    submitted_by: str
    submitted_at: datetime
    comment: str
    categories: list[str] | None
    status: str
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
