"""The facts a policy names, taken from the policy's own words.

A rule that bounds one quantity by another is *about* those quantities, and the
sentence names them. "The proposed increase shall not exceed 5% of the
reference amount" turns on two measurable things, and the document supplies
both. Extracting them is not inventing a schema: every entry here is a phrase
the source wrote, carried verbatim beside the identifier derived from it.

That distinction is the whole point. A fact *path* asserts that some system has
a field at that address, and nothing in a policy document establishes it. A
fact *name* derived from the document asserts only that the policy talks about
this thing — which is exactly what a consumer needs in order to say "here is
where that lives in my data".

Not every policy has one. A definition names no quantity, and an obligation to
notify may name none either. An empty list is the correct answer for those, and
says so plainly.
"""
from __future__ import annotations

import re

from policy_platform.contracts.formulation import CanonicalPolicyRule
from policy_platform.contracts.policy import PolicyFact

#: Canonical fields that *name a thing* a case could be measured against,
#: paired with the role each plays. Order is the order facts are emitted, so
#: the same rule always produces the same list.
#:
#: Conditions, prerequisites, constraints and triggers are deliberately absent.
#: They state a *test over* facts rather than naming one, and their phrases are
#: clauses: including them produced entries like
#: `based-on-their-functions-and-depending-on-the-recommendation-of-the-...`,
#: an eighty-character truncation of a sentence sitting where an identifier
#: belongs — the same defect that once put whole clauses in the action slot.
#: The tests a policy states are already carried, decomposed, on the
#: projection's `conditions`.
#:
#: Party fields are included: a named authority is a thing a case either has
#: an approval from or does not, and a consumer routing a policy needs it.
_FACT_BEARING_FIELDS: tuple[tuple[str, str], ...] = (
    ("subject", "subject"),
    ("object", "object"),
    ("threshold", "threshold"),
    ("calculation", "calculation"),
    ("temporal_constraint", "temporal_constraint"),
    ("deadline", "deadline"),
    ("frequency", "frequency"),
    ("location", "location"),
    ("assigner", "authority"),
    ("actor", "actor"),
    ("beneficiary", "beneficiary"),
    ("recipient", "recipient"),
    ("candidate", "candidate"),
)

#: Roles whose value *is* a period of time. A duration word elsewhere is
#: incidental: a phrase naming an entitlement "per calendar year (12 months)"
#: is an entitlement, and reading the parenthetical as its type made an
#: allowance a duration.
_TIME_BEARING_ROLES = frozenset({"deadline", "frequency", "temporal_constraint"})

#: Currency written as a symbol or an ISO-shaped code. Structural rather than a
#: list of currencies, so a document denominated in anything is read the same.
_CURRENCY_SYMBOLS = "$€£¥₹₽₩₪₦₨₫₴₸₺﷼"
_MONEY_RE = re.compile(rf"(?:\b[A-Z]{{3}}\b|[{_CURRENCY_SYMBOLS}])")
_NUMBER_RE = re.compile(r"\d")
_DURATION_RE = re.compile(
    r"\b(?:day|days|week|weeks|month|months|year|years|hour|hours)\b", re.IGNORECASE
)
#: Phrasing that states a yes/no condition rather than a measured quantity.
#: Deliberately narrow: these are the constructions that *are* the state, not
#: words that merely appear near one.
_BOOLEAN_RE = re.compile(
    r"\b(?:approval|approved|consent|authori[sz]ation|endorsement|"
    r"eligible|eligibility|entitled|enrolled|registered|expired|completed)\b",
    re.IGNORECASE,
)


#: Roles whose value *is* a quantity, so a number anywhere in the phrase is the
#: value rather than part of a name.
_VALUE_BEARING_ROLES = frozenset(
    {"threshold", "calculation", "deadline", "frequency", "temporal_constraint"}
)

#: A phrase that opens with its value: "10% of …", "5,000 per claim", "$200".
#: A value expression leads with the value; a name does not. That is what
#: separates the object "10% of the reference amount", which is a quantity,
#: from a subject named "… per calendar year (12 months)", which is a thing
#: whose name happens to contain a parenthetical.
_LEADS_WITH_VALUE_RE = re.compile(
    rf"^\s*(?:the\s+|a\s+|an\s+)?(?:[{_CURRENCY_SYMBOLS}]|[A-Z]{{3}}\s+)?\d"
)


def infer_data_type(phrase: str, role: str = "") -> str | None:
    """The type the phrase itself shows, or None.

    Read from what the sentence writes, never assumed from the field it sits
    in. A `threshold` is usually numeric but not always — "limited to one
    person" is a count and "limited to written requests" is not a quantity at
    all — so the phrase decides.

    `role` narrows one case only. A duration word is read as the *type* solely
    where the value is a period: "per calendar year (12 months)" is a frequency
    and is one, while an entitlement named "… per calendar year (12 months)" is
    an entitlement whose name happens to contain a parenthetical. Reading the
    second as a duration made an allowance into a length of time.

    Returning None is a real answer: the document names the thing without
    saying what kind of value it holds, and a consumer mapping it to their data
    is better served by that silence than by a guess.
    """

    text = (phrase or "").strip()
    if not text:
        return None

    # A quantitative type is only read where the phrase is a *value* rather
    # than a name that happens to contain a number. Without this, an
    # entitlement named "… per calendar year (12 months)" came back first as a
    # duration and then as a number: a parenthetical inside a name was being
    # read as the thing's type.
    quantitative = role in _VALUE_BEARING_ROLES or bool(_LEADS_WITH_VALUE_RE.match(text))
    if quantitative and _NUMBER_RE.search(text):
        if _MONEY_RE.search(text):
            return "money"
        if _DURATION_RE.search(text):
            return "duration"
        return "number"
    if _BOOLEAN_RE.search(text):
        return "boolean"
    return None


def _slugify(phrase: str) -> str:
    """A stable identifier derived from the phrase's own words."""

    from policy_platform.infrastructure.xacml_projection import _slug

    return _slug(phrase)


def facts_for(rule: CanonicalPolicyRule | None) -> list[PolicyFact]:
    """Every fact the rule's own sentence names, in a stable order.

    Deduplicated on the identifier rather than the phrase, because one phrase
    routinely fills two canonical fields — an amount is frequently both the
    `object` and the `threshold` — and a consumer needs one entry per thing,
    not one per slot it occupied. The first field in declaration order keeps
    the winner deterministic.
    """

    if rule is None:
        return []

    facts: list[PolicyFact] = []
    seen: set[str] = set()
    for field, role in _FACT_BEARING_FIELDS:
        phrase = (getattr(rule, field, None) or "").strip()
        if not phrase:
            continue
        name = _slugify(phrase)
        if not name or name in seen:
            continue
        seen.add(name)
        facts.append(
            PolicyFact(
                name=name,
                source_phrase=phrase,
                role=role,
                data_type=infer_data_type(phrase, role),
            )
        )
    return facts
