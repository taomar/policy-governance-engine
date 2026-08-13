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
    """What must happen next. Not a scale.

    Three values, and they are not three rungs of one ladder — a finding is
    sorted by *who can act on it*, which is the only thing a reviewer needs
    from this field. A graduated scale invites triage-by-severity, and the
    whole point of this pass is that an unsupported claim is either present or
    it is not; there is no "mostly traceable".

    An earlier version keyed severity off whether the record declared
    `source_origin`. Measured over a live corpus that correlated 100% with
    provenance being declared and 0% with what had actually gone wrong: it
    blocked hardest on flattened table structure, which no reviewer can repair
    by editing wording, and merely flagged genuinely fabricated phrases. A
    check whose most severe finding is the one nobody can act on teaches
    reviewers that severity is noise, so severity now follows the *nature of
    the mismatch*.
    """

    #: The record states something the source does not. Publishing it would
    #: ship a claim about the customer's policy that the policy never made.
    #: A reviewer can act: correct the wording or reject the record.
    BLOCKING = "blocking"
    #: The record's words are damaged by how the document was *read*, not by
    #: what it says — most often several table cells welded into one attribute.
    #: A reviewer cannot fix this by editing; the source structure has to be
    #: read again. Routed here so it is never presented as a wording decision.
    REEXTRACTION = "reextraction"
    #: Traceable, but a reviewer should see it. It does not misstate the
    #: source, so it does not block.
    REVIEW = "review"


class LogicFinding(BaseModel):
    """One thing the second pass could not verify."""

    code: str
    severity: LogicFindingSeverity
    #: Why the phrase is not a quotation. Carried alongside severity because
    #: severity says who can act and this says what happened, and a reviewer
    #: shown only the first has to guess the second.
    shape: "MismatchShape | None" = None
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


class MismatchShape(str, Enum):
    """Why a phrase is not a contiguous quotation of its sentence.

    Every test below is structural — layout separators, word order, word
    presence. None of them knows a language, a domain or a document, because a
    classifier that recognised particular wording would bound the wording it
    was shown rather than the shapes a mismatch can take.
    """

    #: Several cells welded into one attribute. The claim still carries the
    #: separators the layout used, so the record is quoting a whole table row
    #: where the document had distinct values.
    CONCATENATED = "concatenated"
    #: Every word is present, in the order the claim states them, with other
    #: words interleaved. This is what lifting one branch out of a coordinated
    #: phrase looks like — "The disclosure, distribution ... or copying of X"
    #: yielding "distribution of X" — and it is correct decomposition.
    DECOMPOSED = "decomposed"
    #: In order, but the words skipped over reverse the clause. The mechanics
    #: look identical to DECOMPOSED, which is exactly the danger: dropping
    #: "not" from "may not enter" leaves a perfect subsequence that states the
    #: opposite of the sentence.
    INVERTED = "inverted"
    #: The claim shares no word with the sentence, so it was supplied from
    #: outside it — a pronoun, a heading, or a governing clause.
    SUPPLIED = "supplied"
    #: Some of the sentence's words, reassembled into a phrase it does not
    #: contain. This is the shape a paraphrase takes when it passes for a
    #: quotation, and the one that ships a claim the document never made.
    UNSUPPORTED = "unsupported"


#: Characters a layout uses to separate one value from the next. Presence of
#: one *inside a single attribute* means the extraction carried a boundary into
#: a field that should hold one value.
_CELL_SEPARATOR_RE = re.compile(r"[|\n\r\t]|;\s")

#: Words that reverse the force of a clause. Only consulted for words the claim
#: *skipped*: a subsequence that steps over a negation is not a shorter way of
#: saying the sentence, it is the opposite of it.
_REVERSING_RE = re.compile(
    r"^(?:not|never|no|nor|cannot|non|without|except|unless|neither)$", re.IGNORECASE
)


def _subsequence_gap_words(claim: str, source: str) -> list[str] | None:
    """The source words a claim steps over *between* its own words.

    The text before the first match and after the last is deliberately not
    counted. A phrase that begins part-way through a sentence has not "skipped"
    the words before it — it simply starts there, and those words belong to a
    different part of the clause. Counting them read the recipient of
    "Employees may not disclose X to anyone who is not employed by AIS" as
    having dropped the sentence's "not", because the main verb sits in front of
    where the recipient begins.

    Matching is leftmost-greedy, so a word occurring several times is anchored
    at its first available position. That can only widen a gap, never narrow
    one, so the caller reads the result as evidence a claim *may* have stepped
    over something rather than proof it did.
    """

    claim_words = _normalise(claim).split()
    source_words = _normalise(source).split()
    if not claim_words:
        return None
    cursor = 0
    skipped: list[str] = []
    first = True
    for word in claim_words:
        try:
            found = source_words.index(word, cursor)
        except ValueError:
            return None
        if not first:
            skipped.extend(source_words[cursor:found])
        first = False
        cursor = found + 1
    return skipped


def classify_mismatch(claim: str, source: str) -> MismatchShape:
    """Why this phrase is not a quotation — tested in order of confidence.

    Separators are read first because they are the least ambiguous signal
    available: a value containing a cell boundary came from more than one cell,
    whatever else is true of its words.
    """

    if _CELL_SEPARATOR_RE.search(claim or ""):
        return MismatchShape.CONCATENATED
    skipped = _subsequence_gap_words(claim, source)
    if skipped is not None:
        if any(_REVERSING_RE.match(word) for word in skipped):
            return MismatchShape.INVERTED
        return MismatchShape.DECOMPOSED
    claim_words = set(_normalise(claim).split())
    if not claim_words & set(_normalise(source).split()):
        return MismatchShape.SUPPLIED
    return MismatchShape.UNSUPPORTED


#: What a reviewer can do about each shape, and therefore how it is ranked.
#: `DECOMPOSED` is absent because it is not a defect: it is what a correct
#: decomposition of a coordinated phrase looks like, and reporting correct
#: behaviour is how a check teaches reviewers to ignore it.
_SHAPE_SEVERITY: dict[MismatchShape, LogicFindingSeverity] = {
    MismatchShape.UNSUPPORTED: LogicFindingSeverity.BLOCKING,
    MismatchShape.INVERTED: LogicFindingSeverity.BLOCKING,
    MismatchShape.CONCATENATED: LogicFindingSeverity.REEXTRACTION,
    MismatchShape.SUPPLIED: LogicFindingSeverity.REVIEW,
}


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

    Severity follows the *shape* of the mismatch (see `classify_mismatch`), so
    a fabricated phrase outranks a flattened table row and a correct
    decomposition is not reported at all.

    `inherited_context` is the canonical record's own `source_origin` signal.
    It explains one shape and only one: a phrase sharing no word with this
    sentence, which a rule formulated under a governing stem legitimately
    carries — "Increase due to inflation ... 5% of the employee's basic
    salary" decomposes to subject "Employee basic salary", which lives in the
    parent clause. It is a modifier on what the reviewer is told, not the axis
    that decides severity: a declared provenance cannot make an invented word
    quoted, and reading it as though it could is what mis-ranked this check.
    """

    findings: list[LogicFinding] = []
    for attribute in assessment.attributes_referenced:
        if _is_quoted_from(attribute.phrase, source_text):
            continue
        shape = classify_mismatch(attribute.phrase, source_text)
        if shape is MismatchShape.DECOMPOSED:
            continue
        findings.append(
            LogicFinding(
                code="attribute_not_in_source",
                severity=_SHAPE_SEVERITY[shape],
                shape=shape,
                claim=attribute.phrase,
                source_excerpt=source_text[:400],
                detail=_attribute_detail(shape, attribute.role, inherited_context),
            )
        )
    return findings


def _attribute_detail(role_shape: MismatchShape, role: str, inherited: bool) -> str:
    """Say what went wrong in the words that are true of *this* mismatch."""

    lead = f"the extraction target derived from canonical '{role}'"
    if role_shape is MismatchShape.CONCATENATED:
        return (
            f"{lead} carries a cell boundary, so several of the row's values were "
            "read into one attribute. The document's structure was flattened when "
            "it was read; re-extract the source rather than editing the wording, "
            "which cannot separate values the record no longer holds apart"
        )
    if role_shape is MismatchShape.INVERTED:
        return (
            f"{lead} quotes the sentence in order but steps over a word that "
            "reverses it, so the attribute states the opposite of the source "
            "while reading as a clean quotation"
        )
    if role_shape is MismatchShape.SUPPLIED:
        return (
            f"{lead} shares no wording with this sentence, so it was supplied from "
            "outside it"
            + (
                "; the rule declares inherited context, so it may come from the "
                "governing clause — a reviewer should confirm it does"
                if inherited
                else " — a reviewer should confirm the document says it somewhere"
            )
        )
    return (
        f"{lead} reuses this sentence's words in an order the sentence does not, "
        "so an evaluator would be told to look for wording the policy never used"
    )


def check_parties_are_quoted(
    assessment: EvaluabilityAssessment,
    source_text: str,
    inherited_context: bool = False,
) -> list[LogicFinding]:
    """Every named party must be in the source.

    An invented approver is the worst failure this pass can catch: it tells a
    customer that someone must sign off when the document never said so, and
    it is the kind of claim nobody re-reads the source to check.

    Which is exactly why the finding must not overstate itself. An earlier
    version reported "the rule asserts a party the document does not name"
    for every mismatch, including ones where the document names them plainly
    and only contiguity failed — the claim dropping a single linking word. A
    quality check that overclaims its own finding is the defect this module
    exists to catch, sitting inside the checker.
    """

    findings: list[LogicFinding] = []
    for party in assessment.parties:
        if _is_quoted_from(party.name, source_text):
            continue
        shape = classify_mismatch(party.name, source_text)
        if shape is MismatchShape.DECOMPOSED:
            continue
        findings.append(
            LogicFinding(
                code="party_not_in_source",
                severity=_SHAPE_SEVERITY[shape],
                shape=shape,
                claim=party.name,
                source_excerpt=source_text[:400],
                detail=_party_detail(
                    shape, party.role.value, party.source_field, inherited_context
                ),
            )
        )
    return findings


def _party_detail(shape: MismatchShape, role: str, source_field: str, inherited: bool) -> str:
    """Say only what this mismatch establishes about the party."""

    lead = f"the {role} named from '{source_field}'"
    if shape is MismatchShape.CONCATENATED:
        return (
            f"{lead} carries a cell boundary, so more than one of the row's values "
            "was read as a single party. Re-extract the source; the record no "
            "longer holds the names apart for a reviewer to separate"
        )
    if shape is MismatchShape.INVERTED:
        return (
            f"{lead} quotes the sentence in order but steps over a word that "
            "reverses it, so the party is attached to the opposite of what the "
            "document says"
        )
    if shape is MismatchShape.SUPPLIED:
        return (
            f"{lead} shares no wording with this sentence, so it was supplied from "
            "outside it"
            + (
                "; the rule declares inherited context, so the name may come from "
                "the governing clause — a reviewer should confirm it does"
                if inherited
                else " — a reviewer should confirm the document names them"
            )
        )
    return (
        f"{lead} reuses this sentence's words in an order the sentence does not, "
        "so the rule asserts a party the document does not name"
    )


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
