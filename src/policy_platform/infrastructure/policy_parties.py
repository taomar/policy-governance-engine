"""Who a rule concerns — extracted, named, and traceable to source text.

The canonical contract has had `actor`, `assigner`, `beneficiary`, `candidate`
and `recipient` since Section 21. Across the AD-103 extraction `actor` was
populated 0 times out of 45 and `assigner` 0 times, so no party was visible
anywhere in the product: "The exceptional increase requires the approval of
the President" decomposed to subject/predicate/object with "the President"
buried inside the object string.

That is two defects at two boundaries, and both are fixed:

* Section 21 lists the party fields without defining them against `subject`,
  so the formulator had no basis to choose one. Corrected in the prompt.
* Nothing downstream ever assembled a party list, so even the fields that
  *were* populated (`beneficiary` 6, `recipient` 1) went unread. Corrected
  here.

This module is not a workaround for the prompt. A party list is a contract
need in its own right: the shipped JSON is evaluated by an LLM against a
customer's case, and "who does this govern, and who decides it" is a question
that evaluation must answer. It also keeps working on the 45 rules already
extracted, which a prompt fix alone would leave blank until re-extraction.

Nothing here infers a party from what a sentence sounds like. A party is
either a canonical field the formulator populated, or a span captured by an
explicit delegation construction and quoted verbatim from the source sentence.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel

from policy_platform.contracts.formulation import CanonicalPolicy, CanonicalPolicyRule


class PartyRole(str, Enum):
    """What the party does in the rule, in XACML 3.0 terms where they exist.

    XACML §B.2 defines a closed set of subject categories, two of which map
    cleanly onto the canonical party fields. The third role has no XACML
    subject category because XACML does not model an approver as a subject at
    all — it models required approval as an Obligation on a Permit — so
    `AUTHORITY` is named for what it is rather than forced into a category
    that means something else.
    """

    #: `urn:oasis:names:tc:xacml:1.0:subject-category:access-subject` — the
    #: party whose conduct the rule governs.
    ACCESS_SUBJECT = "access_subject"
    #: `urn:oasis:names:tc:xacml:1.0:subject-category:recipient-subject` —
    #: XACML's "subject that receives the result". A beneficiary of an
    #: allowance is receiving the result of the decision, not requesting it,
    #: and calling them the access-subject would say the rule governs their
    #: conduct when it governs what they are owed.
    RECIPIENT_SUBJECT = "recipient_subject"
    #: The party the document delegates the decision to. XACML expresses this
    #: as an Obligation the PEP must discharge before a Permit takes effect;
    #: DMN 1.5 as an `authorityRequirement` pointing at a `knowledgeSource`.
    #: Both treat a delegated decision as a decision, which is why a rule with
    #: an authority and no threshold is `DISCRETIONARY`, not incomplete.
    AUTHORITY = "authority"


class PartyProvenance(str, Enum):
    """Where the party was read from. Ordered strongest first.

    Kept explicit because the two are not equally trustworthy and a reviewer
    asking "who approves this?" needs to know which they are looking at.
    """

    #: The formulator populated a party-typed canonical field from this
    #: sentence. Strongest: it is the decomposition of the rule's own text.
    CANONICAL_FIELD = "canonical_field"
    #: An explicit delegation construction in the verbatim source sentence,
    #: with the party captured from the phrase.
    DELEGATION_PHRASE = "delegation_phrase"


class PolicyParty(BaseModel):
    """One party, quoted from the source.

    `name` is verbatim. "the Board of Trustees" is what the document says;
    resolving it to a directory principal, an approval queue, or an org-chart
    node is a mapping into a customer's schema that this platform has no basis
    to invent — the same reason `required_facts` never invents a fact path.

    `source_field` names the canonical field or the matched construction, so a
    reviewer can check the claim instead of taking it on trust.
    """

    name: str
    role: PartyRole
    provenance: PartyProvenance
    source_field: str


#: Canonical fields that are party-typed by definition, and the role each
#: carries. `subject` is deliberately absent: it is a grammatical subject, not
#: a party. "Annual increase", "Employee basic salary" and "The housing
#: allowance" are all canonical subjects and none of them is anybody. The same
#: reasoning already governs `subjectAttribute` in the web vocabulary, which
#: refuses to assert `subject.role` for exactly this reason.
_PARTY_FIELDS: tuple[tuple[str, PartyRole], ...] = (
    ("actor", PartyRole.ACCESS_SUBJECT),
    ("assigner", PartyRole.AUTHORITY),
    ("beneficiary", PartyRole.RECIPIENT_SUBJECT),
    ("recipient", PartyRole.RECIPIENT_SUBJECT),
    ("candidate", PartyRole.RECIPIENT_SUBJECT),
)

#: Explicit delegation constructions. Narrow and closed by design: this is the
#: only place the module reads wording rather than field presence, so it earns
#: that by naming the exact constructions and quoting the captured party for
#: verification. A looser pattern would begin classifying rules by what they
#: sound like, which is the failure mode this codebase exists to avoid.
#:
#: Matched against the verbatim `source_text` rather than any single canonical
#: field, because the construction spans the decomposition: in "requires the
#: approval of the President" the verb sits in `predicate` and the party in
#: `object`, so no one field contains the phrase.
#:
#: Every alternative carries an explicit delegation head. A bare passive
#: ("approved by X") was tried and removed: it matched "clinics and hospitals
#: that are not approved by the insurance company", a relative clause saying
#: which hospitals qualify, and reported the insurer as the authority deciding
#: that rule. The insurer approves hospitals; the rule's actual obligation is
#: to submit invoices to HR, under nobody's approval. A delegation head cannot
#: appear that way, which is why the loose form is gone rather than patched.
_DELEGATION_RE = re.compile(
    r"""(?P<marker>
          subject\s+to\s+the\s+(?:[\w\s]{0,40}?\s+)??(?:approval|judgment|judgement|discretion|consent)\s+of
        | at\s+the\s+(?:sole\s+)?discretion\s+of
        | (?:requires?|require)\s+the\s+(?:prior\s+)?(?:approval|authori[sz]ation|consent|endorsement)\s+of
        | with\s+the\s+(?:prior\s+)?(?:approval|authori[sz]ation|consent)\s+of
        | upon\s+the\s+recommendation\s+of
        | as\s+(?:determined|approved|authori[sz]ed|decided)\s+by
    )
    \s+(?P<party>.{2,80}?)
    (?=\s*(?:[,;.]|\band\s+(?:the\s+)?(?:employee|staff|manager)\b|$))""",
    re.IGNORECASE | re.VERBOSE,
)

#: A negated delegation is not a delegation. "not subject to the approval of
#: the Board" says the Board does *not* decide, and reporting the Board as the
#: authority would invert the sentence — the same defect that once turned
#: "shall not exceed 10%" into an obligation to exceed it.
#:
#: Scoped to the words immediately before the marker so a negation elsewhere in
#: a long sentence cannot suppress a real delegation.
_NEGATED_DELEGATION_RE = re.compile(
    r"\b(?:not|never|without|nor)\b(?:\s+\w+){0,3}\s*$", re.IGNORECASE
)

#: Delegation written the other way round, with the party *before* the verb:
#: "cases that the university deems necessary", "an amount the committee
#: considers appropriate". Found on the live data — "Exceptional Increase may
#: be granted for specific cases that the university deems necessary" names an
#: authority that the marker-first pattern above structurally cannot reach,
#: because it scans for a head phrase followed by a party.
#:
#: Anchored on a judgement verb plus a judgement complement, so an ordinary
#: transitive reading ("the university deems the policy effective from May")
#: does not match.
_SUBJECT_FIRST_DELEGATION_RE = re.compile(
    r"""(?:that|which|as)\s+
        (?P<party>(?:the\s+)?[A-Za-z][\w'’\-]*(?:\s+[\w'’\-]+){0,4}?)
        \s+(?P<marker>deems?|deemed|considers?|judges?|sees\s+fit)
        \s*(?:it\s+)?(?:necessary|appropriate|fit|suitable|proper)""",
    re.IGNORECASE | re.VERBOSE,
)

#: Trailing words that are never part of a party name. "the approval of the
#: President for exceptional cases" must yield "the President", not the whole
#: trailing clause — a captured span that runs on stops being quotable as an
#: entity and starts being a paraphrase of the sentence.
_PARTY_TAIL_RE = re.compile(
    r"\s+(?:for|in|on|under|when|where|during|after|before|according|pursuant|as)\b.*$",
    re.IGNORECASE,
)


def _clean_party(raw: str) -> str:
    """Trim a captured span down to the entity itself."""

    name = _PARTY_TAIL_RE.sub("", raw).strip()
    return name.strip(" \t\r\n,;.:-—–")


def _delegated_parties(source_text: str) -> list[PolicyParty]:
    """Parties named by an explicit delegation construction in the sentence."""

    text = source_text or ""
    found: list[tuple[int, PolicyParty]] = []
    for match in _DELEGATION_RE.finditer(text):
        if _NEGATED_DELEGATION_RE.search(text[: match.start()]):
            continue
        name = _clean_party(match.group("party"))
        # A construction that captured nothing usable is reported as no party
        # rather than as an empty one. An authority whose name is "" would
        # make a rule look delegated to nobody, which reads as a decision
        # having been made when none was.
        if len(name) < 2:
            continue
        found.append(
            (
                match.start(),
                PolicyParty(
                    name=name,
                    role=PartyRole.AUTHORITY,
                    provenance=PartyProvenance.DELEGATION_PHRASE,
                    source_field=" ".join(match.group("marker").split()).lower(),
                ),
            )
        )
    for match in _SUBJECT_FIRST_DELEGATION_RE.finditer(text):
        if _NEGATED_DELEGATION_RE.search(text[: match.start()]):
            continue
        name = _clean_party(match.group("party"))
        if len(name) < 2:
            continue
        found.append(
            (
                match.start(),
                PolicyParty(
                    name=name,
                    role=PartyRole.AUTHORITY,
                    provenance=PartyProvenance.DELEGATION_PHRASE,
                    source_field=" ".join(match.group("marker").split()).lower(),
                ),
            )
        )
    # Sentence order, so the shipped JSON is identical run to run regardless of
    # which pattern matched first.
    return [party for _, party in sorted(found, key=lambda item: item[0])]


def extract_parties(
    rule: CanonicalPolicyRule | None, source_text: str = ""
) -> list[PolicyParty]:
    """Every party this rule names, strongest provenance first.

    Order is deterministic — canonical fields in declaration order, then
    delegation matches in sentence order — because the result ships inside the
    rule JSON, and a set would make identical input produce a different
    document run to run.
    """

    parties: list[PolicyParty] = []
    seen: set[tuple[str, PartyRole]] = set()

    def add(party: PolicyParty) -> None:
        key = (party.name.casefold(), party.role)
        if key in seen:
            return
        seen.add(key)
        parties.append(party)

    if rule is not None:
        for field, role in _PARTY_FIELDS:
            name = (getattr(rule, field, None) or "").strip()
            if name:
                add(
                    PolicyParty(
                        name=name,
                        role=role,
                        provenance=PartyProvenance.CANONICAL_FIELD,
                        source_field=field,
                    )
                )

    for party in _delegated_parties(source_text):
        add(party)
    return parties


def parties_for_policy(policy: CanonicalPolicy | None) -> list[PolicyParty]:
    """`extract_parties` for a whole canonical policy, using its source text."""

    if policy is None:
        return []
    return extract_parties(policy.rule, policy.source_text or "")


def authorities(parties: list[PolicyParty]) -> list[PolicyParty]:
    """Just the parties the decision was delegated to."""

    return [party for party in parties if party.role is PartyRole.AUTHORITY]


def is_judgement_bounded(parties: list[PolicyParty]) -> bool:
    """True when a named party has to exercise judgement for this rule.

    Keyed on an authority *party*, not on the evaluability verdict, because
    the two answer different questions and a rule can be both. "Increase due
    to inflation with a percentage not exceeding 5% ... and subject to the
    judgment and approval of the Board of Trustees" states a testable limit
    **and** requires a human to approve; grouping only the rules with nothing
    else stated would have left it out of the very group it belongs in.

    This is the XACML reading: a Permit carrying an Obligation is still a
    Permit, and the Obligation is what a PEP must discharge before acting.
    """

    return bool(authorities(parties))
