"""Checking that an extracted rule still says what its source said.

Extraction is a chain of lossy steps: a passage is selected, decomposed into
subject/predicate/object, classified, and projected to an effect. Each step can
drop something, and the result always *looks* well-formed — a rule with a
subject, an effect and a citation reads as correct whether or not it survived
the journey intact.

This module re-reads each rule against the source text it cites and reports
where the two disagree. It is a second, independent pass by construction: it
does not consult the classification that produced the rule, only the words the
document used and the rule that came out.

Every check here is deterministic and every finding names the evidence for it.
That matters more than coverage: a faithfulness check that is itself a guess
adds a second source of error to the one it was meant to catch. Semantic drift
that no rule of this kind can see is left to the model pass, which must quote
the source for anything it asserts.

The checks exist because each corresponds to a defect found in real extracted
output, not to a category someone imagined:

* A source reading "shall NOT exceed 10%" produced a rule whose stated action
  was "exceed 10% of the employee's current basic salary" — an instruction to do
  the forbidden thing.
* A source stating "not exceeding 5%" produced a rule carrying no 5% anywhere,
  silently removing the limit.
* A source stating conditions produced a rule with an empty condition tree and
  no note that anything had been lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from policy_platform.contracts.policy import (
    CanonicalRule,
    EffectType,
    yields_no_verdict,
)
from policy_platform.infrastructure.extraction.passage_extractor import (
    _APPLICATION_SCAFFOLDING,
)

#: Negations as they appear in policy prose. Matched on word boundaries so
#: "cannot" counts and "notify" does not.
_NEGATION_RE = re.compile(
    r"\b(?:not|never|cannot|shall\s+not|must\s+not|may\s+not|no\s+longer|neither|nor)\b",
    re.IGNORECASE,
)

#: Quantities a policy turns on: percentages, money, counts, durations. A rule
#: that drops one has usually dropped the limit that made it a rule.
#:
#: `%` is matched without a trailing word boundary. An earlier version ended the
#: whole alternation with `\b`, which silently never matched a percentage: `%`
#: and the space after it are both non-word characters, so there is no boundary
#: between them and every "10%" in every document went unchecked.
#:
#: Money is matched structurally rather than by listing currencies. An earlier
#: version enumerated four codes, which meant a document denominated in any
#: other currency had its every monetary limit go unchecked — the check passed
#: because it could not see the amounts, not because they survived. A currency
#: is now any ISO-4217-shaped code (three capitals) or any Unicode currency
#: symbol, on either side of the number, which is a property of how money is
#: written rather than of which money a particular customer uses.
#:
#: Case sensitivity is scoped rather than global. The whole pattern cannot be
#: case-insensitive, because `[A-Z]{3}` would then match ordinary words and
#: read "for", "the" and "and" as currencies. It also cannot be wholly
#: case-sensitive, because a document writing "30 DAYS" or "10 PERCENT" would
#: have those limits go unchecked. The unit words therefore carry an inline
#: `(?i:…)` and the currency code does not.
_CURRENCY_SYMBOLS = "$€£¥₹₽₩₪₦₨₫₴₸₺﷼"
_UNIT_WORDS = r"(?i:percent|per\s+cent|days?|months?|years?|hours?|weeks?|times?)"
_QUANTITY_RE = re.compile(
    r"(?:"
    # A currency written before the amount: "USD 5,000", "$5,000".
    rf"(?:\b[A-Z]{{3}}\b|[{_CURRENCY_SYMBOLS}])\s*\d[\d,]*(?:\.\d+)?"
    r"|"
    # An amount followed by a percentage, a unit of time or count, or a
    # currency written after it: "10%", "30 days", "5,000 USD", "5,000 €".
    r"\b\d[\d,]*(?:\.\d+)?\s*"
    rf"(?:%|[{_CURRENCY_SYMBOLS}]|\b[A-Z]{{3}}\b|{_UNIT_WORDS}\b)"
    r")"
)

#: Effects that assert something is required or allowed. A negated source must
#: not produce one of these.
_POSITIVE_EFFECTS = frozenset({EffectType.REQUIRE_ACTION, EffectType.ALLOW})


@dataclass(frozen=True)
class FaithfulnessFinding:
    """One disagreement between a rule and the source it cites."""

    rule_id: str
    #: Stable identifier, so a consumer can filter or suppress by kind rather
    #: than by matching prose.
    code: str
    #: What a reviewer needs to decide, in one sentence.
    message: str
    #: The source text that establishes the finding. Never model-authored: a
    #: finding a reviewer cannot check against the document is an assertion.
    source_quote: str = ""
    severity: str = "warning"


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def _source_text(rule: CanonicalRule) -> str:
    formulation = rule.formulation
    canonical = formulation.canonical if formulation else None
    return _normalize(canonical.source_text if canonical else "")


def _rule_surface(
    rule: CanonicalRule,
    *,
    include_stated_condition: bool = True,
    include_description: bool = True,
) -> str:
    """Everything the rule says, as one string, for presence checks.

    Deliberately includes the condition tree, the effect action and the
    canonical decomposition: a quantity is preserved whether it landed in a
    condition, in the action, or in the object, and demanding a particular
    location would report faithful rules as defective.

    Two exclusions exist, both for the same caller, and both because a check
    asking "did this survive into the rule's operative parts" must not be
    allowed to find it in a field that merely *describes* the rule.

    `include_stated_condition` drops the canonical `condition` field, which is
    where the source's condition is recorded — comparing it against itself
    would never fire.

    `include_description` drops `description`, and this one was learned the
    hard way. `formulation_mapping` appends a provenance note to every
    description, and that note quotes the very condition it is reporting as
    lost:

        [Conditions: conditions_not_projected — The source states conditions,
         but they could not be projected into executable bindings:
         'for administrative, technical and service staff'. …]

    So `check_condition_preserved` found the condition in the surface every
    single time, concluded nothing had been lost, and returned no finding — for
    exactly the rules it was written to catch. It reported zero findings across
    47 rules while three housing-allowance rules had each dropped the staff
    category that distinguished them. The note added to make the loss legible
    is what made the loss invisible.
    """

    parts = [rule.title, rule.effect.action if rule.effect else ""]
    if include_description:
        parts.append(rule.description)
    formulation = rule.formulation
    canonical = formulation.canonical if formulation else None
    policy_rule = canonical.rule if canonical else None
    if policy_rule is not None:
        parts += [
            policy_rule.subject or "",
            policy_rule.predicate or "",
            policy_rule.object or "",
        ]
        if include_stated_condition:
            parts.append(policy_rule.condition or "")
    parts.append(rule.condition.model_dump_json() if rule.condition else "")
    for decision in (formulation.dmn_decisions if formulation else []) or []:
        projection = decision.semantic_projection
        if projection is None:
            continue
        parts += [
            projection.outcome or "",
            projection.condition_source or "",
            *(projection.conditions or []),
        ]
    return _normalize(" ".join(parts))


def check_negation_preserved(rule: CanonicalRule) -> FaithfulnessFinding | None:
    """A forbidding source must not become a requiring or permitting rule.

    The most dangerous single failure available here. "Salary shall not exceed
    10%" presented as an obligation to exceed 10% is not a degraded answer — it
    is the opposite one, delivered with the same confidence and the same
    citation.

    The test is deliberately narrow: the rule's own action must be the source's
    negated phrase *with the negation removed*. Merely finding "not" in the
    source is not enough, and an earlier version that did exactly that was right
    half the time — "in clinics that are not approved by the insurer, the
    original receipt shall be submitted to HR" carries a negation inside a
    condition while the obligation to submit is entirely real. A check that
    cries wolf on half its findings teaches a reviewer to skip it, which leaves
    the true inversions less visible than before it existed.
    """

    source = _source_text(rule)
    if not source or rule.effect is None:
        return None
    if rule.effect.type not in _POSITIVE_EFFECTS:
        return None
    action = _normalize(rule.effect.action)
    if not action:
        return None

    # If the action keeps a negation, nothing was stripped.
    if _NEGATION_RE.search(action):
        return None

    # Does the source forbid precisely what the rule now requires? Compared on
    # the opening words of the action, because a negated phrase continues into
    # its object ("not exceed 10% of the employee's basic salary") and the whole
    # action rarely matches a contiguous source span verbatim.
    head = " ".join(action.split()[:4])
    if len(head) < 6:
        return None
    pattern = re.compile(
        r"\b(?:not|never|cannot)\s+(?:be\s+)?" + re.escape(head), re.IGNORECASE
    )
    match = pattern.search(source)
    if match is None:
        return None

    return FaithfulnessFinding(
        rule_id=rule.rule_id,
        code="negation_dropped",
        message=(
            f"The source forbids '{match.group(0)}' and the rule requires '{head}…'. "
            "Read literally it now instructs the opposite of the policy."
        ),
        source_quote=match.group(0),
        severity="blocking",
    )


def check_quantities_preserved(rule: CanonicalRule) -> list[FaithfulnessFinding]:
    """Every limit the source states must survive into the rule.

    A dropped quantity is a silent weakening: "not exceeding 5%" becomes "not
    exceeding", which reads as a complete rule and enforces nothing.
    """

    source = _source_text(rule)
    if not source:
        return []
    surface = _rule_surface(rule)
    findings: list[FaithfulnessFinding] = []
    seen: set[str] = set()
    for match in _QUANTITY_RE.finditer(source):
        quantity = _normalize(match.group(0))
        key = quantity.lower().replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        # Compared on digits alone: the source may write "10%" where the rule
        # writes "10 percent", and reporting that as a loss would train a
        # reviewer to ignore this check.
        digits = re.sub(r"[^\d]", "", quantity)
        if digits and digits in re.sub(r"[^\d]", "", surface):
            continue
        if quantity.lower() in surface.lower():
            continue
        findings.append(
            FaithfulnessFinding(
                rule_id=rule.rule_id,
                code="quantity_dropped",
                message=(
                    f"The source states '{quantity}' and the rule does not carry it. "
                    "This check matches a figure beside a unit and cannot tell a ceiling "
                    "from a duration or a count, so a reviewer must read the sentence to "
                    "see what the figure governs."
                ),
                source_quote=quantity,
                severity="blocking",
            )
        )
    return findings


def check_conditions_represented(rule: CanonicalRule) -> FaithfulnessFinding | None:
    """A stated condition that reached no operative field of the rule.

    Reports "not compiled", which is what it can actually see — and that
    correction matters, because the finding used to say "The rule would apply
    unconditionally" and that is false.

    The condition it compares against is read *from* `canonical.rule.condition`,
    so this check can only fire when the condition is in the canonical record.
    A genuinely lost condition leaves that field empty, and the check returns
    None without a word — see `check_source_conditions_reached_canonical`,
    which reads the source text and is the one that can see real loss.

    What survives, for the five rules this fires on in the live corpus:

    * `formulation.canonical.rule.condition` — persisted verbatim.
    * `decision_readiness.required_attributes` — derived on read, so the
      condition ships to whatever evaluates the rule.
    * `xacml_view.source_semantics.conditions` — derived on read.
    * the Logic view and every rule row, which now display the stated condition
      rather than "Always".

    What does not: `rule.condition`, the tree the deterministic evaluator
    reads. That engine returns NOT_APPLICABLE for these rules — the vacuous
    guard stops an empty `all` matching everything — so nothing applies
    unconditionally anywhere. Severity is `warning` accordingly: a blocking
    finding on five of forty-seven rules, asserting a danger that is already
    guarded, is the false-alarm rate that teaches reviewers to skip the whole
    category.
    """

    formulation = rule.formulation
    canonical = formulation.canonical if formulation else None
    policy_rule = canonical.rule if canonical else None
    stated = _normalize(policy_rule.condition if policy_rule else "")
    if not stated:
        return None

    condition = rule.condition
    empty_tree = condition is not None and (
        (condition.type == "all" and not condition.all)
        or (condition.type == "any" and not condition.any)
    )
    if not empty_tree:
        return None

    surface = _rule_surface(
        rule, include_stated_condition=False, include_description=False
    )
    if stated.lower() in surface.lower():
        # Restated in an operative field, so a reader of the rule alone still
        # sees it. Nothing to report.
        #
        # `description` is excluded from that surface deliberately — see
        # `_rule_surface`. The provenance note appended there quotes the
        # condition verbatim, so including it satisfied this test for every
        # rule and the check never fired once.
        return None

    return FaithfulnessFinding(
        rule_id=rule.rule_id,
        code="condition_not_compiled",
        message=(
            f"The source conditions this rule ('{stated[:80]}') and no fact model compiles "
            "it, so the deterministic evaluator cannot test it and returns NOT_APPLICABLE. "
            "The condition is preserved verbatim in the canonical record and ships with the "
            "rule; what is missing is an attribute mapping, which is configuration rather "
            "than a defect in the extraction."
        ),
        source_quote=stated[:160],
        severity="warning",
    )


#: Constructions that introduce a condition in policy prose. Used only to ask
#: whether the *canonical record* captured a condition the source plainly
#: states — never to build one, and never to guess its test.
#:
#: Anchored to reduce false positives: "provided" alone is a common past
#: participle ("housing provided by FBSU"), so only "provided that" counts.
_SOURCE_CONDITION_RE = re.compile(
    r"\b(?:if|unless|provided\s+that|subject\s+to|depending\s+on|conditional\s+upon"
    r"|in\s+the\s+(?:case|event)\s+of|only\s+if|only\s+when|where\s+the|upon\s+approval"
    r"|after\s+the|before\s+the|so\s+long\s+as|as\s+long\s+as)\b",
    re.IGNORECASE,
)

#: Canonical fields any one of which means the source's condition was captured
#: somewhere. A condition legitimately lands in whichever of these fits, so
#: demanding it be in `condition` specifically would report faithful records as
#: defective — the same named-slot mistake that duplicate detection made twice.
_CONDITION_BEARING_FIELDS = (
    "condition",
    "prerequisite",
    "trigger",
    "temporal_constraint",
    "constraint",
    "exception",
    "location",
)


def check_source_conditions_reached_canonical(
    rule: CanonicalRule,
    siblings: "list[CanonicalRule] | None" = None,
) -> FaithfulnessFinding | None:
    """The source states a condition and nothing captured it.

    This is the check that can see real loss, and it did not exist. Its
    sibling above compares against `canonical.rule.condition` and so can only
    fire when the condition is present — a check that reads its expected value
    from the record it is auditing cannot report that record as empty.

    The lossy step is source text -> canonical decomposition, so that is where
    this reads. It asks only whether *something* conditional was captured, and
    never what the test should be: deciding that would manufacture policy the
    document did not write.

    `siblings` are the other rules formulated from the same sentence, and they
    matter because one sentence legitimately becomes several rules. "3.2.3.
    Increase due to inflation with a percentage not exceeding 5% of the
    employee's basic salary, and subject to the judgment and approval of the
    Board of Trustees" became two: one carrying the 5% limit, one carrying the
    Board's approval. Judged alone the first appears to have dropped "subject
    to"; judged with its sibling the sentence is fully captured, and it was
    reported blocking for a decomposition that had lost nothing.
    """

    # A record that decides nothing has no decision to be incomplete. "Please
    # check with the HR department about the latest Covid regulations as these
    # are subject to change" states a conditional ("subject to") and captures no
    # condition, both true, neither a defect: the record is guidance, and its
    # whole content is "go and ask". See `yields_no_verdict`.
    if yields_no_verdict(rule):
        return None

    formulation = rule.formulation
    canonical = formulation.canonical if formulation else None
    if canonical is None:
        return None
    source = canonical.source_text or ""
    match = _SOURCE_CONDITION_RE.search(source)
    if not match:
        return None

    marker = " ".join(match.group(0).split()).casefold()

    def captures(candidate: CanonicalRule) -> bool:
        can = candidate.formulation.canonical if candidate.formulation else None
        if can is None or (can.source_text or "") != source:
            return False
        policy_rule = can.rule
        if any(
            (getattr(policy_rule, field, None) or "").strip()
            for field in _CONDITION_BEARING_FIELDS
        ):
            return True
        # The marker may be absorbed into the rule's own predicate or object
        # rather than placed in a condition-bearing field, and that is capture
        # too: in "The recommendations of the director are subject to the
        # approval of the President" the dependency *is* the rule. Without
        # this, every blocking finding the check produced on the live corpus
        # was a false positive — 3 of 46 rules — which is worse than no check,
        # because it teaches reviewers that blocking findings are noise.
        absorbed = " ".join(
            (getattr(policy_rule, field, None) or "")
            for field in ("subject", "predicate", "object")
        )
        return marker in " ".join(absorbed.split()).casefold()

    if captures(rule):
        return None
    if siblings and any(captures(other) for other in siblings if other is not rule):
        return None

    return FaithfulnessFinding(
        rule_id=rule.rule_id,
        code="source_condition_not_captured",
        message=(
            f"The source uses conditional language ('{match.group(0)}') and the canonical "
            "decomposition records no condition, prerequisite, trigger or constraint at "
            "all, nor is it absorbed into the subject, predicate or object. The sentence "
            "is still held verbatim in the record; what no field carries is the "
            "dependency it states, so anything reading the decomposition alone misses it."
        ),
        source_quote=source[:160],
        severity="blocking",
    )


def check_action_is_not_a_fragment(rule: CanonicalRule) -> FaithfulnessFinding | None:
    """An obligation's action must be something a reader could carry out.

    "is calculated as twice the monthly basic salary up to a maximum of" is a
    sentence fragment, not work. It appeared because a rule that derives a value
    was projected as an obligation, and the fragment is the tell that the
    projection was wrong rather than merely terse.
    """

    if rule.effect is None or rule.effect.type is not EffectType.REQUIRE_ACTION:
        return None
    action = _normalize(rule.effect.action)
    if not action:
        return FaithfulnessFinding(
            rule_id=rule.rule_id,
            code="action_missing",
            message="The rule requires an action but names none.",
            severity="blocking",
        )
    # A trailing preposition or copula is the reliable signal of a clause cut
    # mid-thought. Checked on the final word only, so a long but complete action
    # is not reported.
    if re.search(r"\b(?:of|as|to|for|by|with|from|than|is|are|be)\s*$", action, re.IGNORECASE):
        return FaithfulnessFinding(
            rule_id=rule.rule_id,
            code="action_fragment",
            message=(
                f"The required action ends mid-thought ('…{action[-48:]}'), so it does not "
                "name work anything could carry out."
            ),
            source_quote=action[-80:],
            severity="warning",
        )
    return None


def check_passage_is_not_scaffolded(rule: CanonicalRule) -> FaithfulnessFinding | None:
    """A cited passage must be the document's words, not this application's.

    The extractor renders clauses into a batch for the model, and that batch
    carries labels the application adds: `(section: …)`, `(columns: …)`,
    `[clause_ref=…]`. A model that copied one into the passage it returned
    produced a `source_text` that is not in the customer's document.

    It survived `verify_verbatim` because that check proves containment against
    the *rendered batch* -- document plus labels -- so a passage that copied a
    label was checked against the copy of the label rather than against the
    document. The extractor now strips these before verification, but records
    written before that fix are already approved and published, and nothing
    reported them: a published run named the affected rules only through an
    unrelated low-severity finding and never mentioned the label at all.

    Blocking, because a passage is the whole product promise. Every other
    finding here says a rule disagrees with its source; this one says the
    source as quoted does not exist.

    The patterns are imported rather than restated. They are the extraction
    layer's own record of what it adds to a document, and a second copy here
    would be a second opinion that drifts -- which is how a check ends up
    judging something narrower than the thing it is checking.
    """

    text = _source_text(rule)
    if not text:
        return None
    for pattern in _APPLICATION_SCAFFOLDING:
        match = pattern.match(text)
        if match:
            label = _normalize(match.group(0))
            return FaithfulnessFinding(
                rule_id=rule.rule_id,
                code="passage_carries_application_scaffolding",
                message=(
                    f"The cited passage begins with {label!r}, which this application adds "
                    "when it renders a document for extraction. The document does not "
                    "contain it, so the passage is not verbatim and a reader checking the "
                    "citation against the source will not find it."
                ),
                source_quote=text[: len(label) + 80],
                severity="blocking",
            )
    return None


def validate_rule(
    rule: CanonicalRule, siblings: "list[CanonicalRule] | None" = None
) -> list[FaithfulnessFinding]:
    """Every faithfulness check, for one rule.

    `siblings` lets the checks that need corpus context see it. Passed rather
    than looked up, so a single rule can still be validated on its own.
    """

    findings: list[FaithfulnessFinding] = []
    for single in (
        check_negation_preserved(rule),
        check_conditions_represented(rule),
        check_source_conditions_reached_canonical(rule, siblings),
        check_action_is_not_a_fragment(rule),
        check_passage_is_not_scaffolded(rule),
    ):
        if single is not None:
            findings.append(single)
    findings.extend(check_quantities_preserved(rule))
    return findings


def validate_rules(rules: list[CanonicalRule]) -> list[FaithfulnessFinding]:
    """Every faithfulness check, across a run.

    Per-rule checks plus the corpus-level duplicate check, which cannot run
    from inside a single rule: each copy of a duplicate is individually
    faithful to the sentence it cites, so the defect is only visible from
    outside both.
    """

    findings = [finding for rule in rules for finding in validate_rule(rule, rules)]
    findings.extend(find_duplicate_rules(rules))
    return findings


#: Function words that appear or vanish purely because of where a phrase was
#: cut, not because the policy says something different.
#:
#: When a clause boundary falls mid-sentence, the same content redistributes
#: across canonical slots and gains or loses a connective at the seam: object
#: "one employee" + condition "of the married couple" against object "one
#: employee of the married couple"; object "in monthly prorated installments"
#: against constraint "prorated installments" + frequency "monthly". The
#: content words are identical in both; only the joinery moves.
#:
#: Deliberately excludes the prepositions that can invert a relation -- `by`,
#: `to`, `from`, `before`, `after`, `without`, `not`. "paid by HR" and "paid to
#: HR" name different parties, and collapsing them would report two real rules
#: as one copy. The words listed here cannot carry that distinction on their
#: own: whatever they attach to survives as a content word either way.
_SEAM_WORDS = frozenset(
    {"a", "an", "the", "of", "in", "on", "at", "and", "or", "as", "for", "its", "their", "this"}
)


def _content_signature(policy_rule: object) -> str:
    """The rule's content, independent of which canonical slot holds what.

    Named fields were tried first and failed in both directions on live data.
    Keying on `object` alone reported two housing-allowance rules capped at the
    same amount as duplicates, because it dropped the condition -- "for
    administrative, technical and service staff" against "for full time
    lecturers, instructors..." -- which is the only thing separating them.
    Adding `condition` fixed that pair and still missed a genuine duplicate,
    because that sentence had decomposed into different slots on the two runs.

    Naming more fields keeps losing the same race. The failure is not that the
    *right* slots were left unnamed; it is that a slot assignment is a
    judgement the formulator makes per run, so no fixed list of slots is stable
    across runs. Reading every qualifying field as one bag of content words is
    stable by construction, and it generalises to slot variance nobody has
    observed yet.

    Exact set equality only, never an overlap threshold. Two rules sharing most
    of their words are not evidence of anything, and a check that guesses adds
    a second source of error to the one it was meant to catch.
    """

    if policy_rule is None:
        return ""
    # Every field that can carry content. The structural anchors (subject,
    # predicate) are excluded because they are compared separately, so that
    # "A limits B" and "B limits A" cannot collide; the bookkeeping fields
    # describe the extraction rather than the policy.
    dumped = policy_rule.model_dump(exclude_none=True)
    for field in ("rule_type", "source_origin", "subject", "predicate", "modality"):
        dumped.pop(field, None)
    words = _normalize(" ".join(str(v) for v in dumped.values())).lower().split()
    return " ".join(sorted({w for w in words if w not in _SEAM_WORDS}))


def find_duplicate_rules(rules: "list[CanonicalRule]") -> list[FaithfulnessFinding]:
    """Rules whose content is identical to another rule's.

    A corpus-level check, because a duplicate is invisible from inside either
    copy: each is individually faithful to the sentence it cites.

    Both live examples were caused by a clause boundary falling mid-sentence.
    "The housing allowance is limited to one employee of the married couple
    (husband and wife). In the case of a married couple are employed by FBSU..."
    was split between "married couple" and "(husband and wife)", so the second
    clause begins mid-sentence; the formulator then reconstructs the governing
    sentence from inherited context and produces a rule the first clause had
    already produced. Reported rather than silently de-duplicated, because
    which copy to keep depends on which clause carries the better evidence, and
    that is a reviewer's call.

    Keyed on subject, predicate and a slot-independent content signature -- see
    `_content_signature` for why naming fields could not work. Title,
    description and the effect action are all excluded: each is *derived* from
    the fields above, so including one double-counts them, and a difference in
    that derivation ("is limited to one employee" against "is limited to one
    employee of the married couple") was enough to hide the very pair this
    check was added for.
    """

    seen: dict[tuple[str, str, str], str] = {}
    findings: list[FaithfulnessFinding] = []
    for rule in rules:
        canonical = rule.formulation.canonical if rule.formulation else None
        policy_rule = canonical.rule if canonical else None
        key = (
            _normalize(policy_rule.subject if policy_rule else "").lower(),
            _normalize(policy_rule.predicate if policy_rule else "").lower(),
            _content_signature(policy_rule),
        )
        if not any(key):
            continue
        first = seen.get(key)
        if first is None:
            seen[key] = rule.rule_id
            continue
        findings.append(
            FaithfulnessFinding(
                rule_id=rule.rule_id,
                code="duplicate_rule",
                message=(
                    f"This rule's subject, predicate and remaining content match {first}'s "
                    "once wording is normalised. The two source citations were not "
                    "compared, so read them before deciding: in both live examples the "
                    "pair came from one sentence cut by a clause boundary, but a genuine "
                    "restatement in two places looks the same to this check. A reviewer "
                    "keeps the copy whose clause carries the better evidence."
                ),
                source_quote=(canonical.source_text if canonical else "")[:160],
                severity="warning",
            )
        )
    return findings
