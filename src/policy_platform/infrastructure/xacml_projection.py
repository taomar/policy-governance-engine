"""Build the XACML view from a canonical record, without inventing anything.

Three defects this replaces, all of them generalisations rather than one-off
mappings:

**Grammatical position was treated as evidence of role.** Whatever occupied
the canonical `subject` slot became `subject.subject-id`, so "the allowance",
"Annual increase" and "A work nature allowance at the rate of (200) two
hundred SR per month" were all asserted to be XACML subjects. They are
resources. XACML's subject is the requesting entity, and a benefit does not
request anything.

**Whole verbal clauses became `action.action-id`.** "will be calculated based
on the higher basic salary of the couple" is a complete normative outcome, not
a canonical action identifier. An action-id is matched against a request, and
no request will ever carry that string.

**Conditions were anonymous strings with a runtime badge.** "after the trial
period has expired" states a complete predicate; "depending on the financial
position of the University" names a dependency and never says what qualifies.
Both were rendered as source text tagged `Indeterminate · missing-attribute`,
which conflated the document's clarity with our fact model's emptiness and
reported a PDP result before any PDP ran.

Every classification here records its basis. Where evidence does not settle a
role, the entity is kept as `UNCLASSIFIED` rather than defaulted — an entity a
reviewer can see is unresolved beats a confident wrong category nobody checks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.xacml_projection import (
    AdviceExpression,
    ClassifiedEntity,
    CompilationStatus,
    EntityRole,
    FactModelReadiness,
    FactModelStatus,
    NormativeModality,
    ObligationExpression,
    PolicyXacmlView,
    PredicateStatus,
    RequiredAttribute,
    RuleEffect,
    SourceCondition,
    SourceSemantics,
    XacmlProjection,
    XacmlTarget,
)
from policy_platform.infrastructure.policy_parties import PartyRole, extract_parties

#: Canonical fields that name a party. Only these produce a XACML subject.
#: The grammatical subject is deliberately absent: it is whatever the predicate
#: is predicated of, which for policy prose is usually a benefit, an amount or
#: an entitlement.
_PARTY_FIELDS: tuple[str, ...] = ("actor", "beneficiary", "recipient", "candidate", "assigner")

#: Normalised XACML action identifiers, matched against the head of the
#: canonical predicate. Closed on purpose: an open mapping is how whole clauses
#: became action-ids. A predicate that matches nothing here yields no
#: `action.action-id` at all, and the clause is preserved as the outcome, which
#: is what it is.
#:
#: Keys are lemma stems so that "grants", "granted" and "granting" all reach
#: "grant" without a stemmer pulling in false matches.
#:
#: The suffix set has to include the bare `e`. An earlier version used
#: `(?:e?[sd]|ing)?`, which matched "provides", "provided" and "providing" but
#: not "provide": after the stem `provid` the `e` needs an `s` or `d` to
#: follow, so the group matched nothing and the word boundary then failed
#: mid-word. The same verb was therefore recognised in three grammatical forms
#: and refused in the fourth — and every `-e` verb in the lexicon carried the
#: same hole.
#:
#: It also has to allow the doubled final consonant English writes before
#: `-ed` and `-ing` on some verbs — "transferred", "submitted". Those were
#: refused for the same reason and found the same way: by exercising each entry
#: through the forms a sentence actually uses, rather than reading the table
#: and assuming an entry that is present works.
def _stem_pattern(stem: str) -> str:
    """A word-bounded pattern matching `stem` in its ordinary inflections."""

    forms = ["e", "es", "ed", "ing", "s", "d"]
    tail = stem[-1]
    if tail.isalpha():
        forms += [f"{tail}ed", f"{tail}ing"]
    return rf"\b{stem}(?:{'|'.join(forms)})?\b"


#: Stems whose lemma is not formed by adding a suffix to a verb root, so the
#: general pattern above cannot reach them. `eligib` never matched anything at
#: all: "eligible" is `eligib` + `le`, which is not in the suffix set, so the
#: entry sat in the lexicon looking like coverage it did not provide.
_ACTION_IRREGULAR: tuple[tuple[str, str], ...] = (
    (r"eligib(?:le|ility)", "determine-eligibility"),
    # Limit constructions. English states a bound in several ways and they mean
    # the same thing; recognising only the comparative form left the others
    # with no action while an identical rule phrased with "exceed" got one.
    (r"limited\s+to", "limit"),
    (r"up\s+to\s+a\s+maximum\s+of", "limit"),
    (r"no\s+more\s+than", "limit"),
    (r"at\s+most", "limit"),
    (r"capped\s+at", "limit"),
)

_ACTION_LEXICON: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(_stem_pattern(stem), re.IGNORECASE), action)
    for stem, action in (
        (r"grant", "grant"),
        (r"pay", "pay"),
        (r"paid", "pay"),
        (r"calculat", "calculate"),
        (r"increas", "increase"),
        (r"transfer", "transfer"),
        (r"approv", "approve"),
        (r"provid", "provide"),
        (r"submit", "submit"),
        (r"reimburs", "reimburse"),
        (r"deduct", "deduct"),
        (r"terminat", "terminate"),
        (r"entitl", "entitle"),
        (r"cover", "cover"),
        (r"exceed", "limit"),
    )
) + tuple(
    (re.compile(rf"\b{pattern}\b", re.IGNORECASE), action)
    for pattern, action in _ACTION_IRREGULAR
)

#: Source constructions that introduce a condition or dependency. Recognising
#: one does *not* license inventing an operator — that is the whole point of
#: the resolved/unresolved split below.
_DEPENDENCY_MARKERS: tuple[str, ...] = (
    "depending on",
    "based on",
    "subject to",
    "provided that",
    "conditional upon",
    "only if",
    "in the case of",
    "in one of the following cases",
    "upon approval of",
    "upon the recommendation of",
)

#: Constructions that state a complete, testable predicate. Each carries its
#: own truth condition in the wording, so reading one asserts nothing the
#: source did not write.
#:
#: "after the trial period has expired" means the trial period has expired. The
#: fact model may not carry the attribute; that is a separate axis entirely.
_RESOLVED_PREDICATE_RE: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bafter\s+(?P<concept>.+?)\s+(?:has|have)\s+(?:expired|elapsed|passed|ended)\b", re.IGNORECASE),
        "boolean-equal",
        "true",
    ),
    (
        re.compile(r"\bafter\s+(?:the\s+)?(?P<concept>.+?)\s+(?:is|are)\s+(?:completed|complete|finished)\b", re.IGNORECASE),
        "boolean-equal",
        "true",
    ),
    (
        re.compile(r"\b(?:subject\s+to|upon)\s+(?:the\s+)?(?:prior\s+)?approval\s+of\s+(?P<concept>.+)$", re.IGNORECASE),
        "boolean-equal",
        "true",
    ),
    (
        re.compile(r"\brequires?\s+(?:the\s+)?(?:prior\s+)?approval\s+of\s+(?P<concept>.+)$", re.IGNORECASE),
        "boolean-equal",
        "true",
    ),
    (
        re.compile(r"\bnot\s+exceed(?:ing)?\s+(?P<concept>.+)$", re.IGNORECASE),
        "less-than-or-equal",
        None,
    ),
    (
        re.compile(r"\bat\s+least\s+(?P<concept>.+)$", re.IGNORECASE),
        "greater-than-or-equal",
        None,
    ),
)

#: Constructions that name a dependency without stating its test. "depending on
#: the financial position of the University" establishes that financial
#: position matters and never says whether that means a threshold, a boolean or
#: a judgement, so no operator may be derived.
_DEPENDENCY_ONLY_RE = re.compile(
    r"\b(?:depending\s+on|based\s+on|according\s+to|in\s+accordance\s+with)\s+"
    r"(?:the\s+)?(?P<concept>.+)$",
    re.IGNORECASE,
)

_ARTICLE_RE = re.compile(r"^(?:the|a|an|its|their)\s+", re.IGNORECASE)
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")

#: A passive or middle construction: the grammatical subject is what the verb
#: is done *to*, so it is the thing acted upon.
#:
#: This is the only structural signal that separates "the allowance will be
#: calculated" (a resource) from "FBSU grants employee benefits" (an
#: organisation acting). Both are grammatical subjects with no party field, and
#: classifying by slot alone put an allowance and a university into the same
#: category. Voice is a property of the sentence, not a guess about the world.
#:
#: Irregular participles are listed because `-ed`/`-en` misses "is paid", "is
#: given", "is set" — and those are the commonest constructions in benefits
#: prose, so omitting them would leave the rule firing mostly on the rare case.
_PASSIVE_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|get|gets|got)\s+"
    r"(?:\w+(?:ed|en)"
    r"|paid|given|taken|made|set|put|held|kept|sent|built|drawn|shown|met|left|lost"
    r"|found|told|brought|bought|caught|taught|sought|dealt|felt|meant|read|cut|hit"
    r"|let|split|spread|born)\b",
    re.IGNORECASE,
)


def is_passive_predicate(predicate: str | None) -> bool:
    """True when the predicate puts its grammatical subject on the receiving end."""

    return bool(_PASSIVE_RE.search(predicate or ""))


def _slug(phrase: str) -> str:
    """A stable identifier for a concept, derived from its own words.

    Not a fact path. `trial-period-expired` names what the source talked about;
    it does not claim a customer's schema has that field, which is why the
    readiness layer reports every one of these as `missing` until somebody maps
    it deliberately.
    """

    stripped = _ARTICLE_RE.sub("", (phrase or "").strip())
    slug = _NON_SLUG_RE.sub("-", stripped.casefold()).strip("-")
    return slug[:80]


def normalize_action(predicate: str | None) -> str | None:
    """Map a canonical predicate to a XACML action identifier, or to nothing.

    Returns None when no entry in the closed lexicon matches. That is the
    correct outcome, not a failure: `action.action-id` is matched against a
    request, so emitting "will be calculated based on the higher basic salary
    of the couple" produces an identifier no request can ever carry, and the
    Target silently matches nothing.
    """

    text = (predicate or "").strip()
    if not text:
        return None
    for pattern, action in _ACTION_LEXICON:
        if pattern.search(text):
            return action
    return None


def _modality_for(rule: CanonicalPolicyRule) -> NormativeModality | None:
    """Read the source's normative force from the canonical record.

    Kept separate from the XACML Effect because the two do not correspond. An
    obligation is not a Permit; it projects to a Permit whose mandatory
    behaviour lives in an ObligationExpression, and collapsing the two loses
    the requirement.

    The **modal word wins over the rule type**, and that is not a refinement.
    Reading the type alone loses the negation entirely: a sentence forbidding
    conduct is frequently typed `conditional_outcome` or `obligation`, and
    every one of those projected to Permit — so the record asserted the
    opposite of what the document said, on exactly the rules where being wrong
    matters most. Measured before this guard, every rule in a live extraction
    projected to Permit, including three that read "shall not exceed…", "will
    not be enrolled…" and "will not bear any responsibility".

    `states_a_negation` is the platform's existing test, already used to stop
    the same defect reaching `Effect.type`. It is imported rather than
    re-implemented: two definitions of what counts as a negation is how one of
    them ends up not counting "may not" — or, as happened here, not counting a
    negation the sentence wrote into its predicate rather than its modal word.
    """

    from policy_platform.infrastructure.formulation_mapping import states_a_negation

    base = {
        CanonicalRuleType.OBLIGATION: NormativeModality.OBLIGATION,
        CanonicalRuleType.PROHIBITION: NormativeModality.PROHIBITION,
        CanonicalRuleType.PERMISSION: NormativeModality.PERMISSION,
        CanonicalRuleType.ENTITLEMENT: NormativeModality.ENTITLEMENT,
        CanonicalRuleType.ELIGIBILITY: NormativeModality.ELIGIBILITY,
        CanonicalRuleType.INELIGIBILITY: NormativeModality.ELIGIBILITY,
        CanonicalRuleType.CALCULATION: NormativeModality.CALCULATION_REQUIREMENT,
        CanonicalRuleType.CONDITIONAL_OUTCOME: NormativeModality.DEPENDENCY,
        CanonicalRuleType.DEFINITION: NormativeModality.DEFINITION,
        CanonicalRuleType.CLASSIFICATION: NormativeModality.DEFINITION,
    }.get(rule.rule_type)

    if base is None:
        return None
    # A definition states meaning and cannot be negated into a prohibition;
    # "X does not mean Y" still defines rather than forbids.
    if base is NormativeModality.DEFINITION:
        return base
    if states_a_negation(rule):
        return NormativeModality.PROHIBITION
    return base


def classify_entities(
    rule: CanonicalPolicyRule, source_text: str
) -> tuple[list[ClassifiedEntity], list[ClassifiedEntity], list[ClassifiedEntity]]:
    """Split the rule's noun phrases into subjects, resources and unclassified.

    A phrase becomes a XACML subject only when a party-typed canonical field
    names it, or when the grammatical subject *is* one of those parties. The
    grammatical slot on its own is not evidence: "The employee shall submit"
    and "The allowance will be calculated" are the same shape and different
    roles, and the previous rule read both as subjects.

    Returns `(subjects, resources, unclassified)`.
    """

    subjects: list[ClassifiedEntity] = []
    resources: list[ClassifiedEntity] = []
    unclassified: list[ClassifiedEntity] = []
    party_names: set[str] = set()

    for field in _PARTY_FIELDS:
        phrase = (getattr(rule, field, None) or "").strip()
        if not phrase:
            continue
        party_names.add(phrase.casefold())
        subjects.append(
            ClassifiedEntity(
                phrase=phrase,
                role=EntityRole.SUBJECT,
                basis=f"canonical '{field}' names a party",
                normalized_id=_slug(phrase),
            )
        )

    # An authority read from a delegation construction is a party too, even
    # when no canonical field carried it.
    for party in extract_parties(rule, source_text):
        if party.role is PartyRole.AUTHORITY and party.name.casefold() not in party_names:
            party_names.add(party.name.casefold())
            subjects.append(
                ClassifiedEntity(
                    phrase=party.name,
                    role=EntityRole.SUBJECT,
                    basis=f"named as decision authority by '{party.source_field}'",
                    normalized_id=_slug(party.name),
                )
            )

    grammatical = (rule.subject or "").strip()
    if grammatical:
        if grammatical.casefold() in party_names:
            # Already recorded as a subject by a party field; nothing to add.
            pass
        elif _modality_for(rule) is NormativeModality.DEFINITION:
            # A definition names the term it defines. That is the thing being
            # described, not an actor and not something acted upon.
            resources.append(
                ClassifiedEntity(
                    phrase=grammatical,
                    role=EntityRole.RESOURCE,
                    basis="term defined by a definition or classification",
                    normalized_id=_slug(grammatical),
                )
            )
        elif is_passive_predicate(rule.predicate):
            # The predicate is done *to* it, so it is the thing acted upon.
            # This is the sentence's own structure, not an inference about the
            # world: "the allowance will be calculated" cannot be the requester.
            resources.append(
                ClassifiedEntity(
                    phrase=grammatical,
                    role=EntityRole.RESOURCE,
                    basis=f"passive predicate '{rule.predicate}' acts on it",
                    normalized_id=_slug(grammatical),
                )
            )
        else:
            # Active voice with no party evidence. It could be an organisation
            # acting ("FBSU grants employee benefits"), a policy issuer, a
            # scope, or a stative subject ("Annual increase shall not exceed").
            # Nothing available distinguishes them, so the phrase is kept and
            # the category is not asserted — forcing "FBSU" into either subject
            # or resource states something the document does not.
            unclassified.append(
                ClassifiedEntity(
                    phrase=grammatical,
                    role=EntityRole.UNCLASSIFIED,
                    basis=(
                        "active predicate and no party evidence — could be an actor, an "
                        "issuing organisation, a scope, or the thing constrained"
                    ),
                )
            )

    obj = (rule.object or "").strip()
    if obj and obj.casefold() not in {r.phrase.casefold() for r in resources}:
        if obj.casefold() in party_names:
            pass
        else:
            unclassified.append(
                ClassifiedEntity(
                    phrase=obj,
                    role=EntityRole.UNCLASSIFIED,
                    basis=(
                        "canonical 'object' — the evidence does not establish whether it "
                        "is a resource, an outcome, or part of the action"
                    ),
                )
            )
    return subjects, resources, unclassified


#: Splits a phrase that chains several dependencies into its parts. "based on
#: their functions and depending on the recommendation of the director of the
#: concerned Department" states two conditions, and the correction that
#: prompted this module names them separately. Reading it as one produced a
#: run-on concept identifier that matched nothing and told a reviewer nothing.
#:
#: Only splits before a marker, so "the director of the concerned Department"
#: stays whole — splitting on every "and" would break the parties apart.
_CONDITION_SPLIT_RE = re.compile(
    r"\s*(?:,|;|\band\b)\s+(?=(?:depending\s+on|based\s+on|subject\s+to|provided\s+that"
    r"|conditional\s+upon|only\s+if|upon\s+approval\s+of|upon\s+the\s+recommendation\s+of"
    r"|after|before)\b)",
    re.IGNORECASE,
)


def split_conditions(phrase: str) -> list[str]:
    """Break a chained condition phrase into the conditions it states."""

    text = " ".join((phrase or "").split())
    if not text:
        return []
    return [part.strip(" ,;") for part in _CONDITION_SPLIT_RE.split(text) if part.strip(" ,;")]
def resolve_fact_status(
    concept: str, source_phrase: str, fact_model: Mapping[str, object] | None
) -> tuple[FactModelStatus, str | None]:
    """Look the concept up in the policy set's fact model.

    Replaces a hardcoded `MISSING` on every condition. That constant happened
    to be true for a policy set with an empty `trusted_config`, but it was
    never checked — a three-value enum that only ever emitted one value, which
    is an assertion wearing the clothes of a finding.

    The fact model is keyed by *source term* (`{"age of the worker":
    {"feel_expression": "worker.ageYears"}}`), and that key exists precisely so
    source wording can be recognised. So two things count as a match, both of
    them quotation rather than similarity:

    * the concept identifier equals a configured term's identifier;
    * a configured term appears verbatim inside the condition's own sentence.

    Nothing fuzzy. Inventing a correspondence between "director recommendation"
    and some plausibly-related configured attribute is the same failure as
    inventing a fact path, and it would be harder to spot because it produces a
    green badge.

    Returns `(status, matched_term)`.
    """

    if not fact_model:
        return FactModelStatus.NOT_CONFIGURED, None

    phrase_slug = _slug(source_phrase)
    matches: list[str] = []
    for term in fact_model:
        term_slug = _slug(str(term))
        if not term_slug:
            continue
        if term_slug == concept or (phrase_slug and term_slug in phrase_slug):
            matches.append(str(term))

    if not matches:
        return FactModelStatus.MISSING, None
    if len(matches) > 1:
        # Choosing between them would be a guess about which the document
        # meant, and a wrong choice compiles into a rule that silently tests
        # the wrong thing.
        return FactModelStatus.AMBIGUOUS, " | ".join(sorted(matches))
    return FactModelStatus.MAPPED, matches[0]


def _condition_from(
    text: str, fact_model: Mapping[str, object] | None = None
) -> SourceCondition:
    """Read one condition phrase into a predicate, or record that it has none.

    The distinction this makes is the whole point of the module. A source that
    states a test and a source that names a dependency are not the same, and
    treating them alike either invents a predicate or discards one.
    """

    phrase = " ".join((text or "").split())

    def finish(
        concept: str,
        predicate_status: PredicateStatus,
        operator: str | None = None,
        value: str | None = None,
        unspecified_note: str | None = None,
    ) -> SourceCondition:
        status, matched = resolve_fact_status(concept, phrase, fact_model)
        return SourceCondition(
            source_text=phrase,
            concept=concept,
            predicate_status=predicate_status,
            operator=operator,
            value=value,
            unspecified_note=unspecified_note,
            fact_model_status=status,
            mapped_to=matched,
        )

    for pattern, operator, value in _RESOLVED_PREDICATE_RE:
        match = pattern.search(phrase)
        if not match:
            continue
        concept = " ".join(match.group("concept").split()).rstrip(".,;")
        return finish(
            _slug(concept) or _slug(phrase),
            PredicateStatus.SPECIFIED,
            operator=operator,
            # `value` is None for comparisons whose bound is the concept
            # itself ("not exceeding 5% of basic salary"): the operator and the
            # quantity are both stated, and quoting the quantity as the concept
            # keeps it verbatim rather than parsing a number out of prose.
            value=value if value is not None else concept,
        )

    match = _DEPENDENCY_ONLY_RE.search(phrase)
    if match:
        concept = " ".join(match.group("concept").split()).rstrip(".,;")
        return finish(
            _slug(concept) or _slug(phrase),
            PredicateStatus.NOT_SPECIFIED_BY_SOURCE,
            unspecified_note=(
                "the condition is stated; the source does not say what value or "
                "comparison satisfies it"
            ),
        )

    if any(marker in phrase.casefold() for marker in _DEPENDENCY_MARKERS):
        return finish(
            _slug(phrase),
            PredicateStatus.NOT_SPECIFIED_BY_SOURCE,
            unspecified_note=(
                "the condition is stated; the source does not say what satisfies it"
            ),
        )

    return finish(
        _slug(phrase),
        PredicateStatus.NOT_SPECIFIED_BY_SOURCE,
        unspecified_note="the source does not state a comparison for this condition",
    )


#: Distinguishes "no record effect supplied" from "the record has no effect".
#: A definition legitimately projects to no XACML Rule at all, so `None` is a
#: real value here and cannot double as the default.
_UNSET = object()


def xacml_effect_for(effect_type: object) -> RuleEffect | None:
    """The record's stored effect, in XACML terms.

    One mapping, used by every read path, so a rule's effect and its projection
    cannot answer "does this forbid?" differently. `informational` maps to no
    Rule at all rather than to Permit: a statement that grants and refuses
    nothing is not a XACML Rule, and calling it a permission asserts something
    the document did not.
    """

    value = getattr(effect_type, "value", effect_type)
    if value == "deny":
        return RuleEffect.DENY
    if value in {"allow", "require_action"}:
        return RuleEffect.PERMIT
    return None


def _effect_for(
    rule: CanonicalPolicyRule, modality: NormativeModality | None
) -> tuple[RuleEffect | None, str]:
    """The XACML Rule Effect, which is Permit, Deny, or no Rule at all.

    Never NotApplicable. That is a PDP result for a rule that did not apply,
    and a policy cannot declare it — the previous mapping emitted it for
    informational rules and so asserted a decision XACML has no way to express.

    A definition returns `None`: it grants and refuses nothing, so it is not a
    Rule. `None` and NotApplicable are different claims, and only one of them
    is true here.
    """

    if modality is NormativeModality.DEFINITION:
        return None, "a definition or classification states meaning; it is not a XACML Rule"
    if modality is NormativeModality.PROHIBITION:
        return RuleEffect.DENY, "the source forbids the conduct"
    if modality in (
        NormativeModality.PERMISSION,
        NormativeModality.ENTITLEMENT,
        NormativeModality.ELIGIBILITY,
    ):
        return RuleEffect.PERMIT, f"the source states a {modality.value}"
    if modality in (
        NormativeModality.OBLIGATION,
        NormativeModality.CALCULATION_REQUIREMENT,
    ):
        return (
            RuleEffect.PERMIT,
            f"the source states an {modality.value.replace('_', ' ')}; XACML carries the "
            "mandatory behaviour in an ObligationExpression, not in the Effect",
        )
    if modality is NormativeModality.DEPENDENCY:
        return (
            RuleEffect.PERMIT,
            "the source states a conditional outcome; the conditions govern whether it "
            "applies, and the outcome is carried as an Obligation",
        )
    return None, "the source's normative force could not be read, so no Effect is asserted"


def build_xacml_view(
    policy: CanonicalPolicy | None,
    fact_model: Mapping[str, object] | None = None,
    record_effect: "RuleEffect | None | object" = _UNSET,
) -> PolicyXacmlView:
    """Project one canonical policy into the four separated layers.

    `fact_model` is the policy set's `trusted_config["fact_model"]` — keyed by
    source term. Omitting it means no fact model is configured, and every
    condition reports `not_configured` rather than `missing`: those are
    different jobs, and only one of them is per-attribute.

    `record_effect` is the rule's own stored effect, expressed here in XACML
    terms. Supplied by every read path, because this projection is a
    *restatement* of that decision rather than a second opinion about it: a
    consumer that gets Deny from one field and a permission from another has
    been told opposite things about whether the policy forbids something, which
    is the worst output this system can produce.

    Re-deriving instead looks equivalent, and is — right up until the
    derivation is corrected. Records written before the fix keep their stored
    effect while the projection reports the new reading, so one record answers
    the same question two ways. Measured on a live corpus, exactly one did:
    "not exceeding 5% of the base" stored as an obligation from before
    negation-in-the-predicate was read, projected as Deny after.

    Omitting it keeps the derived reading, for callers projecting a sentence
    that has no record yet.
    """

    if policy is None or policy.rule is None:
        return PolicyXacmlView()

    rule = policy.rule
    source_text = policy.source_text or ""
    modality = _modality_for(rule)
    subjects, resources, unclassified = classify_entities(rule, source_text)

    condition_phrases = [
        phrase
        for phrase in (rule.condition, rule.prerequisite, rule.trigger, rule.temporal_constraint)
        if (phrase or "").strip()
    ]
    conditions = [
        _condition_from(part, fact_model)
        for phrase in condition_phrases
        for part in split_conditions(phrase or "")
    ]

    action_id = normalize_action(rule.predicate)
    action = (
        ClassifiedEntity(
            phrase=(rule.predicate or "").strip(),
            role=EntityRole.ACTION,
            basis="predicate head matched the normalised action vocabulary",
            normalized_id=action_id,
        )
        if action_id
        else None
    )
    if action_id is None and (rule.predicate or "").strip():
        # No action-id rather than a wrong one. The clause survives as the
        # outcome, which is what it describes.
        unclassified.append(
            ClassifiedEntity(
                phrase=(rule.predicate or "").strip(),
                role=EntityRole.UNCLASSIFIED,
                basis=(
                    "predicate matched no normalised action; emitting it as action.action-id "
                    "would produce an identifier no request can carry"
                ),
            )
        )

    effect, effect_basis = _effect_for(rule, modality)
    if record_effect is not _UNSET:
        # The record's own decision wins. See the docstring: this projection
        # restates that decision, and a second opinion about it lets one record
        # answer "does this forbid?" two ways.
        effect = record_effect  # type: ignore[assignment]

    obligations: list[ObligationExpression] = []
    if modality is NormativeModality.CALCULATION_REQUIREMENT and (rule.calculation or "").strip():
        obligations.append(
            ObligationExpression(
                obligation_id="calculation-basis",
                fulfill_on=RuleEffect.PERMIT,
                attributes={"calculation-basis": (rule.calculation or "").strip()},
            )
        )
    if (rule.constraint or "").strip():
        obligations.append(
            ObligationExpression(
                obligation_id="stated-constraint",
                fulfill_on=effect or RuleEffect.PERMIT,
                attributes={"constraint": (rule.constraint or "").strip()},
            )
        )

    advice: list[AdviceExpression] = []
    if modality is NormativeModality.DEFINITION and (rule.object or "").strip():
        advice.append(
            AdviceExpression(
                advice_id="stated-meaning",
                attributes={"meaning": (rule.object or "").strip()},
            )
        )

    required = [
        RequiredAttribute(
            attribute_id=condition.concept,
            status=condition.fact_model_status,
            source_phrase=condition.source_text,
            mapped_to=condition.mapped_to,
        )
        for condition in conditions
    ]

    if not conditions:
        compilation = (
            CompilationStatus.EXECUTABLE if effect else CompilationStatus.NOT_EXECUTABLE
        )
    elif all(c.predicate_status is PredicateStatus.SPECIFIED for c in conditions):
        compilation = CompilationStatus.PARTIALLY_EXECUTABLE
    else:
        compilation = CompilationStatus.NOT_EXECUTABLE

    return PolicyXacmlView(
        source_semantics=SourceSemantics(
            subjects=subjects,
            resources=resources,
            action=action,
            conditions=conditions,
            normative_modality=modality,
            outcome=(rule.consequence or "").strip() or None,
            unclassified=unclassified,
        ),
        xacml_projection=XacmlProjection(
            target=XacmlTarget(
                subject_ids=[s.normalized_id or s.phrase for s in subjects],
                resource_ids=[r.normalized_id or r.phrase for r in resources],
                action_ids=[action_id] if action_id else [],
            ),
            condition=conditions,
            effect=effect,
            effect_basis=effect_basis,
            obligation_expressions=obligations,
            advice_expressions=advice,
            compilation_status=compilation,
        ),
        fact_model_readiness=FactModelReadiness(
            required_attributes=required,
            fact_model_configured=bool(fact_model),
        ),
        runtime_evaluation=None,
    )
