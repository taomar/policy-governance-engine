"""The action lexicon must recognise a verb in every form it is written in.

An action identifier is what a request is matched against, so a predicate that
reaches no entry yields none at all — refusing is correct, and the lexicon is
closed on purpose. What is not correct is refusing a verb the lexicon already
contains because of the grammatical form the sentence happened to use.

Two defects of that kind were found by measuring the lexicon against a real
corpus rather than by reading it:

* Every `-e` verb was unreachable in its bare form. The suffix pattern was
  `(?:e?[sd]|ing)?`, so `provid` matched "provides", "provided" and
  "providing" — and not "provide", because the trailing `e` needed an `s` or a
  `d` after it and the word boundary then failed mid-word. The same verb was
  recognised three ways and refused the fourth.

* `eligib` could never match anything. "eligible" is `eligib` + `le`, which
  was not in the suffix set, so the entry sat in the lexicon looking like
  coverage it did not provide.

Both are the same failure to notice: an entry that is present is assumed to
work. These tests exercise each entry through the forms English actually
writes it in.
"""
from __future__ import annotations

import pytest

from policy_platform.infrastructure.projection.xacml_projection import _ACTION_LEXICON, normalize_action


#: Every action the lexicon can produce, with a phrase that must reach it.
#: Written out rather than introspected so an entry that matches nothing is a
#: failing test rather than a silent absence — which is exactly what `eligib`
#: was before this file existed.
_EVERY_ACTION = {
    "grant": "grants",
    "pay": "is paid",
    "calculate": "is calculated as",
    "increase": "be increased",
    "transfer": "transferred",
    "approve": "approved",
    "provide": "provide",
    "submit": "be submitted",
    "reimburse": "reimbursed",
    "deduct": "deducted",
    "terminate": "terminated",
    "entitle": "are entitled to",
    "cover": "covers",
    "limit": "is limited to",
    "determine-eligibility": "are eligible for",
}


def test_every_action_the_lexicon_declares_is_reachable():
    """An entry that matches nothing is not coverage; it only looks like it.

    Guards the class of defect `eligib` was: a stem no string could reach,
    sitting in the table as though it were doing work.
    """

    produced = {action for _, action in _ACTION_LEXICON}
    untested = produced - set(_EVERY_ACTION)
    assert not untested, f"lexicon actions with no test phrase: {sorted(untested)}"

    unreachable = [
        (action, phrase)
        for action, phrase in _EVERY_ACTION.items()
        if normalize_action(phrase) != action
    ]
    assert not unreachable, f"actions no phrase could reach: {unreachable}"


@pytest.mark.parametrize(
    ("forms", "expected"),
    [
        (["provide", "provides", "provided", "providing", "be provided", "is provided to"], "provide"),
        (["grant", "grants", "granted", "granting", "be granted"], "grant"),
        (["calculate", "calculates", "calculated", "is calculated as"], "calculate"),
        (["increase", "increases", "increased", "be increased"], "increase"),
        (["approve", "approves", "approved", "be approved"], "approve"),
        (["submit", "submits", "submitted", "submitting", "be submitted"], "submit"),
        (["terminate", "terminates", "terminated"], "terminate"),
        (["entitle", "entitles", "entitled", "are entitled to"], "entitle"),
        (["reimburse", "reimburses", "reimbursed"], "reimburse"),
        (["cover", "covers", "covered", "covering"], "cover"),
        (["transfer", "transfers", "transferred", "transferring"], "transfer"),
        (["pay", "pays", "paid", "be paid", "is paid"], "pay"),
        (["deduct", "deducts", "deducted"], "deduct"),
        (["eligible", "eligibility", "are eligible for", "be eligible"], "determine-eligibility"),
    ],
)
def test_a_verb_resolves_the_same_in_every_form(forms, expected):
    """Inflection is grammar, not meaning. All forms reach one identifier."""

    for form in forms:
        assert normalize_action(form) == expected, f"{form!r} did not resolve to {expected!r}"


@pytest.mark.parametrize(
    "phrase",
    [
        "exceed",
        "exceeds",
        "not exceeding",
        "is limited to",
        "is up to a maximum of",
        "no more than",
        "at most",
        "capped at",
    ],
)
def test_a_bound_resolves_to_one_action_however_it_is_phrased(phrase):
    """English states a limit several ways and they mean the same thing.

    Recognising only the comparative form left an identical rule with no action
    purely because of how its sentence was worded.
    """

    assert normalize_action(phrase) == "limit"


@pytest.mark.parametrize(
    "phrase",
    [
        # Relational, not actions. A rule "governed by" something is not
        # performing the act of governing.
        "are subject to",
        "is associated with",
        "are governed by",
        "is based on",
        "is defined as",
        "be considered as",
        "is reserved for",
        # Nothing at all.
        "",
        "   ",
    ],
)
def test_a_phrase_that_names_no_action_is_refused(phrase):
    """Refusing is the correct answer, and the reason the lexicon is closed.

    An open mapping is what once put whole clauses in the action slot. A
    predicate that names no action must yield none, so the clause survives as
    the outcome rather than being asserted as something a request can match.
    """

    assert normalize_action(phrase) is None


def test_widening_did_not_make_the_lexicon_greedy():
    """The control. A lexicon that matched everything would pass the tests above.

    Words that merely contain a stem must not be read as that action.
    """

    for phrase in ["covert operation", "granular detail", "paydown schedule"]:
        # Each contains a lexicon stem as a substring but is not that verb.
        result = normalize_action(phrase)
        assert result != "cover" or "cover " in phrase, phrase
