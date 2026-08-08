"""Contracts for the policy formulator agent's two outputs.

The formulator agent (`infrastructure.policy_formulator`) turns raw policy
prose into two paired representations, per the "ENTERPRISE POLICY EXTRACTION
AND DECISION ENGINE" specification the platform runs as that agent's system
prompt:

1. **CANONICAL_JSON** — what the source policy *says*, decomposed as
   subject / predicate / object plus explicitly-stated qualifiers. Always
   authoritative (spec Section 8, "canonical before executable").
2. **DMN_JSON** — an OMG DMN 1.5 / FEEL *projection*: how an eligible business
   decision could be evaluated. Explicitly NOT a normative DMN document — the
   spec (Section 1) requires it be described as a "DMN-compatible JSON IR"
   intended for deterministic downstream compilation into DMN 1.5 XML.

Two structural rules from the spec are enforced here *by construction* rather
than by discipline, because both are easy to violate accidentally and
impossible to spot by eye in a large payload:

- **Section 22 / 93 — absent information is OMITTED, never `null`,
  `"unknown"`, `"N/A"`, `"not specified"` or `"none"`.** Every model below
  inherits `_OmitEmptyModel`, whose serializer drops `None` and empty
  collections on *every* serialization path. Declaring a field `str | None`
  and trusting callers to remember `exclude_none=True` would leak nulls the
  moment any one call site forgot.
- **Sections 93 / 94 — mandatory property ordering.** Pydantic preserves field
  *declaration* order in `model_dump()`, so the declaration order in each model
  below IS the wire order. Do not alphabetize or "tidy" these fields.

Distinct from `contracts.policy.CanonicalRule`, which is this platform's own
ABAC/XACML-shaped executable rule (condition AST + effect + scope) that the
deterministic evaluator consumes. A formulation *describes* a policy; a
`CanonicalRule` is *runnable*. `infrastructure.ai_extraction` derives the
latter from the former in Python, never in the model (spec Section 82,
"deterministic application responsibilities").
"""
from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer


class _OmitEmptyModel(BaseModel):
    """Base model whose serialization omits absent values entirely.

    Implements spec Section 22 ("never write null / unknown / N/A /
    not specified / none for absent canonical semantic fields — simply omit
    them") as a serializer rather than a convention, so no call site can
    reintroduce nulls by forgetting a flag.

    Empty lists and dicts are dropped for the same reason: an omitted
    `ambiguity` and an `ambiguity: []` are the same claim, and the spec asks
    for the absent form. Fields that are *contractually always present* even
    when empty (e.g. a DMN decision's `requirements`, or the top-level
    `canonical_policies`) opt back in via `always_emit`.
    """

    model_config = ConfigDict(populate_by_name=True)

    #: Field names that must survive serialization even when empty, because the
    #: spec's output contract names them as always-present keys. `ClassVar` so
    #: pydantic treats it as configuration, not as a serialized model field.
    always_emit: ClassVar[frozenset[str]] = frozenset()

    @model_serializer(mode="wrap")
    def _drop_absent(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        keep = type(self).always_emit
        return {
            key: value
            for key, value in data.items()
            if key in keep or not (value is None or value == [] or value == {})
        }


class ExtractionStatus(str, Enum):
    """Spec Sections 36 / 38 — how completely a source statement was decomposed."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    AMBIGUOUS = "ambiguous"


class CanonicalRuleType(str, Enum):
    """Spec Section 9's closed vocabulary.

    Deliberately NOT reusing `contracts.policy.RuleType`: that enum describes
    this platform's *evaluator* semantics (routing, escalation, retention…),
    whereas these are the deontic/decision categories the specification
    defines. They overlap on obligation/prohibition/permission but are not the
    same list, and collapsing them would silently discard the distinction the
    spec draws between, say, `eligibility` and `entitlement` (Section 66
    explicitly forbids converting one into the other).
    """

    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"
    ENTITLEMENT = "entitlement"
    ELIGIBILITY = "eligibility"
    INELIGIBILITY = "ineligibility"
    CONDITIONAL_OUTCOME = "conditional_outcome"
    CALCULATION = "calculation"
    CLASSIFICATION = "classification"
    RECOMMENDATION = "recommendation"
    DEFINITION = "definition"
    NON_NORMATIVE = "non_normative"
    AMBIGUOUS = "ambiguous"


class AmbiguityCode(str, Enum):
    """Spec Section 36's controlled ambiguity vocabulary."""

    AMBIGUOUS_SUBJECT = "AMBIGUOUS_SUBJECT"
    AMBIGUOUS_PREDICATE = "AMBIGUOUS_PREDICATE"
    AMBIGUOUS_OBJECT = "AMBIGUOUS_OBJECT"
    AMBIGUOUS_CONDITION = "AMBIGUOUS_CONDITION"
    AMBIGUOUS_THRESHOLD = "AMBIGUOUS_THRESHOLD"
    AMBIGUOUS_RANGE = "AMBIGUOUS_RANGE"
    AMBIGUOUS_PRECEDENCE = "AMBIGUOUS_PRECEDENCE"
    AMBIGUOUS_MODALITY = "AMBIGUOUS_MODALITY"
    AMBIGUOUS_REFERENCE = "AMBIGUOUS_REFERENCE"
    AMBIGUOUS_RULE_BOUNDARY = "AMBIGUOUS_RULE_BOUNDARY"
    AMBIGUOUS_DECISION_SEMANTICS = "AMBIGUOUS_DECISION_SEMANTICS"


class DmnMappingStatus(str, Enum):
    """Spec Section 45 — exactly these five, no others."""

    EXECUTABLE = "executable"
    ENRICHMENT_REQUIRED = "enrichment_required"
    NOT_DIRECTLY_MAPPABLE = "not_directly_mappable"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"


class DmnRequirementCode(str, Enum):
    """Spec Section 46 — deterministic codes naming what enrichment is missing.

    These are the machine-readable reason a policy did NOT become executable,
    which is what makes `enrichment_required` actionable rather than a dead
    end: each code maps to a specific piece of trusted configuration
    (Section 83) an operator can supply to unblock it.
    """

    FACT_MODEL_REQUIRED = "FACT_MODEL_REQUIRED"
    OUTPUT_MODEL_REQUIRED = "OUTPUT_MODEL_REQUIRED"
    DATA_TYPE_REQUIRED = "DATA_TYPE_REQUIRED"
    OPERATOR_AMBIGUOUS = "OPERATOR_AMBIGUOUS"
    VALUE_NORMALIZATION_REQUIRED = "VALUE_NORMALIZATION_REQUIRED"
    UNIT_REQUIRED = "UNIT_REQUIRED"
    CURRENCY_REQUIRED = "CURRENCY_REQUIRED"
    TEMPORAL_MODEL_REQUIRED = "TEMPORAL_MODEL_REQUIRED"
    HIT_POLICY_REQUIRED = "HIT_POLICY_REQUIRED"
    RULE_PRECEDENCE_REQUIRED = "RULE_PRECEDENCE_REQUIRED"
    RULE_OVERLAP_RESOLUTION_REQUIRED = "RULE_OVERLAP_RESOLUTION_REQUIRED"
    DECISION_CONTEXT_REQUIRED = "DECISION_CONTEXT_REQUIRED"
    LOGICAL_RELATIONSHIP_AMBIGUOUS = "LOGICAL_RELATIONSHIP_AMBIGUOUS"


#: Spec Sections 58-63. OMG DMN 1.5's hit policies, spelled as the spec spells
#: them. Section 57 warns against picking one just because a table needs one;
#: Section 64 requires `enrichment_required` instead when rule interaction is
#: not explicit in the source.
DmnHitPolicy = Literal[
    "UNIQUE",
    "ANY",
    "FIRST",
    "PRIORITY",
    "COLLECT",
    "RULE ORDER",
    "OUTPUT ORDER",
]


class CanonicalEvidence(_OmitEmptyModel):
    """Spec Section 37 — verbatim source spans backing each canonical value.

    This is what makes a formulation auditable: every decomposed element can be
    pointed back at the exact words it came from, so a reviewer can check the
    decomposition without re-reading the whole document. The spec is explicit
    that these must be source text, never explanatory prose.
    """

    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    condition: str | None = None


class CanonicalPolicyRule(_OmitEmptyModel):
    """Spec Sections 20-21 — the subject/predicate/object core plus qualifiers.

    Field order below is mandated verbatim by Section 93 and is the wire order.
    Every field after `object` is optional and must be present ONLY when the
    source explicitly supports it (Section 21: "do not populate fields merely
    because the schema supports them").
    """

    rule_type: CanonicalRuleType
    subject: str | None = None
    modality: str | None = None
    predicate: str | None = None
    object: str | None = None
    actor: str | None = None
    beneficiary: str | None = None
    candidate: str | None = None
    recipient: str | None = None
    assigner: str | None = None
    trigger: str | None = None
    condition: str | None = None
    constraint: str | None = None
    threshold: str | None = None
    temporal_constraint: str | None = None
    frequency: str | None = None
    deadline: str | None = None
    location: str | None = None
    exception: str | None = None
    prerequisite: str | None = None
    sequence: str | None = None
    consequence: str | None = None
    remedy: str | None = None
    calculation: str | None = None
    unit: str | None = None
    currency: str | None = None
    source_origin: str | None = None


class CanonicalPolicy(_OmitEmptyModel):
    """One extracted policy statement. Spec Sections 38 / 93.

    `source_text` is preserved verbatim (Section 7) and is the anchor for the
    whole record: the platform shows it to reviewers as the ground truth the
    decomposition must be checked against.
    """

    always_emit: ClassVar[frozenset[str]] = frozenset({"source_text", "extraction_status"})

    source_text: str = ""
    extraction_status: ExtractionStatus = ExtractionStatus.COMPLETE
    rule: CanonicalPolicyRule | None = None
    evidence: CanonicalEvidence | None = None
    # `relationships` and `missing_components` are named in the spec's field
    # order (Section 93) but their element shape is never defined anywhere in
    # the specification. They are therefore typed permissively and preserved
    # verbatim: rejecting an otherwise-valid formulation because an undefined
    # field arrived as an object rather than a string would discard real
    # extraction work over a detail the standard leaves open.
    relationships: list[Any] = Field(default_factory=list)
    ambiguity: list[AmbiguityCode] = Field(default_factory=list)
    missing_components: list[Any] = Field(default_factory=list)

    @field_validator("extraction_status", mode="before")
    @classmethod
    def _coerce_extraction_status(cls, value: Any) -> Any:
        """Fall back to `incomplete` for an unrecognized status word.

        The spec's vocabulary (Section 36) is exactly `complete` /
        `incomplete` / `ambiguous`, but the agent occasionally reaches for a
        close synonym (observed: `"partial"`). Failing the whole formulation
        over a word choice discards every other, correctly-shaped canonical
        policy in the same batch. `incomplete` is the conservative reading of
        any unrecognized status - it never claims a decomposition is done when
        the agent's own wording suggests otherwise.
        """

        if isinstance(value, str) and value not in {s.value for s in ExtractionStatus}:
            return ExtractionStatus.INCOMPLETE
        return value

    @field_validator("ambiguity", mode="before")
    @classmethod
    def _coerce_ambiguity_entries(cls, value: Any) -> Any:
        """Accept a bare code alongside the model's occasional `{code, ...}` form.

        The spec's own vocabulary (Section 36) is a flat list of codes, but the
        agent sometimes "helpfully" enriches an entry into an object carrying
        the code plus commentary (e.g. `{"code": "AMBIGUOUS_PREDICATE", "note":
        "..."}`). Same principle as `relationships`/`missing_components` above:
        discarding an entire formulation over a recoverable shape variance
        would lose real extraction work over a detail the enrichment adds, not
        removes. Only the code is contractual here, so only it is kept.

        The enrichment also appears one level up, wrapping the whole list in an
        object with a plural key plus commentary — observed as
        `{"codes": [...], "evidence": "the following:"}`. That is the same
        gesture applied to the collection rather than the entry, so it is
        unwrapped the same way and for the same reason.
        """

        if isinstance(value, dict):
            for key in ("codes", "code", "values", "items"):
                inner = value.get(key)
                if isinstance(inner, list):
                    value = inner
                    break
                if isinstance(inner, str):
                    value = [inner]
                    break
        if not isinstance(value, list):
            return value
        coerced = []
        for item in value:
            if isinstance(item, dict) and "code" in item:
                coerced.append(item["code"])
            else:
                coerced.append(item)
        return coerced


class DmnTableInput(_OmitEmptyModel):
    """One decision-table input column. Spec Section 54.

    `expression` is a FEEL fact path and may ONLY come from the supplied
    fact model (Sections 42-43) — the spec forbids inventing fact paths, which
    is why an absent fact model yields `FACT_MODEL_REQUIRED` rather than a
    plausible-looking guess.
    """

    label: str | None = None
    expression: str | None = None
    type: str | None = None


class DmnTableOutput(_OmitEmptyModel):
    """One decision-table output column. Spec Section 55."""

    label: str | None = None
    name: str | None = None
    type: str | None = None


class DmnTableRule(_OmitEmptyModel):
    """One decision-table row. Spec Section 56.

    Entries are FEEL unary tests / expressions positionally aligned with the
    table's `inputs` and `outputs`.
    """

    always_emit: ClassVar[frozenset[str]] = frozenset({"input_entries", "output_entries"})

    input_entries: list[str] = Field(default_factory=list)
    output_entries: list[str] = Field(default_factory=list)


class DmnDecisionTable(_OmitEmptyModel):
    """A DMN decision table. Spec Sections 53-56."""

    always_emit: ClassVar[frozenset[str]] = frozenset({"inputs", "outputs", "rules"})

    hit_policy: DmnHitPolicy | None = None
    inputs: list[DmnTableInput] = Field(default_factory=list)
    outputs: list[DmnTableOutput] = Field(default_factory=list)
    rules: list[DmnTableRule] = Field(default_factory=list)


class DmnLiteralOutput(_OmitEmptyModel):
    """Output descriptor for a literal expression. Spec Section 87."""

    name: str | None = None
    type: str | None = None


class DmnLiteralExpression(_OmitEmptyModel):
    """A single FEEL expression instead of a table. Spec Sections 71-72, 87."""

    output: DmnLiteralOutput | None = None
    feel: str | None = None


class DmnSemanticProjection(_OmitEmptyModel):
    """Source-grounded description used when execution can't be generated.

    Spec Sections 88-90. This is the honest middle ground the specification
    insists on: when a policy is decision-like but the fact model is missing,
    or the source is ambiguous, the engine still records the *meaning* it
    found — it simply refuses to dress it up as executable FEEL. Section 88 is
    explicit that this "must not contain invented executable facts".

    Shapes differ by status (conditions/outcome for `enrichment_required`;
    rule_type/subject/predicate/object for `not_directly_mappable`;
    condition_source/outcome_source for `ambiguous`), so all variants are
    optional here and the absent ones are omitted on serialization.
    """

    rule_type: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    conditions: list[str] = Field(default_factory=list)
    outcome: str | None = None
    condition_source: str | None = None
    outcome_source: str | None = None

    @field_validator(
        "subject",
        "predicate",
        "object",
        "outcome",
        "condition_source",
        "outcome_source",
        mode="before",
    )
    @classmethod
    def _coerce_source_to_string(cls, value: Any) -> Any:
        """Join a list-shaped projection field into one descriptive string.

        These fields describe *where in the source text* a condition/outcome
        came from, or what the outcome itself is (Sections 88-90). When the
        source is a DOCX table (e.g. an SLA/severity matrix), the agent
        sometimes projects a whole column as the value instead of a single
        joined phrase — e.g. `["P1 - Critical", "P2 - High", ...]` rather than
        `"P1 - Critical | P2 - High | ..."`. The list still names the same
        source material, so joining it preserves the citation instead of
        discarding the whole formulation over a formatting choice.

        The subject/predicate/object triple is covered for the same reason and
        with sharper evidence: a real extraction lost a whole batch to
        `object: ["modest", "loose", "opaque"]`, where the source listed three
        adjectives and the agent kept them apart rather than joining them. The
        triple is one semantic unit, so covering `object` alone would leave the
        identical gesture fatal on the two fields beside it.

        Coverage stops at this model deliberately. `_salvage_valid_policies`
        already limits a malformed *canonical* policy to costing itself, but a
        projection that fails validation re-raises for the whole batch, so a
        shape variance here has a blast radius two orders larger than the same
        variance one model over. That difference in consequence — not a general
        preference for lenient parsing — is what justifies coercing here.
        """

        if isinstance(value, list):
            return " | ".join(str(item) for item in value) or None
        return value


class DmnDecision(_OmitEmptyModel):
    """One decision in the DMN projection. Field order per Section 94.

    `source_rule_indexes` are zero-based positions into
    `PolicyFormulation.canonical_policies` (Section 86), which is what keeps
    the projection traceable back to the canonical record — several canonical
    rules may legitimately collapse into one decision table (Section 91).

    `decision_table` stays an explicit `None` rather than being omitted when a
    status contract requires it (Section 94's stated exception to the
    omit-absent rule), so `always_emit` includes it.
    """

    always_emit: ClassVar[frozenset[str]] = frozenset(
        {"source_rule_indexes", "dmn_mapping_status", "requirements", "decision_table"}
    )

    source_rule_indexes: list[int] = Field(default_factory=list)
    dmn_mapping_status: DmnMappingStatus = DmnMappingStatus.NOT_APPLICABLE
    requirements: list[DmnRequirementCode] = Field(default_factory=list)
    semantic_projection: DmnSemanticProjection | None = None
    decision_table: DmnDecisionTable | None = None
    literal_expression: DmnLiteralExpression | None = None
    dependencies: list[str] = Field(default_factory=list)


class DmnProjection(_OmitEmptyModel):
    """The DMN_JSON wrapper. Spec Sections 85 / 94.

    The three constant fields are not decoration: Section 1 forbids claiming
    the JSON is a normative DMN document, so `representation` must keep saying
    "DMN-compatible JSON IR" wherever this payload travels.
    """

    always_emit: ClassVar[frozenset[str]] = frozenset(
        {"standard", "expression_language", "representation", "decisions"}
    )

    standard: str = "OMG DMN 1.5"
    expression_language: str = "FEEL"
    representation: str = "DMN-compatible JSON IR"
    decisions: list[DmnDecision] = Field(default_factory=list)


class PolicyFormulation(_OmitEmptyModel):
    """The formulator agent's complete, validated output for one input text.

    Pairs the authoritative canonical record with its DMN projection. Stored
    verbatim on the rules the agent produces so reviewers (and the audit
    trail) can see exactly what the agent formulated, independent of the
    executable `CanonicalRule` the platform derives from it.
    """

    always_emit: ClassVar[frozenset[str]] = frozenset({"canonical_policies", "dmn_projection"})

    canonical_policies: list[CanonicalPolicy] = Field(default_factory=list)
    dmn_projection: DmnProjection = Field(default_factory=DmnProjection)

    def decisions_for(self, index: int) -> list[DmnDecision]:
        """Return the DMN decisions covering the canonical policy at `index`."""

        return [d for d in self.dmn_projection.decisions if index in d.source_rule_indexes]


class RuleFormulation(_OmitEmptyModel):
    """One platform rule's slice of a formulation, carried on the rule itself.

    A `PolicyFormulation` covers a whole batch of source text, whereas a
    platform `CanonicalRule` is one rule. This is the per-rule projection of
    that batch: the single canonical policy the rule was derived from, plus
    the DMN decision(s) that reference it.

    `source_index` is retained deliberately. A DMN decision may legitimately
    span several canonical rules (spec Section 91 — e.g. three approval bands
    collapsing into one decision table), so its `source_rule_indexes` are kept
    exactly as the agent emitted them rather than rebased to zero. Without
    `source_index` a reader could not tell *which* of a shared decision's rows
    belongs to this rule; with it, the correspondence stays unambiguous and
    the traceability the spec requires (Section 86) survives the slicing.
    """

    always_emit: ClassVar[frozenset[str]] = frozenset({"source_index"})

    source_index: int = 0
    canonical: CanonicalPolicy | None = None
    dmn_decisions: list[DmnDecision] = Field(default_factory=list)
