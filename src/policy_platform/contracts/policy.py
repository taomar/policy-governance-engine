"""Canonical policy representation (Section 14).

This is the provider-neutral intermediate representation. It must not depend
on Azure OpenAI response objects, Microsoft Agent Framework messages, Azure AI
Search documents, UI component structures, a particular workflow engine, or
generated source code.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Final, Literal

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
    #: What the number counts, in the document's own words — "minutes",
    #: "calendar days", "months". Empty when the source named none.
    #:
    #: Load-bearing wherever a condition compares a fact against a bare literal.
    #: "lateness > 15" is not a rule until something says fifteen *of what*, and
    #: a consumer holding seconds would satisfy it with a quarter of a minute.
    #: Carried verbatim and never mapped onto a canonical vocabulary, because
    #: "calendar days" and "working days" are different quantities and a table
    #: that flattened them would change what rules mean without saying so.
    unit: str = ""


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
    #: Which document element(s) this specific rule was formulated from, e.g.
    #: "p5-6-E000050". Scoped to the rule rather than the whole batch, which is
    #: what stops one rule from a multi-topic batch appearing to come from
    #: another rule's clause.
    #:
    #: It lived in the description until the description became the policy as
    #: written. Attribution is lineage, not prose, and a reviewer reading the
    #: rule's text should not have to step over it.
    source_elements: str = ""


def evaluation_mode_from(
    condition: "ConditionNode", required_facts: "list[RequiredFact]"
) -> EvaluationMode:
    """Whether a condition is decided by the engine or by reading it.

    Derived from the condition itself rather than from any flag, because the
    condition is the thing that decides it. A rule is `deterministic` exactly
    when it carries a test the engine can run over facts it has been told to
    expect — a tree with at least one comparison, and the facts that tree
    reads. Everything else is `ai_ready`.

    Deliberately not a stored field. A second copy could disagree with the tree
    it describes, and a correction would then reach rules extracted afterwards
    and not the ones already on disk.
    """

    from policy_platform.contracts.conditions import AllCondition, AnyCondition

    if isinstance(condition, AllCondition) and not condition.all:
        return EvaluationMode.AI_READY
    if isinstance(condition, AnyCondition) and not condition.any:
        return EvaluationMode.AI_READY
    if not required_facts:
        # A tree with no named facts has nothing to read a case against, so the
        # engine would decide it on nothing.
        return EvaluationMode.AI_READY
    return EvaluationMode.DETERMINISTIC


def evaluation_mode_for(rule: "CanonicalRule") -> EvaluationMode:
    """`evaluation_mode_from` for a whole rule. One implementation, two shapes."""

    return evaluation_mode_from(rule.condition, rule.required_facts)


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


class CandidateRelationship(BaseModel):
    """A typed link discovery found without enough evidence to confirm.

    Carries its own reason so a reviewer can judge it rather than take it on
    trust — which is the whole difference between a candidate and a confirmed
    edge. Never merged into `related_rule_ids`.
    """

    target_rule_id: str
    #: One of `contracts.relationships.PolicyRelationshipType`.
    relationship_type: str
    #: Why discovery proposed it, quoted or named, never a similarity score
    #: presented as a fact.
    reason: str = ""


class EvaluationMode(str, Enum):
    """How this policy can be decided.

    One field, two values, so a reader asks the question once. It replaces a
    scattering of signals that each answered part of it — a boolean, a
    projection status, a condition provenance code, a readiness verdict — and
    left the reader to reconcile them.

    Neither value is a defect and neither is a grade. Most policy text is not a
    decision table and never will be: an obligation to notify, a delegation of
    authority, a definition, or a rule whose outcome the document reserves to a
    named authority are all complete, correct policy records.
    """

    #: Every condition compiled to a test over named facts, so the
    #: deterministic engine can decide it without a model in the loop.
    DETERMINISTIC = "deterministic"
    #: Grounded and structured, but not reducible to a fact comparison — so it
    #: is decided by reading it against the evidence for a case.
    AI_READY = "ai_ready"


class PolicyFact(BaseModel):
    """Something a policy is measured against, named by the policy itself.

    `name` is derived from `source_phrase`, and the phrase is carried beside it
    so the derivation is always checkable. Neither is a fact *path*: a path
    asserts that some system holds a field at that address, and nothing in a
    document establishes that. This says only that the policy talks about this
    thing, which is what a consumer needs in order to point at where it lives
    in their own data.

    `roles` is a list because one phrase routinely plays several parts in one
    sentence. "The University Council decides on the discount" names the
    Council as both the grammatical subject and the deciding authority, and an
    earlier single-valued `role` kept the first and dropped the second — so a
    consumer asking who decides the rule found nothing, on a rule that says.

    `data_type` is present only when the phrase shows it. Silence means the
    document named the thing without saying what kind of value it holds, which
    is more useful to a consumer than a guess.
    """

    #: Stable identifier derived from the phrase's own words.
    name: str
    #: The document's wording, verbatim.
    source_phrase: str
    #: Every part the phrase plays — `threshold`, `authority`, `subject`, and
    #: so on. Ordered, so the same rule always produces the same list.
    roles: list[str] = Field(default_factory=list)
    #: `money` | `duration` | `number` | `boolean`, or absent.
    data_type: str | None = None


class PolicyAttribute(BaseModel):
    """One attribute the formulator assigned, with the words it assigned.

    Three parts and nothing else: the attribute's own name, the document's
    text, and the identifier a case supplies a value for. Every consumer of a
    policy record — a reviewer checking the extraction, a search API indexing
    it, a judge deciding a case from it — is answering some version of the same
    two questions, and this shape answers both without anything in between.

    `attribute` is the canonical field name, unchanged. Renaming it to
    something friendlier changes what the row asserts: an attempt at plainer
    labels turned `frequency` into "how often" and `assigner` into "decided
    by", and picked prepositions that collided with the prepositions already in
    the source, so a trigger reading "after the trial period has expired" was
    presented as "on after the trial period has expired".

    `text` is verbatim. Not trimmed to fit, not merged with a neighbouring
    attribute, not paraphrased. An earlier presentation glued `modality` and
    `predicate` into "shall not exceed", which reads well and is a string no
    attribute contains.

    `fact` is absent where the document supplies the value itself. That is a
    statement rather than a gap: "(200) two hundred SR per month" is what the
    policy pays, so a case is asked for nothing.
    """

    #: The canonical field name, exactly as the record declares it.
    attribute: str
    #: The document's words for that attribute, verbatim.
    text: str
    #: The fact identifier a case supplies a value for, when there is one.
    fact: str | None = None
    #: `money` | `duration` | `number` | `boolean`, when the fact states one.
    data_type: str | None = None


class PolicyAttributes(BaseModel):
    """A rule's attributes, split into what scopes it and what follows.

    The split is the only structure imposed, and it is the one a reader already
    applies: everything in `applies` narrows when or to whom the rule holds,
    everything in `outcome` says what then happens. Order within each list is
    fixed so two records of the same shape read the same way.
    """

    applies: list[PolicyAttribute] = Field(default_factory=list)
    outcome: list[PolicyAttribute] = Field(default_factory=list)


#: Attributes saying what a rule covers and when it applies, in display order.
APPLIES_ATTRIBUTES: tuple[str, ...] = (
    "subject",
    "beneficiary",
    "recipient",
    "candidate",
    "actor",
    "location",
    "condition",
    "prerequisite",
    "trigger",
    "temporal_constraint",
    "constraint",
)

#: Attributes saying what follows, and who decides or is carved out.
OUTCOME_ATTRIBUTES: tuple[str, ...] = (
    "modality",
    "predicate",
    "object",
    "threshold",
    "calculation",
    "unit",
    "currency",
    "frequency",
    "deadline",
    "sequence",
    "consequence",
    "remedy",
    "assigner",
    "exception",
)

#: A fact's role is named after the field it was read from, with one exception:
#: `assigner` publishes as `authority`, which is the part the party plays
#: rather than the slot it filled.
_ROLE_FOR_ATTRIBUTE: dict[str, str] = {"assigner": "authority"}


def _fact_for_attribute(facts: list[PolicyFact], attribute: str) -> PolicyFact | None:
    """The fact extracted from this attribute, if any.

    Matched on role, never on text. Matching by containment was tried and
    produced false attributions: `per-month`, read from `frequency`, also
    matched "(200) two hundred SR per month" and "at the rate of (200) two
    hundred SR per month", so three attributes appeared to require a value that
    only one of them names.
    """

    role = _ROLE_FOR_ATTRIBUTE.get(attribute, attribute)
    return next((fact for fact in facts if role in fact.roles), None)


def attributes_for(rule: object | None, facts: list[PolicyFact]) -> PolicyAttributes:
    """Pair every populated attribute with its text and its fact.

    Every attribute the record carries appears, including one whose text
    repeats another's. A phrase filling three slots is what the formulator
    wrote — `object`, `threshold` and `calculation` routinely hold the same
    bound — and collapsing them would report the extraction as tidier than it
    is, on exactly the records where a reader most needs to see it.
    """

    if rule is None:
        return PolicyAttributes()

    def rows(names: tuple[str, ...]) -> list[PolicyAttribute]:
        out: list[PolicyAttribute] = []
        for name in names:
            value = getattr(rule, name, None)
            text = value.strip() if isinstance(value, str) else ""
            if not text:
                continue
            fact = _fact_for_attribute(facts, name)
            out.append(
                PolicyAttribute(
                    attribute=name,
                    text=text,
                    fact=fact.name if fact else None,
                    data_type=fact.data_type if fact else None,
                )
            )
        return out

    return PolicyAttributes(applies=rows(APPLIES_ATTRIBUTES), outcome=rows(OUTCOME_ATTRIBUTES))


def _states_its_test(core: object | None) -> bool:
    """Whether the record carries the rule's operative content, anywhere.

    Deliberately generous about *where*, and strict about *whether*. A sentence
    decides which slot carries its test — "shall not exceed 10% of the base"
    puts it in a predicate and a threshold, "begins on the first working day" in
    a temporal constraint, "provided upon promotion" in a trigger — and a check
    that reads only a field named `condition` reports the other two as gaps. It
    did: 29 of 46 records were called incomplete by a check looking in one
    place.
    """

    def text(name: str) -> str:
        value = getattr(core, name, None)
        return value.strip() if isinstance(value, str) else ""

    if core is None:
        return False
    if text("condition") or text("prerequisite") or text("constraint"):
        return True
    if text("trigger") or text("temporal_constraint") or text("deadline"):
        return True
    return bool(text("predicate") and (text("object") or text("threshold")))


def unanswered_for_judge(rule: "CanonicalRule") -> list[str]:
    """What a judge would not find in this record, in its own words.

    An `ai_ready` policy is decided by a judge reading the record, so the record
    has to be sufficient on its own. This names the questions it fails to
    answer; an empty list means it is decidable as written.

    The questions are the ones any consumer is really asking: what does the
    document say, what does the rule require, what must be established about a
    case, what follows, and where did this come from.
    """

    canonical = rule.formulation.canonical if rule.formulation else None
    core = canonical.rule if canonical else None
    missing: list[str] = []
    if not (canonical and (canonical.source_text or "").strip()):
        missing.append("the sentence it came from")
    if not _states_its_test(core):
        missing.append("what it requires")
    if not rule.fact_model:
        missing.append("what a case must establish")
    if not (rule.effect and rule.effect.action):
        missing.append("what follows")
    if not rule.evidence:
        missing.append("a link back to the document")
    return missing


def unrunnable_reasons(rule: "CanonicalRule") -> list[str]:
    """Why a `deterministic` record could not actually be evaluated.

    A record routed to the engine has to be runnable by it. The failure that
    matters is a condition naming a fact the record never declares: the engine
    reaches evaluation, finds the fact absent, and reports a missing input for
    a policy that looked complete.
    """

    reasons: list[str] = []
    condition = rule.condition
    vacuous = getattr(condition, "type", None) == "all" and not getattr(condition, "all", None)
    if vacuous:
        reasons.append("its condition tree is empty")
    if not rule.required_facts:
        reasons.append("it declares no facts to evaluate against")

    declared = {fact.name for fact in rule.required_facts}
    for name in _facts_named_by(condition):
        if name not in declared:
            reasons.append(f"its condition names {name!r}, which it does not declare")
    return reasons


def _facts_named_by(condition: object) -> list[str]:
    """Every fact identifier a condition tree references, at any depth."""

    names: list[str] = []
    fact = getattr(condition, "fact", None)
    if isinstance(fact, str):
        names.append(fact)
    reference = getattr(condition, "reference", None)
    if reference is not None and isinstance(getattr(reference, "fact", None), str):
        names.append(reference.fact)
    for attribute in ("all", "any"):
        for child in getattr(condition, attribute, None) or []:
            names.extend(_facts_named_by(child))
    child = getattr(condition, "not_", None)
    if child is not None:
        names.extend(_facts_named_by(child))
    return names


#: Every code `condition_provenance` can put on a record.
#:
#: The list was a prose comment on the field, which is a definition only a human
#: can read. The code is emitted by one module and turned into words by another
#: — in a different language, in a different tree — and the two drift the moment
#: a sixth case is added: the record still routes correctly and the interface
#: showing it has nothing to say. Declaring the set here gives a test something
#: to enumerate, so the drift fails a build instead of reaching a reviewer.
#:
#: Deliberately not a `Literal` on `code`. That would make pydantic reject a
#: record carrying a code this version has never heard of, and records outlive
#: the code that wrote them — a stored rule from an older or newer writer must
#: still parse. The set is a declaration of what *we* emit, not a gate on what
#: we accept.
CONDITION_PROVENANCE_CODES: Final[tuple[str, ...]] = (
    "derived",
    "derived_from_stated_bound",
    "derived_from_stated_quantity",
    "conditions_not_projected",
    "conditions_not_representable",
    "no_scope_derived",
    # A quantity reached the record and did not become a condition. Each code
    # names what the source supplied instead of a test. Until these existed the
    # whole set collapsed into `no_scope_derived` — "the source states no test"
    # — which was untrue of a rule carrying a threshold and a unit, and left a
    # reviewer no way to find the rules worth a second look.
    "quantity_states_a_range",
    "quantity_states_no_comparison",
    "quantity_not_read_as_number",
    "proportion_has_no_stated_base",
)


class ConditionProvenance(BaseModel):
    """Why a rule's condition tree looks the way it does.

    A code, not a sentence. An empty `all: []` tree means either "this rule
    genuinely applies always" or "this rule has conditions we did not encode",
    and reading the second as the first turns a narrow permission into an open
    one — so the distinction has to be carried somewhere a consumer can branch
    on, count and filter.

    It carried a `message` until the served records were read end to end. Every
    one restated the condition already present in the record and then told the
    reader what to do about it — "a reviewer must supply the missing mapping" —
    which is a workflow instruction, not a property of the policy. Nine
    kilobytes of it across forty-six records, addressed to a reviewer, in a
    document whose consumer is a search API and a judge. The code says which of
    the four cases this is; anything a human should read about it belongs in
    the interface that shows it to them.

    `unsupported_expression` stays, because it is the agent's own output rather
    than a description of it: a reviewer sees the exact text that would not
    compile.
    """

    #: One of `CONDITION_PROVENANCE_CODES`, declared above. Anything a human
    #: should read about it belongs in the interface that shows it to them.
    code: str
    unsupported_expression: str = ""
    #: The document's own wording for a quantity that reached the record and did
    #: not compile into a comparison. Kept for the same reason as
    #: `unsupported_expression`: it is the source's text, not a description of
    #: it, so a reviewer sees exactly what was read and can judge the refusal
    #: rather than take it on trust.
    unprojected_quantity: str = ""

    @property
    def is_platform_limitation(self) -> bool:
        """True when the configuration was sufficient and the compiler was not.

        The distinction a reviewer acts on: everything else in this model asks
        them to supply something, and this one asks them to wait for an
        engineering change.
        """

        return self.code == "conditions_not_representable"


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
    #: How this policy can be decided: `deterministic` or `ai_ready`.
    #: Derived on read from the condition and its required facts, so it can
    #: never disagree with the tree it describes.
    evaluation_mode: EvaluationMode = EvaluationMode.AI_READY
    #: The things this policy is measured against, named by the policy itself.
    #: Empty when the sentence names none — a definition, for instance.
    fact_model: list[PolicyFact] = Field(default_factory=list)
    #: Every attribute the formulator assigned, paired with the document's own
    #: words and the fact a case supplies for it. Derived on read from the
    #: canonical record, so the served JSON and anything rendering it are the
    #: same table rather than two readings of one.
    attributes: PolicyAttributes = Field(default_factory=PolicyAttributes)
    #: Why `condition` is what it is. Absent on hand-authored rules, which have
    #: no formulation to derive it from.
    condition_provenance: ConditionProvenance | None = None
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
    # Typed links discovery found but could not confirm. Kept separate from
    # `related_rule_ids`, which stays confirmed-only: a candidate is a lead for
    # a reviewer, and promoting one to a stated relationship would assert
    # something the evidence does not support.
    #
    # They were previously discarded outright — `ai_extraction` dropped every
    # edge whose state was not `confirmed` — so a rule linked only by candidate
    # evidence was reported isolated. On AD-103 that overstated isolation by 5
    # rules (21 against 16) and lost 6 `definition_used_by` links, which are
    # exactly the links a non-executable rule most needs: a definition cannot
    # be grouped by a shared fact comparison, because it has no facts.
    candidate_relationships: list[CandidateRelationship] = Field(default_factory=list)
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
    # The three-layer XACML view: what the source states, whether this
    # deployment can supply the attributes, and — always None — what a PDP
    # returned. Derived on read from `formulation.canonical` for the same
    # reason `decision_readiness` is, and kept beside it so a consumer reading
    # one cannot miss the other.
    #
    # Typed loosely here to keep `contracts.policy` free of a dependency on the
    # projection module; the shape is `contracts.xacml_projection.PolicyXacmlView`.
    xacml_view: object | None = None


class ApprovedPolicyPackage(BaseModel):
    """An immutable, approved policy version — the unit the evaluator consumes."""

    schema_version: str = CANONICAL_SCHEMA_VERSION
    policy_set_id: str
    policy_version_id: str
    effective_from: date
    effective_to: date | None = None
    rules: list[CanonicalRule] = Field(default_factory=list)
    aggregate_limits: list[AggregateLimit] = Field(default_factory=list)
