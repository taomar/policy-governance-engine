"""Can an LLM decide this rule against a customer's text?

`machine_executable` answers a different question — can *our FEEL evaluator*
decide it — and answers it correctly. That evaluator needs a fact model
(`"the employee's current basic salary"` -> `employee.salary.basic`) and value
normalisation (`"10%"` -> `0.10`), neither of which can be invented from the
document, so the flag is false for all 45 rules of the AD-103 extraction.

But the shipped policy JSON is evaluated by an LLM against the customer's own
text, and the LLM performs that binding at evaluation time from the case in
front of it. So for the deployed pipeline the FEEL flag measures a capability
nobody needs, and reporting only it says "0 of 45 executable" about a document
whose rules are mostly decidable. A reviewer reading that number concludes the
extraction failed, when what actually happened is that a different question
was asked.

This module answers the deployment's question instead. `machine_executable` is
untouched: the evaluator guard that skips non-projectable rules is correct and
load-bearing, and two honest answers to two different questions are worth more
than one flag stretched across both.

The assessment reads *which canonical fields the formulator populated*, never
their wording. `CanonicalPolicyRule` populates a field only when the source
explicitly supports it (Section 21: "do not populate fields merely because the
schema supports them"), so presence is evidence and absence is evidence. The
one exception is delegation, which `policy_parties` handles behind a narrow
closed set of constructions and quotes for verification.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.infrastructure.extraction.policy_parties import (
    PartyRole,
    PolicyParty,
    extract_parties,
)
from policy_platform.infrastructure.extraction.self_containment import (
    UnresolvedReferent,
    unresolved_referents,
)


class Evaluability(str, Enum):
    """Whether the rule states enough for an LLM to reach a decision.

    Deliberately separate from `machine_executable`, and deliberately more
    than a boolean: a fully-stated prohibition, a delegated decision and a
    sentence fragment are all un-projectable to FEEL, but only the last is a
    defect. Collapsing them into one flag is what made the extraction look
    worse than it is.
    """

    #: A test exists and its terms are stated. An LLM given the case and this
    #: rule has everything the document offers.
    DECIDABLE = "decidable"
    #: The document states no test because it *delegated the decision*. Not a
    #: gap: "Exceptional Increase may be granted" answers the question — it is
    #: possible, and someone decides. Reporting it as incomplete asks a
    #: reviewer to invent a threshold the policy deliberately withheld.
    #:
    #: DMN 1.5 models this as an `authorityRequirement` pointing at a
    #: `knowledgeSource`; XACML 3.0 as a Permit carrying an Obligation to
    #: obtain approval. Both treat a delegated decision as a decision.
    DISCRETIONARY = "discretionary"
    #: Subject and predicate are stated, nothing to test against, and no
    #: discretion signal either — no permissive modality, no named authority.
    #: The sentence genuinely says nothing actionable. The document is what is
    #: incomplete here, not the extraction.
    UNDERSPECIFIED = "underspecified"
    #: Carries no decision by construction — a definition, a classification, or
    #: a statement about the document. Nothing to evaluate, and nothing wrong.
    NOT_A_DECISION = "not_a_decision"
    #: The decomposition itself is damaged (no subject, no predicate, a
    #: predicate that swallowed the modal word, or operative wording that
    #: points at text the record does not contain). An extraction defect, not a
    #: property of the source.
    MALFORMED = "malformed"


#: Verdicts that mean the rule can be put in front of an evaluator. Named once
#: so callers stop re-deriving the set and drifting apart on whether
#: `DISCRETIONARY` counts (it does — a delegated decision is a decision).
ANSWERABLE = frozenset({Evaluability.DECIDABLE, Evaluability.DISCRETIONARY})


class ReferencedAttribute(BaseModel):
    """One thing the evaluator must find in the case, quoted from the source.

    `phrase` is verbatim canonical text, never a fact path. "the employee's
    current basic salary" is what the document says; `employee.salary.basic`
    is a mapping into a customer's schema that this platform has no basis to
    invent. Quoting asserts nothing the formulator did not already read out of
    the document; inventing the path would assert a schema.

    `role` is the canonical field the phrase came from, so a reviewer can trace
    any entry back to the decomposition rather than take the list on trust.
    """

    phrase: str
    role: str


class EvaluabilityAssessment(BaseModel):
    """The verdict, the reason for it, and what the rule needs to be decided."""

    evaluability: Evaluability
    #: Which populated field carried the test, or which required field was
    #: missing. Written for a reviewer deciding whether to fix the rule or the
    #: document, so it names the field rather than restating the verdict.
    reason: str
    #: Targets for the entity/attribute extraction pass. Empty is meaningful:
    #: it means the rule named nothing to look for.
    attributes_referenced: list[ReferencedAttribute] = Field(default_factory=list)
    #: Who the rule governs, who receives its result, and who decides it.
    parties: list[PolicyParty] = Field(default_factory=list)


#: Canonical fields that name something the evaluator must locate in the
#: customer's case before it can decide. Outcome-bearing fields (`consequence`,
#: `remedy`), the modal word, the verb, and qualifiers on other fields
#: (`unit`, `currency`) are excluded: they describe what follows from a
#: decision or how to read another field, not what to go and find.
_INPUT_BEARING_FIELDS: tuple[str, ...] = (
    "subject",
    "actor",
    "beneficiary",
    "candidate",
    "recipient",
    "assigner",
    "object",
    "threshold",
    "condition",
    "constraint",
    "prerequisite",
    "trigger",
    "temporal_constraint",
    "deadline",
    "frequency",
    "location",
)

#: Fields that pin the rule down — anything the document supplies beyond
#: naming a subject and a verb. A rule carrying one of these has something an
#: evaluator can work with.
#:
#: The list started as the four value-bearing fields and missed "Medical
#: benefits begin on the employee's first working day", which carries only
#: `temporal_constraint`. Asked "when do my benefits start?", that sentence
#: answers completely — calling it underspecified said the document was silent
#: when it was specific, just about *when* rather than *how much*.
#:
#: Outcome fields (`consequence`, `remedy`) are excluded because they describe
#: what follows a decision rather than how to reach one, and `unit` / `currency`
#: because they qualify a threshold and cannot stand without it.
_SPECIFYING_FIELDS: tuple[str, ...] = (
    "object",
    "threshold",
    "constraint",
    "calculation",
    "condition",
    "prerequisite",
    "trigger",
    "temporal_constraint",
    "deadline",
    "frequency",
    "location",
)

#: Canonical rule types that carry no decision by construction.
_NON_DECISION_TYPES = frozenset(
    {
        CanonicalRuleType.DEFINITION,
        CanonicalRuleType.CLASSIFICATION,
        CanonicalRuleType.NON_NORMATIVE,
    }
)

#: Fields whose presence overrides a non-decision rule type.
#:
#: The type alone is not enough. "Increase due to inflation not exceeding 5% of
#: the employee's basic salary" arrived typed `classification` and carrying
#: `threshold: "5% of the employee's basic salary"` — reporting that as "states
#: meaning only" told a reviewer there was nothing to evaluate while the cap sat
#: in the record. A reviewer asking "what is the limit?" gets an answer from
#: that rule, so it is a decision whatever it was labelled.
#:
#: `object` and `condition` are deliberately excluded: a genuine definition has
#: both. "Basic salary means the monthly salary before allowances" carries an
#: object, and "for the purposes of this section, X means Y" carries a
#: condition. Neither states a limit. Only value-bearing fields override, and a
#: definition does not carry a limit.
_VALUE_BEARING_FIELDS: tuple[str, ...] = ("threshold", "constraint", "calculation")

#: Deontic permission operators. A permissive modal *is* a discretion signal:
#: "may" grants latitude rather than stating a test, which is why a rule
#: carrying one and no threshold is delegated rather than incomplete.
#:
#: Negated forms are excluded below — "may not" is a prohibition, and reading
#: it as discretion would turn a ban into an option.
_PERMISSIVE_MODALITY_RE = re.compile(
    r"^\s*(?:may|might|can|could|is\s+permitted\s+to|is\s+authori[sz]ed\s+to)\b",
    re.IGNORECASE,
)

_NEGATED_MODALITY_RE = re.compile(r"\b(?:not|never|no)\b", re.IGNORECASE)


def is_permissive_modality(modality: str | None) -> bool:
    """True when the modal word grants latitude rather than stating a duty."""

    text = modality or ""
    if _NEGATED_MODALITY_RE.search(text):
        return False
    return bool(_PERMISSIVE_MODALITY_RE.match(text))


def referenced_attributes(rule: CanonicalPolicyRule | None) -> list[ReferencedAttribute]:
    """The verbatim phrases an evaluator must locate in the customer's case.

    This is the list the extraction pass is missing today. Without it the LLM
    reading a customer's text decides for itself what is relevant, which is
    where non-determinism enters the pipeline — at extraction, before any
    evaluation happens. With it, extraction has a target, and an attribute the
    case never mentions is *detectably* absent rather than silently estimated.

    Order follows `_INPUT_BEARING_FIELDS` so the same rule always produces the
    same list; a set would make the output depend on hash order.
    """

    if rule is None:
        return []
    found: list[ReferencedAttribute] = []
    seen: set[str] = set()
    for field in _INPUT_BEARING_FIELDS:
        phrase = (getattr(rule, field, None) or "").strip()
        if not phrase:
            continue
        # The same phrase often fills two fields — `object` and `threshold`
        # both hold "10% of the employee's current basic salary" when the limit
        # *is* the object. One thing to find, so one entry; the first field in
        # declaration order keeps the winner deterministic.
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(ReferencedAttribute(phrase=phrase, role=field))
    return found


#: Fields whose wording a reader has to understand before the rule can be
#: applied at all: who it is about, and what pins it down. A pointer that does
#: not resolve is a defect wherever it sits, but here it is *load-bearing* —
#: these are the very fields the `decidable` verdict below is granted for, so a
#: record earning that verdict from wording it cannot explain is claiming
#: something it does not deliver.
_OPERATIVE_FIELDS: tuple[str, ...] = ("subject", *_SPECIFYING_FIELDS)


def dangling_referents(
    rule: CanonicalPolicyRule | None, source_text: str = ""
) -> list[UnresolvedReferent]:
    """Operative wording in `rule` that the record itself does not explain.

    The record is its own resolution scope, which is exactly the promise being
    checked: an AI Ready rule is read on its own. So every field the
    record carries counts as available text, and the source sentence counts
    twice over — it is what a judge actually reads.
    """

    if rule is None:
        return []

    def text(name: str) -> str:
        value = getattr(rule, name, None)
        return value.strip() if isinstance(value, str) else ""

    fields = {name: text(name) for name in _OPERATIVE_FIELDS}
    carried = " ".join(
        value
        for value in (getattr(rule, name, None) for name in type(rule).model_fields)
        if isinstance(value, str)
    )
    return unresolved_referents(fields, f"{source_text} {carried}", source_text)


#: The words English uses to negate a verb phrase. A closed function-word
#: class — these are all of them, not a sample — so it cannot grow into a
#: content classifier.
#:
#: Consulted ONLY on words the predicate dropped from the modality, never on
#: the sentence. `formulation_mapping.is_negative_modality` is the fuller test
#: and is used everywhere a modality is judged as a whole; it is not imported
#: here because that module imports this one, and the cycle is not worth
#: breaking for six words. If a third notion of negation ever appears, all
#: three belong in one place.
_NEGATION_PARTICLES = frozenset({"not", "never", "no", "cannot", "nor", "neither"})


def _predicate_repeats_modality(rule: CanonicalPolicyRule) -> bool:
    """True when the predicate swallowed the modal word.

    "Directors of administrative units **may may** also be eligible" — modality
    "may", predicate "may also be eligible". The duplicate is visible in the
    title and means the decomposition mis-split the sentence, so the predicate
    cannot be trusted as the verb.

    Checked structurally (first token of predicate == last token of modality),
    not by matching a list of modal words, so it holds for any modality the
    formulator reports.
    """

    modality = (rule.modality or "").strip().casefold().split()
    predicate = (rule.predicate or "").strip().casefold().split()
    if not modality or not predicate:
        return False
    return predicate[0] == modality[-1]


def _words_the_predicate_dropped(rule: CanonicalPolicyRule) -> list[str]:
    """The modality's words that the predicate did not keep.

    Only meaningful once `_predicate_repeats_modality` holds: the two fields
    then carry one verb phrase, and the predicate is the shorter copy. What it
    lost is what separates a harmless duplication from a damaging one.
    """

    modality = (rule.modality or "").strip().casefold().split()
    predicate = (rule.predicate or "").strip().casefold().split()
    if not modality or not predicate:
        return []
    return [word for word in modality[:-1] if word not in predicate]


def _predicate_dropped_the_negation(rule: CanonicalPolicyRule) -> bool:
    """The predicate is the modality with its negation removed.

    This is the damaging half of the mis-split, and it needs saying apart from
    the harmless half:

        "Smoking is not allowed"   modality 'is not allowed'   predicate 'allowed'
        "Alcohol ... are strictly forbidden"
                                   modality 'are strictly forbidden'
                                   predicate 'forbidden'

    Both are one verb phrase written into two fields. Only the first inverts:
    read on its own, its predicate says the document permits what the document
    forbids. The second is redundant and says nothing false.

    Reported as one finding, both got the same sentence — "the verb is
    unreliable" — which understates the first and overstates the second. A
    reviewer triaging a report cannot tell which two of four records state the
    opposite of their source.
    """

    return any(word in _NEGATION_PARTICLES for word in _words_the_predicate_dropped(rule))


def assess(rule: CanonicalPolicyRule | None, source_text: str = "") -> EvaluabilityAssessment:
    """Assess one canonical rule. Reads field presence and named parties only."""

    parties = extract_parties(rule, source_text)
    attributes = referenced_attributes(rule)

    def verdict(evaluability: Evaluability, reason: str) -> EvaluabilityAssessment:
        return EvaluabilityAssessment(
            evaluability=evaluability,
            reason=reason,
            attributes_referenced=attributes,
            parties=parties,
        )

    if rule is None:
        return verdict(
            Evaluability.MALFORMED,
            "no canonical decomposition was produced for this statement",
        )

    if rule.rule_type in _NON_DECISION_TYPES:
        stated_value = [
            f for f in _VALUE_BEARING_FIELDS if (getattr(rule, f, None) or "").strip()
        ]
        if not stated_value:
            return verdict(
                Evaluability.NOT_A_DECISION,
                f"canonical rule_type is '{rule.rule_type.value}', which states no decision",
            )

    if not (rule.subject or "").strip():
        return verdict(
            Evaluability.MALFORMED,
            "canonical 'subject' is empty, so the rule names nothing to decide about",
        )
    if not (rule.predicate or "").strip():
        return verdict(
            Evaluability.MALFORMED,
            "canonical 'predicate' is empty, so the rule states no test",
        )
    if _predicate_repeats_modality(rule):
        if _predicate_dropped_the_negation(rule):
            dropped = " ".join(_words_the_predicate_dropped(rule))
            return verdict(
                Evaluability.MALFORMED,
                f"canonical 'predicate' is the modality '{rule.modality}' with "
                f"'{dropped}' removed, so the predicate alone reads "
                f"'{rule.predicate}' — the opposite of what the source states. "
                "Anything reading the predicate without the modality inverts "
                "this rule",
            )
        return verdict(
            Evaluability.MALFORMED,
            f"canonical 'predicate' repeats the modality '{rule.modality}', "
            "so the sentence was mis-split and the verb is unreliable",
        )

    # A pointer the record cannot answer. The source passage says which day,
    # which cases, which documents; this record was sliced out of it without
    # them, so a reader is sent somewhere the record does not go. The document
    # is intact — the slice is not — which is why this is `malformed` and not
    # `underspecified`.
    #
    # ONLY when the slice actually lost the antecedent. `UnresolvedReferent`
    # already separates the two cases and this verdict used to ignore the
    # separation: a pointer whose evidence still carries the sentence before it
    # was reported as a damaged decomposition needing re-extraction, in exactly
    # the same words and at the same blocking severity as one whose evidence
    # holds a single sentence and cannot contain the antecedent at all.
    #
    # The measured case: "If there are workshops, meetings, or other events on
    # Saturdays, you may be asked to attend. In the case of absences on that
    # day, there will be action taken according to the administration
    # procedures." The condition says "that day"; the antecedent is "Saturdays",
    # in the record's own evidence, one sentence earlier. `_resolves_locally`
    # asks whether the *head noun* recurs — "day" against "Saturdays" — so it
    # answers no. That is a lexical test standing in for a semantic one, and
    # anaphora exists precisely so that prose does not repeat the noun: a
    # document that said "on that Saturday" would read worse and pass. The
    # check therefore fired on well-formed writing and told a compliance officer
    # their published policy was damaged.
    #
    # So a pointer whose evidence kept its neighbour is not malformed. It is not
    # silently dropped either — `dangling_referents` still reports it, and
    # `record_does_not_stand_alone` is the check that speaks to "read this with
    # its passage". What changes is that it no longer claims the extraction is
    # broken, because on this evidence it is not.
    lost_their_antecedent = [
        item for item in dangling_referents(rule, source_text)
        if not item.source_carries_a_neighbour
    ]
    if lost_their_antecedent:
        return verdict(
            Evaluability.MALFORMED,
            "the extraction cut this record away from wording it depends on: "
            + "; ".join(item.as_reason() for item in lost_their_antecedent),
        )

    # A stated test wins over a delegation. "not exceeding 5% ... and subject
    # to the approval of the Board of Trustees" is decidable *and* carries an
    # authority: XACML models exactly this as a Permit with an Obligation, so
    # the approval rides along in `parties` rather than downgrading the
    # verdict. Reporting it as discretionary would hide the 5% limit.
    carried = [f for f in _SPECIFYING_FIELDS if (getattr(rule, f, None) or "").strip()]
    if carried:
        fields = ", ".join("'" + field + "'" for field in carried)
        return verdict(Evaluability.DECIDABLE, f"subject, predicate and {fields} are stated")

    named = [p for p in parties if p.role is PartyRole.AUTHORITY]
    if named:
        who = ", ".join(p.name for p in named)
        return verdict(
            Evaluability.DISCRETIONARY,
            f"the source states no test and delegates the decision to {who}",
        )
    if is_permissive_modality(rule.modality):
        return verdict(
            Evaluability.DISCRETIONARY,
            f"the modality '{rule.modality}' grants latitude rather than stating a test, "
            "so the decision is discretionary — but the source names no authority to "
            "exercise it",
        )

    return verdict(
        Evaluability.UNDERSPECIFIED,
        "the source names a subject and a verb and nothing else — no value, condition, "
        "time, place, authority or permissive modality — so it gives nothing to decide on",
    )


def assess_policy(policy: CanonicalPolicy | None) -> EvaluabilityAssessment:
    """`assess` for a whole canonical policy, using its verbatim source text."""

    if policy is None:
        return assess(None)
    return assess(policy.rule, policy.source_text or "")
