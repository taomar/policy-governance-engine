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

#: A phrase that opens with its value: "10% of …", "5,000 per claim", "$200",
#: "(200) two hundred …". A value expression leads with the value; a name does
#: not. That is what separates the object "10% of the reference amount", which
#: is a quantity, from a subject named "… per calendar year (12 months)", which
#: is a thing whose name happens to contain a parenthetical.
#:
#: The optional opening bracket is there because documents write an amount as a
#: numeral followed by its words — "(200) two hundred SR" — and reading that as
#: a name published the policy's own figure as something a case must supply.
_LEADS_WITH_VALUE_RE = re.compile(
    rf"^\s*[(\[]?\s*(?:the\s+|a\s+|an\s+)?(?:[{_CURRENCY_SYMBOLS}]|[A-Z]{{3}}\s+)?\d"
)


#: A bound stated as a proportion of something else: "10% of the base salary".
#: Anchored at both ends so it reads a phrase that *is* a proportion, not one
#: that merely mentions one. "10% of X" qualifies; "the amount, reduced by 10%
#: of X, is paid monthly" does not — there the proportion is a part, and naming
#: the whole phrase after X would misstate what the sentence said.
_PROPORTION_RE = re.compile(
    r"^\s*(?P<percent>\d+(?:\.\d+)?)\s*%\s*of\s+(?P<base>.+?)\s*$",
    re.IGNORECASE,
)


def parse_proportion(phrase: str) -> tuple[float, str] | None:
    """Read "N% of <something>" as a factor and the thing it is taken of.

    Returns None for anything else, including a bare amount: a fixed limit and
    a proportional one are different claims and must not be conflated.
    """

    match = _PROPORTION_RE.match(phrase or "")
    if not match:
        return None
    base = match.group("base").strip()
    if not base:
        return None
    return float(match.group("percent")) / 100.0, base


def fact_phrase(phrase: str) -> str:
    """The part of a phrase that names something a case must supply.

    A proportional bound states a constant and a base: "10% of the current
    basic salary". The 10% belongs to the rule — it is the same for every case
    — while the basic salary is the thing that varies and must be established.
    Naming the fact after the whole expression produced entries like
    "10-of-the-current-basic-salary", which nobody holds a value for: a
    consumer holds the salary, and the rule applies its own 10% to it.

    Everything else is returned unchanged. This narrows one construction that
    was demonstrably wrong, and does not attempt to parse arithmetic generally.
    """

    proportion = parse_proportion(phrase)
    if proportion is None:
        return (phrase or "").strip()
    return proportion[1]


def is_stated_constant(phrase: str, role: str) -> bool:
    """Whether the phrase is the policy's own number rather than a case input.

    A fact is something a case brings; a stated constant is something the
    document already tells you. Listing the second as the first is backwards —
    a consumer reading `fact_model` goes looking for a value the policy handed
    it, and a judge is asked to supply the answer as an input.

    One rule made the cost concrete. "A work nature allowance at the rate of
    (200) two hundred SR per month is paid…" published *three* facts for that
    single amount — the object, the calculation, and the frequency — one of
    them typed as a length of time because the phrase ends in a period word.
    None of the three is something a case establishes.

    Read as three signals, because no single one covers the slots documents
    actually use. A value-bearing slot still carrying a numeral once any
    proportion base has been taken out; a phrase that leads with its value; or
    a phrase whose own words show it is an amount.

    The third exists because the same phrase was being read both ways. An
    amount written words-first — "Fifteen thousand (15,000) SAR" — leads with a
    word, so it was excluded where it filled a threshold and published as a
    fact where it filled an object. One phrase, two answers, from one document.

    Reading currency structurally rather than from a list of currency names
    keeps this working for a document denominated in anything. Measured across
    the corpus it excluded exactly the amounts and no name; a name that
    happened to pair an abbreviation with a year would be a false positive, and
    none occurred.

    The ordering against the proportion matters. "10% of the base" reduces to
    "the base", which carries no numeral and is a genuine input; "5,000" does
    not reduce and stays a constant.
    """

    text = phrase or ""
    if not _NUMBER_RE.search(text):
        return False
    if role in _VALUE_BEARING_ROLES:
        return True
    if _LEADS_WITH_VALUE_RE.match(text):
        return True
    return bool(_MONEY_RE.search(text))


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


def published_facts(rule, required=None) -> list[PolicyFact]:
    """The fact model a record publishes: named by the sentence, typed by it.

    One function because three places need it — extraction and two read paths —
    and while there were three copies they drifted. Extraction reconciled a
    fact's type against the rule's own `required_facts` and the read paths did
    not, so one record told a consumer a value's type was unknown in
    `fact_model` while `required_facts` beside it said `number`.

    Reconciliation only ever fills a gap. `facts_for` reads a type where the
    phrase writes one, which is right: "Annual increase" contains no digits and
    asserting a type from the words alone would be a guess. But once the rule
    compiles a numeric comparison over that fact, the sentence *has* said it is
    a quantity. A type the phrase states is never overwritten, because the
    phrase is the stronger evidence — it says money or duration where a
    compiled comparison can only say "a number".
    """

    facts = facts_for(rule)
    if not required:
        return facts
    declared = {item.name: item.data_type for item in required if item.data_type}
    return [
        fact.model_copy(update={"data_type": declared[fact.name]})
        if fact.data_type is None and fact.name in declared
        else fact
        for fact in facts
    ]


def facts_for(rule: CanonicalPolicyRule | None) -> list[PolicyFact]:
    """Every fact the rule's own sentence names, in a stable order.

    One phrase routinely fills several canonical fields — an amount is often
    both the `object` and the `threshold`, and a body that decides is often
    both the grammatical `subject` and the `assigner`. Those are one thing
    playing several parts, so they produce one entry carrying every part.

    An earlier version kept the first role and discarded the rest, which meant
    a rule reading "<body> decides on <thing>" listed the body as a subject and
    nowhere as an authority: the one question a consumer most needs answered
    about a delegated decision had no answer, on the rule that answers it.

    The type is inferred once, from the role that best explains the phrase — a
    value-bearing role if the phrase fills one, since that is the reading under
    which a number in it is the value rather than part of a name.
    """

    if rule is None:
        return []

    ordered: list[str] = []
    by_name: dict[str, tuple[str, list[str], bool]] = {}
    for field, role in _FACT_BEARING_FIELDS:
        phrase = (getattr(rule, field, None) or "").strip()
        if not phrase:
            continue
        proportional = parse_proportion(phrase) is not None
        named = fact_phrase(phrase)
        if is_stated_constant(named, role):
            continue
        name = _slugify(named)
        if not name:
            continue
        if name not in by_name:
            by_name[name] = (named, [], proportional)
            ordered.append(name)
        roles = by_name[name][1]
        if role not in roles:
            roles.append(role)

    facts: list[PolicyFact] = []
    for name in ordered:
        phrase, roles, proportional = by_name[name]
        typing_role = next((r for r in roles if r in _VALUE_BEARING_ROLES), roles[0])
        data_type = infer_data_type(phrase, typing_role)
        # A proportion's base is a quantity because the sentence takes a
        # percentage of it. That is stated, not assumed, so it survives the
        # base phrase itself carrying no digits: "10% of the basic salary"
        # says the salary is a number without writing one.
        if data_type is None and proportional:
            data_type = "number"
        facts.append(
            PolicyFact(
                name=name,
                source_phrase=phrase,
                roles=roles,
                data_type=data_type,
            )
        )
    return facts
