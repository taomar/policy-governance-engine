"""Second pass over the *formed logic*, after it exists.

`policy_faithfulness` validates the rule surface — title, action, effect —
against the sentence it cites. Nothing validated the logic that gets built on
top of that surface: the projected conditions, the attributes an evaluator is
told to go and find, and the parties it is told decide. Those are derived, and
derived material is exactly where a confident-looking claim can appear without
anything behind it.

The check is deliberately one-directional. It asks only *"is every derived
claim traceable to the source?"* — never *"did we derive everything we
could?"*. Completeness cannot be judged without a second opinion about what
the document meant, and asserting that opinion is the failure this codebase
exists to avoid. A missed condition is a gap; an invented one is a lie, and
only the second is detectable from the evidence alone.

Every finding names the claim, quotes the source it failed to match, and says
which pass produced it, so a reviewer can act without re-reading the document.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum

from pydantic import BaseModel, Field

from policy_platform.contracts.formulation import CanonicalPolicy
from policy_platform.infrastructure.extraction.evaluability import (
    Evaluability,
    EvaluabilityAssessment,
    assess_policy,
)
from policy_platform.infrastructure.extraction.policy_parties import PartyProvenance, PartyRole


class LogicFindingSeverity(str, Enum):
    """How a reviewer should treat the finding.

    Two levels, not five. A scale invites triage-by-severity, and the whole
    point of this pass is that an unsupported claim is either present or it is
    not — there is no "mostly traceable".
    """

    #: The logic asserts something the source does not support. Publishing it
    #: would ship a claim about the customer's policy that the policy never
    #: made.
    BLOCKING = "blocking"
    #: The logic is traceable but incomplete in a way a reviewer should see —
    #: it does not misstate the source, so it does not block.
    REVIEW = "review"


class LogicFinding(BaseModel):
    """One thing the second pass could not verify."""

    code: str
    severity: LogicFindingSeverity
    #: The derived claim being challenged, quoted.
    claim: str
    #: What the source actually says, quoted, so the reviewer can compare
    #: without opening the document.
    source_excerpt: str
    #: What to do about it, in one sentence.
    detail: str


#: Unicode quotes and dashes differ between the PDF text layer and anything
#: retyped from it, so a byte comparison reports a mismatch that is really a
#: typographic difference. Normalising both sides is the same treatment
#: `policy_faithfulness` applies for the same reason.
_QUOTE_MAP = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_DASH_RE = re.compile(r"[\u2010-\u2015]")
_NON_WORD_RE = re.compile(r"[^\w\s%]+")


def _normalise(text: str) -> str:
    """Collapse a string to a form two copies of the same words will share."""

    folded = unicodedata.normalize("NFKC", text or "").translate(_QUOTE_MAP)
    folded = _DASH_RE.sub("-", folded)
    folded = _NON_WORD_RE.sub(" ", folded)
    return " ".join(folded.casefold().split())


def _is_quoted_from(claim: str, source: str) -> bool:
    """True when `claim` is a contiguous quotation of `source`.

    Substring containment after normalisation, not token overlap. Overlap
    would accept a claim assembled from words that appear in the sentence in a
    different order — which is precisely how a paraphrase passes for a
    quotation.
    """

    normalised_claim = _normalise(claim)
    if not normalised_claim:
        return False
    return normalised_claim in _normalise(source)


def check_attributes_are_quoted(
    assessment: EvaluabilityAssessment,
    source_text: str,
    inherited_context: bool = False,
) -> list[LogicFinding]:
    """Every attribute the evaluator is told to find must be in the source.

    These phrases become the extraction targets shipped to the customer. An
    attribute that is not in the document sends the evaluating LLM looking for
    something the policy never mentioned, and whatever it finds instead is
    then treated as the policy's own term.

    `inherited_context` is the canonical record's own `source_origin` signal.
    A rule formulated from a governing stem legitimately carries fields that
    are not in its own sentence — "Increase due to inflation ... 5% of the
    employee's basic salary" decomposes to subject "Employee basic salary",
    which lives in the parent clause. Calling that an invention would condemn
    the enumeration handling the platform deliberately performs. It still
    cannot be verified from this sentence, so it is surfaced for review rather
    than either blocked or silently accepted.
    """

    severity = (
        LogicFindingSeverity.REVIEW if inherited_context else LogicFindingSeverity.BLOCKING
    )
    findings: list[LogicFinding] = []
    for attribute in assessment.attributes_referenced:
        if _is_quoted_from(attribute.phrase, source_text):
            continue
        findings.append(
            LogicFinding(
                code="attribute_not_in_source",
                severity=severity,
                claim=attribute.phrase,
                source_excerpt=source_text[:400],
                detail=(
                    f"the extraction target derived from canonical '{attribute.role}' "
                    "is not a quotation of the sentence it came from"
                    + (
                        "; the rule declares inherited context, so it may come from the "
                        "governing clause — a reviewer should confirm it does"
                        if inherited_context
                        else ", so an evaluator would be told to look for wording the "
                        "policy never used"
                    )
                ),
            )
        )
    return findings


def check_parties_are_quoted(
    assessment: EvaluabilityAssessment,
    source_text: str,
    inherited_context: bool = False,
) -> list[LogicFinding]:
    """Every named party must be in the source.

    An invented approver is the worst failure this pass can catch: it tells a
    customer that someone must sign off when the document never said so, and
    it is the kind of claim nobody re-reads the source to check.
    """

    severity = (
        LogicFindingSeverity.REVIEW if inherited_context else LogicFindingSeverity.BLOCKING
    )
    findings: list[LogicFinding] = []
    for party in assessment.parties:
        if _is_quoted_from(party.name, source_text):
            continue
        findings.append(
            LogicFinding(
                code="party_not_in_source",
                severity=severity,
                claim=party.name,
                source_excerpt=source_text[:400],
                detail=(
                    f"the {party.role.value} named from '{party.source_field}' is not "
                    "quoted from the sentence, so the rule asserts a party the "
                    "document does not name"
                ),
            )
        )
    return findings


def check_authority_is_a_delegation(
    assessment: EvaluabilityAssessment, source_text: str
) -> list[LogicFinding]:
    """An authority read from wording must survive a negation check.

    "clinics and hospitals that are **not** approved by the insurance company"
    once yielded the insurer as the rule's authority: the match dropped the
    negation and turned a qualifier on *which hospitals count* into a claim
    that the insurer approves the rule. The pattern was narrowed, and this
    check keeps a future widening from reintroducing it silently.

    Scoped to authorities read from wording. One read from a canonical field
    is the formulator's own decomposition and is not re-litigated here.
    """

    findings: list[LogicFinding] = []
    normalised = _normalise(source_text)
    for party in assessment.parties:
        if party.role is not PartyRole.AUTHORITY:
            continue
        if party.provenance is not PartyProvenance.DELEGATION_PHRASE:
            continue
        marker = _normalise(party.source_field)
        position = normalised.find(marker)
        if position < 0:
            continue
        preceding = normalised[:position].split()[-4:]
        if any(word in {"not", "never", "without", "nor"} for word in preceding):
            findings.append(
                LogicFinding(
                    code="authority_from_negated_phrase",
                    severity=LogicFindingSeverity.BLOCKING,
                    claim=party.name,
                    source_excerpt=source_text[:400],
                    detail=(
                        f"'{party.source_field}' is negated in the source, so this "
                        "party does not decide the rule — reporting them inverts the "
                        "sentence"
                    ),
                )
            )
    return findings


def check_discretion_names_who(
    assessment: EvaluabilityAssessment, source_text: str
) -> list[LogicFinding]:
    """A delegated decision with no named decision-maker is reviewable.

    Not blocking: "may be granted" is a faithful reading of a document that
    genuinely did not say who grants it. The gap is real and belongs to the
    policy, so it is surfaced rather than suppressed — and rather than filled
    in by guessing the most senior party mentioned nearby.
    """

    if assessment.evaluability is not Evaluability.DISCRETIONARY:
        return []
    if any(p.role is PartyRole.AUTHORITY for p in assessment.parties):
        return []
    return [
        LogicFinding(
            code="discretion_without_authority",
            severity=LogicFindingSeverity.REVIEW,
            claim=assessment.reason,
            source_excerpt=source_text[:400],
            detail=(
                "the source delegates this decision but never names who exercises it, "
                "so an evaluator can say approval is needed but not from whom"
            ),
        )
    ]


def check_malformed_is_reported(
    assessment: EvaluabilityAssessment, source_text: str
) -> list[LogicFinding]:
    """A damaged decomposition must not be published as though it were sound.

    Blocking because the failure is ours, not the document's: "may may also be
    eligible" means the sentence was mis-split, and every downstream claim
    built on that split inherits the error.
    """

    if assessment.evaluability is not Evaluability.MALFORMED:
        return []
    return [
        LogicFinding(
            code="decomposition_malformed",
            severity=LogicFindingSeverity.BLOCKING,
            claim=assessment.reason,
            source_excerpt=source_text[:400],
            detail=(
                "the canonical decomposition is damaged, so the logic derived from it "
                "cannot be trusted and the sentence needs re-extracting"
            ),
        )
    ]


#: Run in this order. Quotation checks come first because an unquotable claim
#: makes every later judgement about it meaningless. The first two take the
#: canonical record's `source_origin` signal; the rest do not need it.
_QUOTATION_CHECKS = (check_attributes_are_quoted, check_parties_are_quoted)
_CHECKS = (
    check_authority_is_a_delegation,
    check_malformed_is_reported,
    check_discretion_names_who,
)


class LogicVerdict(BaseModel):
    """The result of judging one rule's formed logic."""

    findings: list[LogicFinding] = Field(default_factory=list)

    @property
    def blocking(self) -> list[LogicFinding]:
        return [f for f in self.findings if f.severity is LogicFindingSeverity.BLOCKING]

    @property
    def passed(self) -> bool:
        """No blocking finding. Review findings are information, not failure."""

        return not self.blocking


def judge_logic(policy: CanonicalPolicy | None) -> LogicVerdict:
    """Form the logic, then judge it against the sentence it came from."""

    if policy is None:
        return LogicVerdict()
    assessment = assess_policy(policy)
    source_text = policy.source_text or ""
    # The canonical record says for itself whether it drew on a governing
    # clause. Reading that signal is not the same as excusing an unverifiable
    # claim — it decides whether the claim blocks or goes to a reviewer.
    inherited = bool((getattr(policy.rule, "source_origin", None) or "").strip())
    findings: list[LogicFinding] = []
    for quotation_check in _QUOTATION_CHECKS:
        findings.extend(quotation_check(assessment, source_text, inherited))
    for check in _CHECKS:
        findings.extend(check(assessment, source_text))
    return LogicVerdict(findings=findings)
