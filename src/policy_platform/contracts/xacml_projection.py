"""XACML 3.0 projection with its three layers kept apart.

The layers this separates were previously collapsed into one display, and the
collapse produced materially wrong XACML:

1. **Source semantics** — what the document states. "after the trial period has
   expired" states a complete predicate; "depending on the financial position
   of the University" names a dependency and never says what qualifies.
2. **Fact-model readiness** — whether this deployment can supply the attribute.
   A design-time property of *our* configuration, not of the policy.
3. **Runtime evaluation** — Permit / Deny / NotApplicable / Indeterminate.
   These are what a PDP returns after evaluating a request. Nothing here may
   predict one.

The specific defect: a condition the source stated perfectly well was being
badged `Indeterminate · missing-attribute` because no fact model covered it.
That is three errors at once — it reports a runtime result at extraction time,
it blames the document for a gap in our configuration, and `missing-attribute`
is a status a PDP raises when it cannot *obtain* an attribute during
evaluation, which has not happened. A reviewer reading it concludes the policy
is unclear when the policy was clear and the fact model was empty.

`runtime_evaluation` exists on the output and is always `None` here. It is
present rather than omitted so the absence is visible: a reader can see that
the layer exists and has not been reached, instead of inferring from silence.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RuleEffect(str, Enum):
    """A XACML Rule Effect. There are exactly two.

    XACML 3.0 §5.28: a `<Rule>` carries `Effect="Permit"` or `Effect="Deny"`.
    `NotApplicable` and `Indeterminate` are *decision results* a PDP produces
    (§7.2.x); they can never be a declared Effect, and storing one means the
    policy asserts a decision the standard has no way to express.

    Modelled as a two-member enum on purpose. The previous mapping produced
    `Effect = NotApplicable` for informational rules, and a wider type is what
    let that be written down at all — with this enum the malformed state is
    unrepresentable rather than merely discouraged. A rule that grants and
    refuses nothing carries `effect=None`, which is not the same as
    NotApplicable: it says this statement is not a XACML Rule.
    """

    PERMIT = "Permit"
    DENY = "Deny"


class PredicateStatus(str, Enum):
    """Whether the *source* defined a testable predicate.

    Entirely about the document. Independent of whether this deployment can
    supply the attribute — that is `FactModelStatus`, and conflating the two is
    the defect this module exists to fix.
    """

    #: The source states a complete test. "after the trial period has expired"
    #: means `trial-period-expired = true`; nothing has to be invented to know
    #: what would satisfy it.
    RESOLVED = "resolved"
    #: The source names a dependency but never says what qualifies. "depending
    #: on the financial position of the University" establishes that financial
    #: position matters and does not say whether that means a threshold, a
    #: boolean, or a judgement. Inventing `financial-position = good` would
    #: manufacture a test the policy never wrote.
    UNRESOLVED = "unresolved"


class FactModelStatus(str, Enum):
    """Whether this deployment can supply the attribute.

    A property of our configuration, not of the policy. `missing` is a normal
    state for a freshly-extracted document and is never evidence that the
    source was unclear.
    """

    MAPPED = "mapped"
    MISSING = "missing"
    #: More than one candidate attribute could serve, and choosing would be a
    #: guess about which the document meant.
    AMBIGUOUS = "ambiguous"


class EntityRole(str, Enum):
    """XACML 3.0 attribute categories, plus an honest "we do not know".

    Classification never rests on grammatical position alone. "The allowance
    will be calculated" and "The employee shall submit" have the same shape
    and different roles, so the previous rule — grammatical subject becomes
    `subject.subject-id` — put allowances, benefits and whole sentences into
    the XACML subject.
    """

    #: `urn:oasis:names:tc:xacml:1.0:subject-category:access-subject`
    SUBJECT = "subject"
    #: `urn:oasis:names:tc:xacml:3.0:attribute-category:resource`
    RESOURCE = "resource"
    #: `urn:oasis:names:tc:xacml:3.0:attribute-category:action`
    ACTION = "action"
    #: `urn:oasis:names:tc:xacml:3.0:attribute-category:environment`
    ENVIRONMENT = "environment"
    #: Named by the source, and the evidence does not establish which category
    #: it belongs to. Kept rather than forced: an unclassified entity a
    #: reviewer can see beats a confident wrong category they will not check.
    UNCLASSIFIED = "unclassified"


class NormativeModality(str, Enum):
    """What the source obliges, permits or forbids.

    Preserved separately from the XACML Effect because the two do not
    correspond one-to-one. "shall", "must", "is paid" and "will be calculated"
    are not all Permit — an obligation projects to a Permit whose mandatory
    behaviour lives in an ObligationExpression, and treating the modal word as
    the decision loses the distinction.
    """

    PERMISSION = "permission"
    PROHIBITION = "prohibition"
    OBLIGATION = "obligation"
    ENTITLEMENT = "entitlement"
    ELIGIBILITY = "eligibility"
    CALCULATION_REQUIREMENT = "calculation_requirement"
    DEPENDENCY = "dependency"
    #: States meaning rather than conduct. Projects to no Rule at all.
    DEFINITION = "definition"


class CompilationStatus(str, Enum):
    """How much of this rule could become an executable XACML Rule.

    Deliberately not a decision value. `not_executable` says our compiler
    could not build the expression; it says nothing about what a PDP would
    return, because no PDP has run.
    """

    EXECUTABLE = "executable"
    PARTIALLY_EXECUTABLE = "partially_executable"
    NOT_EXECUTABLE = "not_executable"


class ClassifiedEntity(BaseModel):
    """One phrase from the source, and what it is.

    `phrase` is verbatim. `basis` records why the role was chosen, so a
    reviewer can check the classification rather than accept it — the previous
    implementation offered no way to tell an evidenced role from a default.
    """

    phrase: str
    role: EntityRole
    #: Short, checkable justification: which canonical field it came from, or
    #: which rule assigned the role.
    basis: str
    #: Normalised identifier when one could be derived without inventing
    #: meaning — `grant`, `calculate`. None when nothing in the closed
    #: vocabulary matched, which is commoner than not and is not a failure.
    normalized_id: str | None = None


class SourceCondition(BaseModel):
    """One condition the source states, and how completely it states it.

    The two statuses are independent and both are always present. A condition
    can be perfectly stated and unmappable (`resolved` + `missing`), vaguely
    stated and mappable (`unresolved` + `mapped`), or any other combination.
    Collapsing them is what produced `Indeterminate · missing-attribute` on
    conditions the document had expressed clearly.
    """

    #: The condition as the source wrote it, verbatim.
    source_text: str
    #: The concept the condition is about, as a stable identifier where one
    #: could be derived — `trial-period-expired`, `university-financial-position`.
    concept: str
    predicate_status: PredicateStatus
    #: The comparison, when `predicate_status` is `resolved`. Left None for
    #: `unresolved`: a rule that names a dependency without stating its test
    #: has no operator, and supplying one would manufacture the policy.
    operator: str | None = None
    value: str | None = None
    #: Why the predicate is unresolved, for a reviewer deciding whether to go
    #: back to the document or to the policy owner.
    unresolved_reason: str | None = None
    fact_model_status: FactModelStatus = FactModelStatus.MISSING


class ObligationExpression(BaseModel):
    """Mandatory PEP behaviour attached to a decision. XACML 3.0 §7.18.

    Distinct from Advice, which a PEP may ignore. A calculation the source
    requires ("the allowance will be calculated based on the higher basic
    salary of the couple") is an Obligation, not Advice — Advice is not a
    bucket for normative text the classifier could not place.
    """

    obligation_id: str
    fulfill_on: RuleEffect = RuleEffect.PERMIT
    attributes: dict[str, str] = Field(default_factory=dict)


class AdviceExpression(BaseModel):
    """Supplementary guidance a PEP may ignore. XACML 3.0 §7.18."""

    advice_id: str
    fulfill_on: RuleEffect = RuleEffect.PERMIT
    attributes: dict[str, str] = Field(default_factory=dict)


class SourceSemantics(BaseModel):
    """What the document states, before any XACML question is asked."""

    subjects: list[ClassifiedEntity] = Field(default_factory=list)
    resources: list[ClassifiedEntity] = Field(default_factory=list)
    action: ClassifiedEntity | None = None
    conditions: list[SourceCondition] = Field(default_factory=list)
    normative_modality: NormativeModality | None = None
    #: What the rule yields, verbatim. Not a resource and not an action.
    outcome: str | None = None
    unclassified: list[ClassifiedEntity] = Field(default_factory=list)


class XacmlTarget(BaseModel):
    """Coarse applicability matching. XACML 3.0 §5.5.

    Only entities whose role is established go in. Boolean policy logic
    belongs in Condition, not here — forcing every condition into Target
    changes what the rule matches rather than what it decides.
    """

    subject_ids: list[str] = Field(default_factory=list)
    resource_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)


class XacmlProjection(BaseModel):
    """The XACML view of the rule. No runtime result appears here."""

    target: XacmlTarget = Field(default_factory=XacmlTarget)
    #: Conditions, in the same order the source stated them.
    condition: list[SourceCondition] = Field(default_factory=list)
    #: Permit, Deny, or None when the statement is not a XACML Rule at all
    #: (a definition grants and refuses nothing). Never NotApplicable.
    effect: RuleEffect | None = None
    #: Why the effect is what it is, or why there is none.
    effect_basis: str = ""
    obligation_expressions: list[ObligationExpression] = Field(default_factory=list)
    advice_expressions: list[AdviceExpression] = Field(default_factory=list)
    compilation_status: CompilationStatus = CompilationStatus.NOT_EXECUTABLE


class RequiredAttribute(BaseModel):
    """One attribute the rule needs, and whether we can supply it."""

    attribute_id: str
    status: FactModelStatus
    #: The source phrase that gave rise to it, verbatim, so a reviewer mapping
    #: it to a customer schema can see what it has to mean.
    source_phrase: str


class FactModelReadiness(BaseModel):
    """Whether this deployment can evaluate the rule. Never a decision."""

    required_attributes: list[RequiredAttribute] = Field(default_factory=list)

    @property
    def missing(self) -> list[RequiredAttribute]:
        return [a for a in self.required_attributes if a.status is FactModelStatus.MISSING]

    @property
    def ready(self) -> bool:
        return not self.missing


class PolicyXacmlView(BaseModel):
    """The four layers, kept apart.

    `runtime_evaluation` is always None at extraction and is present rather
    than omitted so a reader can see the layer exists and has not been
    reached. Only a PDP evaluating an actual request may fill it, and when it
    does the value may legitimately be Indeterminate with a missing-attribute
    status — which is exactly the state this module refuses to predict.
    """

    source_semantics: SourceSemantics = Field(default_factory=SourceSemantics)
    xacml_projection: XacmlProjection = Field(default_factory=XacmlProjection)
    fact_model_readiness: FactModelReadiness = Field(default_factory=FactModelReadiness)
    runtime_evaluation: None = None
