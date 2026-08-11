"""Canonical policy representation (Section 14).

This is the provider-neutral intermediate representation. It must not depend
on Azure OpenAI response objects, Microsoft Agent Framework messages, Azure AI
Search documents, UI component structures, a particular workflow engine, or
generated source code.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from policy_platform.contracts.conditions import ConditionNode
from policy_platform.contracts.formulation import RuleFormulation

CANONICAL_SCHEMA_VERSION = "1.0"


class RuleType(str, Enum):
    ELIGIBILITY = "eligibility"
    PERMISSION = "permission"
    PROHIBITION = "prohibition"
    OBLIGATION = "obligation"
    APPROVAL_REQUIREMENT = "approval_requirement"
    EVIDENCE_REQUIREMENT = "evidence_requirement"
    THRESHOLD = "threshold"
    DEADLINE = "deadline"
    CALCULATION = "calculation"
    ROUTING = "routing"
    NOTIFICATION = "notification"
    ESCALATION = "escalation"
    EXCEPTION = "exception"
    DEFINITION = "definition"
    SCOPE = "scope"
    DELEGATION_OF_AUTHORITY = "delegation_of_authority"
    RETENTION = "retention"
    ACCESS_RESTRICTION = "access_restriction"
    HUMAN_JUDGMENT_REQUIREMENT = "human_judgment_requirement"


class EffectType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_ACTION = "require_action"
    # A rule that states vocabulary/classification rather than authorizing or
    # forbidding anything (e.g. a `definition`/`classification` rule_type).
    # Added so `_RULE_TYPE_MAP` has somewhere truthful to send these instead
    # of forcing `ALLOW` — see `ai_quality._definition_effect_findings` for
    # the defect this fixes (a negatively-phrased definition asserting the
    # inverse permission of its source text) and `_apply_combining_algorithm`
    # for why this effect never competes on the allow/deny axis.
    INFORMATIONAL = "informational"


class AmbiguityStatus(str, Enum):
    NONE = "none"
    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"
    HUMAN_JUDGMENT_REQUIRED = "human_judgment_required"


class ReviewStatus(str, Enum):
    CANDIDATE = "candidate"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PolicyAuthority(BaseModel):
    level: str
    owner: str
    rank: int


class PolicyScope(BaseModel):
    jurisdictions: list[str] = Field(default_factory=list)
    organizational_units: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)


class PrincipalContext(BaseModel):
    """Who is actually asking, at evaluation time — the request-side mirror of
    `PolicyScope`'s four dimensions (XACML terms: `PolicyScope` is this rule's
    Target; this is the Subject/Environment attributes a Target is matched
    against). A rule's scope is only ever an access restriction if something
    compares it against a real requester; previously nothing did (scope was
    captured but never checked — AI extraction always emitted an empty
    `PolicyScope()`, manual authoring hardcoded `personas: ["*"]`, and the
    evaluator never referenced `rule.scope` at all).

    This is NOT part of the `EvaluationRequest` wire contract — Section 9.13
    fixes that request to exactly {policy_set_id, policy_version_id,
    use_active_version, evaluation_timestamp, facts, correlation_id,
    calling_system_identity}; there is no separate principal field. Instead,
    `to_facts()` flattens this into the reserved fact-key convention
    (`subject.persona`, `subject.organizationalUnit`, `subject.jurisdiction`,
    `context.process`) that the evaluator's Target-matching step reads out of
    the ordinary `facts` dict. Callers (e.g. the frontend's "who is asking"
    panel, or test fixtures) can build one of these for ergonomics and merge
    `to_facts()` into `EvaluationRequest.facts` before submitting — the wire
    contract itself never changes shape.

    `None` means "unknown/not supplied" for that dimension, which only
    satisfies rules that leave the matching scope dimension unrestricted
    (empty or `["*"]`) — an unspecified principal can never satisfy a rule
    that names specific personas/units/jurisdictions/processes. This is the
    safe default: absence of identity never grants access, mirroring how real
    ABAC/IAM engines treat an unauthenticated or under-specified principal.
    """

    persona: str | None = None
    organizational_unit: str | None = None
    jurisdiction: str | None = None
    process: str | None = None

    def to_facts(self) -> dict[str, str]:
        """Flatten into the reserved fact keys the evaluator's Target-matching
        step looks for. Only populated dimensions are included — an absent
        key is treated identically to an absent fact (see class docstring).
        """

        facts: dict[str, str] = {}
        if self.persona is not None:
            facts["subject.persona"] = self.persona
        if self.organizational_unit is not None:
            facts["subject.organizationalUnit"] = self.organizational_unit
        if self.jurisdiction is not None:
            facts["subject.jurisdiction"] = self.jurisdiction
        if self.process is not None:
            facts["context.process"] = self.process
        return facts


class Effect(BaseModel):
    type: EffectType
    action: str


class RequiredFact(BaseModel):
    name: str
    data_type: str
    required: bool = True


class EvidenceReference(BaseModel):
    document_version_id: str
    source_hash: str
    page: int | None = None
    section: str | None = None
    clause_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None


class RuleLineage(BaseModel):
    extraction_run_id: str | None = None
    deployment_name: str | None = None
    prompt_version: str | None = None
    parser_version: str | None = None
    schema_version: str = CANONICAL_SCHEMA_VERSION


class Advice(BaseModel):
    """Non-blocking supplementary guidance attached to a rule's decision.

    Grounded in XACML 3.0's Obligations-vs-Advice distinction: Obligations
    (this codebase's existing `Effect(type=REQUIRE_ACTION)`) MUST be carried
    out by the Policy Enforcement Point for the decision to be honored;
    Advice is informational and MAY be safely ignored by a PEP that doesn't
    understand it. Modeled as a flat, always-attached-on-SATISFIED note
    (no separate condition of its own) — same simplicity as `Effect.action`,
    just non-mandatory and not mutually exclusive with an obligation on the
    same rule (a single rule can carry both a required action AND advice).
    """

    advice_id: str
    text: str


class RuleException(BaseModel):
    exception_id: str
    description: str
    condition: ConditionNode | None = None
    effect_override: Effect | None = None
    # Structured magnitude, so an exception can carry a limit rather than only
    # prose (e.g. "up to 15 days/year for a sick family member"). Optional and
    # free-standing: a pure carve-out exception with no numeric limit leaves
    # these None, exactly as before.
    limit_value: float | None = None
    limit_unit: str | None = None


class AggregateLimitContribution(BaseModel):
    """One rule's numeric contribution to a shared aggregate cap."""

    rule_id: str
    # The fact name whose value (when this rule is SATISFIED) counts toward
    # the shared sum — e.g. "leave.daysRequested" for a leave-entitlement rule.
    amount_fact: str


class AggregateLimit(BaseModel):
    """A cross-rule cap on the combined numeric outcome of several rules.

    Grounded in OMG DMN's "Collect" hit policy with a SUM aggregator — the
    standard, named mechanism business-rule engines (Camunda, Drools, IBM ODM)
    use to combine several matching rules' numeric outputs under one shared
    ceiling. This is the same shape as the real-world US FMLA 12-workweek cap
    combined across different qualifying leave reasons — e.g. two different
    leave-entitlement rules (60 days for a pregnancy, 15 days/year for a sick
    family member) whose days jointly may not exceed 70/year.

    Distinct from `RuleException`, which only modifies a single rule's own
    effect — this spans multiple `rule_id`s and is evaluated as its own step
    after per-rule evaluation completes, not as part of any one rule's
    condition.
    """

    aggregate_id: str
    description: str
    contributing_rules: list[AggregateLimitContribution] = Field(default_factory=list)
    aggregator: Literal["SUM"] = "SUM"
    max_value: float
    period: str | None = None


class PartyRoleName(str, Enum):
    """A party's role, in XACML 3.0 §B.2 terms where the standard has them."""

    #: `urn:oasis:names:tc:xacml:1.0:subject-category:access-subject`
    ACCESS_SUBJECT = "access_subject"
    #: `urn:oasis:names:tc:xacml:1.0:subject-category:recipient-subject`
    RECIPIENT_SUBJECT = "recipient_subject"
    #: No XACML subject category: XACML models a required approval as an
    #: Obligation on a Permit rather than as a subject of the request. DMN 1.5
    #: models it as an `authorityRequirement` on a `knowledgeSource`.
    AUTHORITY = "authority"


class RulePartyRef(BaseModel):
    """One party the rule names, quoted from the source.

    `name` is verbatim. Resolving "the Board of Trustees" to a directory
    principal or an approval queue is a mapping into a customer's org model,
    and inventing it would be the same failure as inventing a fact path.
    """

    name: str
    role: PartyRoleName
    #: Which canonical field or delegation construction it was read from, so a
    #: reviewer can check the claim rather than take it on trust.
    source: str


class RequiredAttributeRef(BaseModel):
    """One thing an evaluator must find in the customer's case.

    This is the target list the extraction step never had. Without it the LLM
    reading a customer's text decides for itself what is relevant, which is
    where non-determinism enters — at extraction, before evaluation. With it,
    an attribute the case never mentions is detectably absent rather than
    silently estimated, which is the difference between XACML's Indeterminate
    and a confident wrong answer.
    """

    phrase: str
    #: The canonical field the phrase was quoted from.
    role: str


class DecisionReadiness(BaseModel):
    """Whether an LLM can decide this rule, and what it needs to do so."""

    #: `decidable` | `discretionary` | `underspecified` | `not_a_decision` |
    #: `malformed`. Five values rather than a boolean because a fully-stated
    #: prohibition, a decision the document delegated, and a mis-split sentence
    #: are all un-projectable to FEEL and only the last is a defect.
    evaluability: str
    #: Why, naming the canonical field that decided it.
    reason: str
    required_attributes: list[RequiredAttributeRef] = Field(default_factory=list)
    parties: list[RulePartyRef] = Field(default_factory=list)

    @property
    def judgement_bounded(self) -> bool:
        """True when a named party must exercise judgement.

        Keyed on an authority party rather than on `evaluability`, because a
        rule can state a testable limit *and* require a human to approve it —
        "not exceeding 5% ... and subject to the judgment and approval of the
        Board of Trustees" is both, and grouping only the rules with nothing
        else stated would leave out the one that most needs a human.
        """

        return any(p.role is PartyRoleName.AUTHORITY for p in self.parties)


class CanonicalRule(BaseModel):
    """A single approved, versioned, machine-executable rule.

    Mirrors the representative structure in Section 14 of the specification.
    """

    schema_version: str = CANONICAL_SCHEMA_VERSION
    policy_set_id: str
    policy_version_id: str
    rule_id: str
    rule_revision: int
    title: str
    description: str = ""
    rule_type: RuleType
    authority: PolicyAuthority
    scope: PolicyScope
    condition: ConditionNode
    effect: Effect
    required_facts: list[RequiredFact] = Field(default_factory=list)
    exceptions: list[RuleException] = Field(default_factory=list)
    priority: int = 0
    effective_from: date
    effective_to: date | None = None
    machine_executable: bool = True
    ambiguity_status: AmbiguityStatus = AmbiguityStatus.NONE
    review_status: ReviewStatus = ReviewStatus.APPROVED
    evidence: list[EvidenceReference] = Field(default_factory=list)
    lineage: RuleLineage = Field(default_factory=RuleLineage)
    # Business classification independent of rule_type (which is about
    # evaluator semantics). category is a single free-text business domain
    # (e.g. "HR", "Finance", "IT"); tags are free-form labels for finer
    # cross-cutting filters (e.g. "leave", "escalation", "q3-2025").
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    # Clusters rules that represent variations/scenarios of one policy topic
    # (e.g. all leave-entitlement rules under "Parental & Family Leave") so the
    # UI can present them together instead of as unrelated flat rows.
    group_label: str = ""
    related_rule_ids: list[str] = Field(default_factory=list)
    # Section 15.4 precedence dimensions not otherwise derivable from existing
    # fields. is_explicit_override: this rule is a deliberate, named override
    # of otherwise-applicable rules (e.g. "executives may override the standard
    # approval threshold") — a real, structural fact about the rule, not
    # decorative title text. supersedes_rule_ids: this rule explicitly
    # replaces the named prior rule_id(s) within the same policy version (a
    # rule-level supersession, distinct from the whole-version supersession
    # already handled by publish/versioning).
    is_explicit_override: bool = False
    supersedes_rule_ids: list[str] = Field(default_factory=list)
    # XACML Obligations/Advice gap (see `Advice` docstring): supplementary,
    # non-blocking guidance surfaced alongside this rule's decision when
    # SATISFIED. Distinct from `effect` (the Obligation-equivalent action a
    # PEP must carry out) — a rule may have neither, either, or both.
    advice: list[Advice] = Field(default_factory=list)
    # The policy-formulator agent's standards-grounded record for this rule:
    # the canonical subject/predicate/object decomposition and its OMG DMN 1.5
    # projection (see contracts.formulation). Retained verbatim because the
    # fields above are a *lossy* executable projection of it — the platform's
    # `rule_type` vocabulary is about evaluator semantics and cannot represent
    # every canonical distinction the specification draws (entitlement vs
    # eligibility, recommendation vs obligation). Keeping the formulation means
    # a reviewer can always see what the source actually said, and a future
    # DMN compiler can work from the projection rather than re-extracting.
    # None for hand-authored rules and for rules drafted before this agent.
    formulation: RuleFormulation | None = None
    # What an LLM evaluating this rule against a customer's case needs, and
    # whether it can. Deliberately separate from `machine_executable`, which
    # answers whether the *FEEL* evaluator can decide the rule and is False for
    # every AI-extracted rule because no fact model exists. The shipped JSON is
    # evaluated by an LLM that binds terms from the case at evaluation time, so
    # that flag measures a capability the deployment does not use — reporting
    # only it said "0 of 45 executable" about a document whose rules are mostly
    # decidable. See infrastructure.evaluability.
    #
    # None for hand-authored rules, which never went through the formulator.
    # Absent is kept distinct from failed, as everywhere else here.
    decision_readiness: DecisionReadiness | None = None


class ApprovedPolicyPackage(BaseModel):
    """An immutable, approved policy version — the unit the evaluator consumes."""

    schema_version: str = CANONICAL_SCHEMA_VERSION
    policy_set_id: str
    policy_version_id: str
    effective_from: date
    effective_to: date | None = None
    rules: list[CanonicalRule] = Field(default_factory=list)
    aggregate_limits: list[AggregateLimit] = Field(default_factory=list)
