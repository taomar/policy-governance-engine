"""``PolicyDocumentGraphV1`` — the versioned candidate-discovery schema.

This is the Docling Graph extraction template. It defines what the extraction
run is asked to *look for*, and therefore also the shape of the candidate graph
that comes back.

WHAT THIS SCHEMA IS AND IS NOT
------------------------------
It is a **discovery** schema. Everything it produces is a candidate: a proposal
that some region of the document contains a definition, an obligation, an
exception, an approval. Nothing here is authoritative, nothing here is evidence,
and nothing becomes approved policy merely because extraction succeeded.

It is deliberately *not* the canonical rule model. `contracts/formulation.py`
already owns that, and it is reached only after exact spans have been resolved
from the canonical document and a reviewer has approved the semantics. Trying to
make one schema serve both jobs would put unverified model output into the same
type as approved policy, which is precisely the confusion the two-layer design
exists to prevent.

DOMAIN NEUTRALITY
-----------------
The node families describe how *policy documents* are written — definitions,
scope, obligations, conditions, exceptions, approvals, tables, footnotes,
cross-references — not what any particular policy is about. Nothing here
mentions leave, security, hardware, or any other subject matter. A schema tuned
to the sample documents would score well on them and fail on the next document,
which the directive explicitly forbids.

IDENTITY
--------
Docling Graph needs a short, scalar, document-derived identity per entity so it
can merge duplicates across chunks. That identity is *graph-local bookkeeping*.
It must never become a canonical policy identity: the directive's zero-tolerance
gate forbids identity derived from generated labels, filename stems, graph node
labels, model list position, or root fallbacks. Canonical identity is computed
later, from verified spans, by `contracts/element_identity.py`.

Each entity therefore carries a ``*_key`` field holding either the label the
document itself prints (``"2.1"``, ``"Eligible Employee"``) or, for unnamed
units, the canonical element reference. Both are document-derived and stable;
neither is invented by the model.

TOLERANCE
---------
Every field except the identity key is optional. Dense extraction is prompt-
schema based rather than provider-enforced, so partially-formed candidates are
expected. One malformed candidate must never invalidate the valid candidates
extracted from the same document, so validation is per-candidate and failures
are recorded rather than raised — see `validate_candidates`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

#: Schema version. Recorded on every run so a candidate graph can always be
#: interpreted against the schema that produced it, and so a schema change is
#: visible as a version change rather than as unexplained output drift.
TEMPLATE_VERSION = "PolicyDocumentGraphV1"

#: ``json_schema_extra`` keys Docling Graph reads to build edges. Declared as
#: constants so the template states its dependency on the documented public
#: convention explicitly rather than scattering magic strings.
_EDGE_LABEL = "edge_label"
_GRAPH_REFERENCE = "graph_reference"
_REFERENCE_CLOSED_CATALOG = "reference_closed_catalog"


def edge(
    label: str,
    default: Any = None,
    *,
    reference: bool = False,
    closed_catalog: bool = False,
    **kwargs: Any,
) -> Any:
    """Declare a field as a graph edge, via the documented public convention.

    ``reference=True`` marks an identity-only link: the field carries
    references to entities described in full elsewhere in the schema, and dense
    extraction fills them from the parent's own call rather than discovering
    them separately. That is what keeps per-parent membership lists intact
    instead of one parent absorbing every row of a shared table.

    List edges default to an empty list and single edges to None, so an absent
    relationship is an absence rather than a validation failure.
    """

    extra = dict(kwargs.pop("json_schema_extra", {}) or {})
    extra[_EDGE_LABEL] = label
    if reference:
        extra[_GRAPH_REFERENCE] = True
    if closed_catalog:
        extra[_REFERENCE_CLOSED_CATALOG] = True

    if default is None and "default_factory" not in kwargs:
        return Field(default=None, json_schema_extra=extra, **kwargs)
    if default is not None:
        return Field(default=default, json_schema_extra=extra, **kwargs)
    return Field(json_schema_extra=extra, **kwargs)


def _edge_list(label: str, description: str, **kwargs: Any) -> Any:
    return edge(label, default_factory=list, description=description, **kwargs)


class _CandidateBase(BaseModel):
    """Shared provenance every candidate carries.

    ``anchors`` is the only link back to the document, and it holds canonical
    element references rather than quoted text. That is deliberate: a model that
    never emits evidence text cannot fabricate it, and the application resolves
    the exact characters itself from the canonical artifact.
    """

    model_config = {"is_entity": True}

    anchors: list[str] = Field(
        default_factory=list,
        description=(
            "Canonical element references this candidate was read from. "
            "System metadata, never evidence text."
        ),
    )
    quote_hint: str | None = Field(
        default=None,
        description=(
            "Short locating phrase to help resolve the span. Advisory only: it is "
            "never used as evidence and never stored as policy text."
        ),
    )
    uncertainty: str | None = Field(
        default=None,
        description="Why this candidate may be wrong, in the model's own words.",
    )


class DefinitionCandidate(_CandidateBase):
    """A term the document defines for its own purposes.

    Definitions are extracted separately because they are routinely stated far
    from the rules that depend on them; a rule read without its definition is
    frequently read wrongly.
    """

    model_config = {"is_entity": True, "graph_id_fields": ["term"]}

    term: str = Field(description="The defined term exactly as the document writes it.")
    meaning: str | None = Field(default=None, description="The definition, paraphrased.")
    applies_within: str | None = Field(
        default=None, description="Section or scope in which this definition holds."
    )


class ScopeCandidate(_CandidateBase):
    """Who or what a policy unit applies to, and where it does not."""

    model_config = {"is_entity": True, "graph_id_fields": ["scope_key"]}

    scope_key: str = Field(
        description="Short document-derived label for this scope, e.g. 'full-time employees'."
    )
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    jurisdiction: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None


class ConditionCandidate(_CandidateBase):
    """A trigger, threshold, timing or duration governing a policy unit."""

    model_config = {"is_entity": True, "graph_id_fields": ["condition_key"]}

    condition_key: str = Field(description="Short document-derived label for this condition.")
    subject: str | None = Field(default=None, description="What is being tested.")
    comparator: str | None = Field(
        default=None,
        description="Relation as written: at least, no more than, before, within, equals.",
    )
    value: str | None = Field(default=None, description="Threshold or bound, as written.")
    unit: str | None = Field(default=None, description="Days, percent, currency, occurrences.")
    boundary_inclusive: bool | None = Field(
        default=None,
        description=(
            "Whether the boundary value itself satisfies the condition. Left unset when "
            "the document does not say: guessing turns 'more than 5' into 'at least 5'."
        ),
    )


class ExceptionCandidate(_CandidateBase):
    """A carve-out, exclusion, or override of another policy unit."""

    model_config = {"is_entity": True, "graph_id_fields": ["exception_key"]}

    exception_key: str = Field(description="Short document-derived label for this exception.")
    applies_when: str | None = None
    effect: str | None = Field(
        default=None, description="What changes when it applies: waived, extended, reduced."
    )


class ApprovalCandidate(_CandidateBase):
    """An approval, escalation, notification, evidence or recordkeeping duty."""

    model_config = {"is_entity": True, "graph_id_fields": ["approval_key"]}

    approval_key: str = Field(description="Short document-derived label for this requirement.")
    approver_role: str | None = None
    duty_kind: str | None = Field(
        default=None,
        description="approval, escalation, notification, evidence, or recordkeeping.",
    )
    timing: str | None = Field(default=None, description="When it must happen, as written.")
    is_sequential: bool | None = Field(
        default=None,
        description=(
            "Whether multiple approvers act in order rather than independently. Unset "
            "when the document does not say."
        ),
    )


class CrossReferenceCandidate(_CandidateBase):
    """A pointer to another section, document, or external authority."""

    model_config = {"is_entity": True, "graph_id_fields": ["reference_key"]}

    reference_key: str = Field(description="The reference as printed, e.g. 'Section 4.2'.")
    target_kind: str | None = Field(
        default=None, description="internal, external, or unresolved."
    )
    target_hint: str | None = None


class FootnoteCandidate(_CandidateBase):
    """A footnote or endnote qualifying material elsewhere.

    Footnotes routinely carry the exception that makes a rule correct, so they
    are modelled explicitly rather than merged into surrounding prose.
    """

    model_config = {"is_entity": True, "graph_id_fields": ["marker"]}

    marker: str = Field(description="The footnote marker as printed, e.g. '1' or '*'.")
    qualification: str | None = None


class TableRuleRegionCandidate(_CandidateBase):
    """A table, or region of one, that encodes rules rather than description."""

    model_config = {"is_entity": True, "graph_id_fields": ["table_key"]}

    table_key: str = Field(description="Canonical table reference or printed caption.")
    purpose: str | None = Field(
        default=None, description="What the table decides, e.g. 'response time by severity'."
    )
    row_labels: list[str] = Field(default_factory=list)
    column_labels: list[str] = Field(default_factory=list)
    units_note: str | None = Field(
        default=None, description="Units or qualifiers stated in headers, captions or notes."
    )


class ProcessStepCandidate(_CandidateBase):
    """One step of a procedure, for documents mixing process with policy."""

    model_config = {"is_entity": True, "graph_id_fields": ["step_key"]}

    step_key: str = Field(description="Step number or short document-derived label.")
    actor: str | None = None
    action: str | None = None
    follows: str | None = Field(default=None, description="step_key of the preceding step.")


class PolicyUnitCandidate(_CandidateBase):
    """One candidate policy-bearing unit, with its supporting material attached.

    This is the schema's centre. Conditions, exceptions and approvals hang off
    the unit they govern rather than floating at document level, because an
    exception detached from its rule is not merely less useful — it is
    misleading, since a reader cannot tell which rule it modifies.
    """

    model_config = {"is_entity": True, "graph_id_fields": ["unit_key"]}

    unit_key: str = Field(
        description=(
            "The clause label the document prints (e.g. '2.1'), or the canonical "
            "element reference when the unit is unnumbered. Never a generated name."
        )
    )
    heading_path: list[str] = Field(
        default_factory=list, description="Headings governing this unit, outermost first."
    )
    modality: str | None = Field(
        default=None,
        description=(
            "must, must_not, may, entitlement, eligibility, or authority — as the "
            "document expresses it. Left unset rather than guessed."
        ),
    )
    actor: str | None = Field(default=None, description="Who the unit binds or entitles.")
    action: str | None = None
    outcome: str | None = None
    is_normative: bool | None = Field(
        default=None,
        description=(
            "Whether this states a rule at all. Narrative, purpose statements and "
            "background must not become rules."
        ),
    )

    scope: ScopeCandidate | None = edge("APPLIES_TO", description="Who this unit applies to.")
    conditions: list[ConditionCandidate] = _edge_list(
        "CONDITION_OF", "Triggers and thresholds governing this unit."
    )
    exceptions: list[ExceptionCandidate] = _edge_list(
        "EXCEPTION_TO", "Carve-outs from this unit."
    )
    approvals: list[ApprovalCandidate] = _edge_list(
        "APPROVAL_FOR", "Approval, escalation and evidence duties."
    )
    references: list[CrossReferenceCandidate] = _edge_list(
        "REFERENCES", "Sections or documents this unit points to."
    )
    footnotes: list[FootnoteCandidate] = _edge_list(
        "FOOTNOTE_QUALIFIES", "Footnotes qualifying this unit."
    )
    tables: list[TableRuleRegionCandidate] = _edge_list(
        "TABLE_CONTEXT_FOR", "Tables carrying this unit's values."
    )
    uses_terms: list[str] = Field(
        default_factory=list,
        description="Defined terms this unit depends on, by term.",
    )
    continues_unit_key: str | None = Field(
        default=None,
        description="unit_key of a unit this one continues across a page or section break.",
    )
    possible_duplicate_of: list[str] = Field(
        default_factory=list,
        description=(
            "unit_keys this may restate. A candidate observation for review, never a "
            "merge: two clauses differing only by a negation or a threshold are "
            "different rules."
        ),
    )


class PolicyDocumentGraphV1(BaseModel):
    """Root of the candidate graph for one policy document.

    Document identity fields are populated only when the document states them
    explicitly. They are never inferred from the filename: the directive's
    identity gate forbids filename-derived identity, and a stem like
    ``HR-Special-Leave-Policy-v1.0`` looks authoritative while being an artifact
    of whoever saved the file.
    """

    model_config = {"is_entity": True, "graph_id_fields": ["document_reference"]}

    template_version: str = Field(
        default=TEMPLATE_VERSION,
        description="Schema version that produced this graph.",
    )
    document_reference: str | None = Field(
        default=None,
        description="Reference code the document prints for itself, when stated.",
    )
    document_title: str | None = Field(
        default=None, description="Title as printed in the document."
    )
    version_label: str | None = None
    effective_date: str | None = None
    issuing_authority: str | None = None

    definitions: list[DefinitionCandidate] = _edge_list(
        "DEFINES", "Terms this document defines for its own purposes."
    )
    policy_units: list[PolicyUnitCandidate] = _edge_list(
        "CONTAINS", "Candidate policy-bearing units found in the document."
    )
    process_steps: list[ProcessStepCandidate] = _edge_list(
        "CONTAINS", "Procedure steps, when the document mixes process with policy."
    )


#: Every entity class in the template, in dependency order. Used by validation
#: and by tests that assert the schema stays complete and domain-neutral.
CANDIDATE_MODELS: tuple[type[BaseModel], ...] = (
    DefinitionCandidate,
    ScopeCandidate,
    ConditionCandidate,
    ExceptionCandidate,
    ApprovalCandidate,
    CrossReferenceCandidate,
    FootnoteCandidate,
    TableRuleRegionCandidate,
    ProcessStepCandidate,
    PolicyUnitCandidate,
    PolicyDocumentGraphV1,
)


def validate_candidates(
    model: type[BaseModel], payloads: list[dict]
) -> tuple[list[BaseModel], list[str]]:
    """Validate each candidate independently, keeping the valid ones.

    Dense extraction uses prompt-schema output rather than provider-enforced
    structured output, so malformed entries are an expected failure mode rather
    than an exceptional one. Validating the batch as a unit would discard every
    correctly extracted candidate because one entry was wrong — which converts a
    small model error into total loss of a document's extraction.

    Returns the successfully validated candidates and one diagnostic per
    rejection, so the failures stay visible rather than being silently dropped.
    """

    valid: list[BaseModel] = []
    diagnostics: list[str] = []

    for index, payload in enumerate(payloads):
        if not isinstance(payload, dict):
            diagnostics.append(f"{model.__name__}[{index}]: expected an object, got {type(payload).__name__}")
            continue
        try:
            valid.append(model.model_validate(payload))
        except ValidationError as exc:
            reasons = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
                for err in exc.errors()[:3]
            )
            diagnostics.append(f"{model.__name__}[{index}]: {reasons}")

    return valid, diagnostics


def edge_labels(model: type[BaseModel]) -> dict[str, str]:
    """Return ``field name -> edge label`` for one model.

    Reads the same ``json_schema_extra`` convention Docling Graph reads, so a
    test asserting the declared relationship families is checking the metadata
    the extractor will actually act on rather than a parallel list.
    """

    labels: dict[str, str] = {}
    for name, field in model.model_fields.items():
        extra = field.json_schema_extra
        if isinstance(extra, dict) and _EDGE_LABEL in extra:
            labels[name] = str(extra[_EDGE_LABEL])
    return labels
