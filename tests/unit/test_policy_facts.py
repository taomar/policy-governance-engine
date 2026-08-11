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


# --------------------------------------------------------------------------
# What becomes a fact
# --------------------------------------------------------------------------


def test_the_things_a_rule_measures_become_facts():
    facts = facts_for(
        _rule(subject="the proposed amount", predicate="exceed", threshold="5% of the base")
    )

    assert [(f.name, f.role) for f in facts] == [
        ("proposed-amount", "subject"),
        ("5-of-the-base", "threshold"),
    ]


def test_a_named_authority_becomes_a_fact():
    """A case either has the approval or has not, so a consumer must see it."""

    facts = facts_for(_rule(subject="the request", assigner="the review board"))

    assert ("review-board", "authority") in [(f.name, f.role) for f in facts]


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

    assert [f.role for f in facts] == ["subject"]


def test_one_phrase_in_two_slots_yields_one_fact():
    """An amount is routinely both the object and the threshold.

    A consumer needs one entry per thing, not one per slot it occupied.
    """

    facts = facts_for(_rule(object="5% of the base", threshold="5% of the base"))

    assert [f.name for f in facts] == ["5-of-the-base"]


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
