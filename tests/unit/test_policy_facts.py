"""Facts a policy names, taken from the policy's own words.

A rule that bounds one quantity by another is about those quantities, and the
sentence names them. Extracting them gives a consumer somewhere to point when
they say "that lives here in my data" — without this system ever claiming to
know their schema.

Two properties matter more than coverage, and both were learned by looking at
real output rather than by reasoning about it:

* A fact names a *thing*. Including the fields that state a *test* produced
  entries like an eighty-character truncation of a whole clause sitting where
  an identifier belongs.
* A number inside a name is not the thing's type. A parenthetical period in an
  entitlement's name made it a duration, and then a number.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.policy_facts import facts_for, infer_data_type


def _rule(**fields) -> CanonicalPolicyRule:
    return CanonicalPolicyRule(rule_type=CanonicalRuleType.OBLIGATION, **fields)


#: A phrase where a proportion appears as a part rather than as the whole.
SOME_COMPOUND = "the amount reduced by 5% of the base"


# --------------------------------------------------------------------------
# What becomes a fact
# --------------------------------------------------------------------------


def test_the_things_a_rule_measures_become_facts():
    facts = facts_for(
        _rule(subject="the proposed amount", predicate="exceed", threshold="5% of the base")
    )

    assert [(f.name, f.roles) for f in facts] == [
        ("proposed-amount", ["subject"]),
        ("base", ["threshold"]),
    ]


def test_a_proportional_bound_names_the_thing_it_is_taken_of():
    """The percentage belongs to the rule; the base is what a case supplies.

    Naming the fact after the whole expression produced "5-of-the-base", which
    nobody holds a value for: a consumer holds the base, and the rule applies
    its own 5% to it. The multiplier is carried in the compiled comparison,
    where it can be evaluated, rather than baked into an identifier.
    """

    facts = facts_for(_rule(subject="the amount", threshold="5% of the reference figure"))

    threshold_fact = next(f for f in facts if "threshold" in f.roles)
    assert threshold_fact.name == "reference-figure"
    assert threshold_fact.source_phrase == "the reference figure"


def test_a_proportion_base_is_typed_as_a_quantity():
    """Stated by the sentence, not assumed: you can only take 5% of a number.

    The base phrase itself carries no digits, so reading the words alone gives
    no type. The comparison does.
    """

    facts = facts_for(_rule(subject="the amount", threshold="5% of the reference figure"))

    assert next(f for f in facts if "threshold" in f.roles).data_type == "number"


def test_a_proportion_inside_a_larger_phrase_is_not_read_as_one():
    """Only a phrase that *is* a proportion is reduced to its base.

    "the amount reduced by 5% of the base" mentions a proportion without being
    one. Reducing it would publish a fact named after the base and silently
    assert the rule bounds that base — a claim the sentence never made.

    The phrase itself is not published either: it is a computed expression, and
    no consumer holds a value for "the amount reduced by 5% of the base".
    """

    names = {f.name for f in facts_for(_rule(subject="the claim", threshold=SOME_COMPOUND))}

    assert "base" not in names
    assert names == {"claim"}


# --------------------------------------------------------------------------
# The policy's own numbers are not facts
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"threshold": "5,000"},
        {"calculation": "at the rate of (200) two hundred XYZ per month"},
        {"frequency": "per calendar year (12 months)"},
        {"object": "(200) two hundred XYZ per month"},
        {"object": "Fifteen thousand (15,000) XYZ"},
    ],
)
def test_a_stated_amount_is_not_something_a_case_supplies(fields):
    """A fact is what a case brings; a constant is what the document tells you.

    Publishing the second as the first sends a consumer looking for a value the
    policy already handed it, and asks a judge to supply the answer as input.
    """

    facts = facts_for(_rule(subject="the entitlement", **fields))

    assert [f.roles for f in facts] == [["subject"]]


def test_an_amount_is_still_a_constant_when_its_currency_is_unrecognised():
    """The branch the corpus actually depends on.

    Currency is read structurally — a symbol, or an ISO-shaped three-letter
    code — so a document writing a two-letter abbreviation gets no match. What
    still identifies the phrase is that it opens with its figure. Without that
    reading, the one amount in the corpus written with a short code was
    published as a thing a case must supply.
    """

    facts = facts_for(_rule(subject="the entitlement", object="(200) two hundred XY per month"))

    assert [f.roles for f in facts] == [["subject"]]


def test_the_same_amount_is_read_the_same_way_in_every_slot():
    """The incoherence this closes: one phrase, two answers, one document.

    An amount written words-first leads with a word, so a leads-with-value test
    alone excluded it from a threshold and published it as a fact from an
    object — for the identical phrase in the identical document.
    """

    as_threshold = facts_for(_rule(subject="the claim", threshold="Fifteen thousand (15,000) XYZ"))
    as_object = facts_for(_rule(subject="the claim", object="Fifteen thousand (15,000) XYZ"))

    assert [f.name for f in as_threshold] == [f.name for f in as_object] == ["claim"]


@pytest.mark.parametrize(
    "phrase",
    [
        "The housing allowance per calendar year (12 months)",
        "Employees and their family members (spouse and 2 children 18 years or younger)",
    ],
)
def test_a_name_that_merely_contains_a_number_stays_a_fact(phrase):
    """The other direction, and the more damaging one to get wrong.

    These name a thing a case must be measured against. Dropping them because
    a parenthetical carries digits would remove the input the policy needs.
    """

    assert [f.name for f in facts_for(_rule(subject=phrase))] != []


def test_a_proportion_base_survives_the_constant_check():
    """Order matters: the base is taken out before the phrase is judged.

    "10% of the base" carries a numeral, but the part that names a fact does
    not. Judging the original phrase would drop the one input the rule needs.
    """

    facts = facts_for(_rule(subject="the amount", threshold="10% of the reference figure"))

    assert [f.name for f in facts] == ["amount", "reference-figure"]


def test_a_named_authority_becomes_a_fact():
    """A case either has the approval or has not, so a consumer must see it."""

    facts = facts_for(_rule(subject="the request", assigner="the review board"))

    assert ("review-board", ["authority"]) in [(f.name, f.roles) for f in facts]


@pytest.mark.parametrize("field", ["condition", "prerequisite", "constraint", "trigger"])
def test_a_clause_never_becomes_a_fact(field):
    """These state a test over facts; they do not name one.

    Including them produced an identifier that was a truncated sentence — the
    same defect as putting a whole clause in an action slot. The tests a policy
    states are carried, decomposed, elsewhere.
    """

    facts = facts_for(
        _rule(subject="the request", **{field: "depending on the recommendation of the reviewer"})
    )

    assert [f.roles for f in facts] == [["subject"]]


def test_one_phrase_in_two_slots_yields_one_fact():
    """An amount is routinely both the object and the threshold.

    A consumer needs one entry per thing, not one per slot it occupied.
    """

    facts = facts_for(_rule(object="5% of the base", threshold="5% of the base"))

    assert [f.name for f in facts] == ["base"]


def test_a_phrase_playing_two_parts_keeps_both():
    """The bug this replaced: a body that decides was listed only as a subject.

    "<body> decides on <thing>" names the body as the grammatical subject *and*
    as the deciding authority. Keeping the first role and discarding the rest
    meant the one question a consumer most needs answered about a delegated
    decision had no answer — on the very rule that answers it.
    """

    (fact, *_rest) = facts_for(
        _rule(subject="the review board", predicate="decides on", assigner="the review board")
    )

    assert fact.name == "review-board"
    assert fact.roles == ["subject", "authority"]


def test_the_type_is_read_under_the_role_that_explains_the_phrase():
    """A phrase filling a value-bearing role is typed as that value.

    "5% of the base" is both the object and the threshold. Typed as an object
    it leads with a number and reads as one; the point is that filling a
    value-bearing role reaches the same answer rather than a different one.
    """

    (fact,) = facts_for(_rule(object="5% of the base", threshold="5% of the base"))

    assert fact.roles == ["object", "threshold"]
    assert fact.data_type == "number"


def test_a_rule_naming_nothing_measurable_yields_nothing():
    """An empty list is a real answer, not a gap."""

    assert facts_for(_rule(predicate="applies")) == []
    assert facts_for(None) == []


def test_the_source_wording_is_carried_verbatim():
    """The identifier is derived, so the derivation must stay checkable."""

    (fact,) = facts_for(_rule(subject="  The Employee's Basic Salary  "))

    assert fact.source_phrase == "The Employee's Basic Salary"
    assert fact.name == "employee-s-basic-salary"


def test_facts_are_emitted_in_a_stable_order():
    """The same rule must always produce the same list."""

    rule = _rule(subject="a", object="b", threshold="c", assigner="d")

    assert [f.name for f in facts_for(rule)] == [f.name for f in facts_for(rule)]


# --------------------------------------------------------------------------
# What type the phrase shows
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "role", "expected"),
    [
        # A value expression leads with its value.
        ("10% of the reference amount", "object", "number"),
        ("USD 5,000", "object", "money"),
        ("$200 per month", "object", "money"),
        ("5,000 USD per claim", "threshold", "money"),
        # A value-bearing role is a value wherever the number sits.
        ("within 30 days", "deadline", "duration"),
        ("per calendar year (12 months)", "frequency", "duration"),
        # A yes/no state.
        ("the approval of the named body", "authority", "boolean"),
        ("eligible staff", "beneficiary", "boolean"),
    ],
)
def test_a_type_the_phrase_shows_is_read(phrase, role, expected):
    assert infer_data_type(phrase, role) == expected


@pytest.mark.parametrize(
    ("phrase", "role"),
    [
        # A name containing a number is not a number. Both of these were
        # mistyped before the shape test existed.
        ("The housing allowance per calendar year (12 months)", "subject"),
        ("a unit with 3 floors", "subject"),
        # A thing whose value type the sentence never states.
        ("Employee basic salary", "subject"),
        ("twice the monthly basic salary", "calculation"),
        ("", "subject"),
    ],
)
def test_an_unstated_type_stays_unstated(phrase, role):
    """Silence is more useful to a consumer than a guess.

    The document named the thing without saying what kind of value it holds.
    Filling that in would be the invention this pipeline exists to avoid.
    """

    assert infer_data_type(phrase, role) is None


def test_currency_is_recognised_structurally():
    """Any currency, in any notation — never a list of the ones seen so far."""

    for phrase in ["5,000 XYZ", "€4.500", "₹50,000", "¥900"]:
        assert infer_data_type(phrase, "threshold") == "money", phrase
