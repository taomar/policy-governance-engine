"""The route seam keeps "not asked" distinct from "asked and found nothing".

A quality check is scoped to the route(s) its assertion is about. When a check
does not speak to a record's route it is *not applicable* to that record -- a
state the report has to be able to tell apart from a check that ran and passed.
These tests pin that distinction so a later edit cannot quietly let a skipped
check read as a clean one, which is the failure the seam exists to prevent.

No observed population count appears here on purpose: the seam is asserted by
the routes a code speaks to, never by how many records happen to sit on each
route. Tying a test to the live split would bake a corpus into the logic.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.policy import EvaluationMode
from policy_platform.infrastructure.quality.route_applicability import (
    Applicability,
    applies_to,
    classify,
    not_applicable_here,
    routes_for,
)

# The two checks the suite already scopes by route, each named by the route it
# speaks to. Referring to them by constant keeps the tests about the seam.
_ENGINE_ONLY = "not_runnable_as_stored"
_JUDGE_ONLY = "not_decidable_as_written"


def test_a_check_skipped_for_route_reasons_is_not_applicable_not_passed():
    """The engine-runnability check on a judged record is a non-result.

    This is the load-bearing distinction: the skip must classify as
    NOT_APPLICABLE and must not be interchangeable with APPLIES, or a check
    that never ran would report as a check that ran and found nothing.
    """

    state = classify(_ENGINE_ONLY, EvaluationMode.AI_READY)

    assert state is Applicability.NOT_APPLICABLE
    assert state is not Applicability.APPLIES


def test_the_skip_is_named_so_a_caller_reads_it_off_rather_than_infers_it():
    """A withheld check is stated, not left as an absence to be noticed."""

    withheld = not_applicable_here(EvaluationMode.AI_READY)

    assert _ENGINE_ONLY in withheld
    # The judged record's own question is never withheld from it.
    assert _JUDGE_ONLY not in withheld


def test_the_judge_check_does_not_speak_to_an_engine_record():
    state = classify(_JUDGE_ONLY, EvaluationMode.DETERMINISTIC)

    assert state is Applicability.NOT_APPLICABLE
    assert _JUDGE_ONLY in not_applicable_here(EvaluationMode.DETERMINISTIC)
    assert _ENGINE_ONLY not in not_applicable_here(EvaluationMode.DETERMINISTIC)


def test_each_route_specific_check_applies_to_its_own_route():
    assert applies_to(_ENGINE_ONLY, EvaluationMode.DETERMINISTIC)
    assert classify(_ENGINE_ONLY, EvaluationMode.DETERMINISTIC) is Applicability.APPLIES
    assert applies_to(_JUDGE_ONLY, EvaluationMode.AI_READY)
    assert classify(_JUDGE_ONLY, EvaluationMode.AI_READY) is Applicability.APPLIES


@pytest.mark.parametrize("route", list(EvaluationMode))
def test_a_route_neutral_check_speaks_to_every_route(route):
    """A code with no entry reaches both routes and is never listed as withheld.

    `decomposition_malformed` is the case that matters here: a damaged
    decomposition is wrong however a record is decided, so scoping it to one
    route would drop a real defect on the other -- the majority, judged route.
    """

    code = "decomposition_malformed"

    assert routes_for(code) is None
    assert applies_to(code, route)
    assert classify(code, route) is Applicability.APPLIES
    assert code not in not_applicable_here(route)


def test_applies_everywhere_never_collapses_into_applies_nowhere():
    """``None`` (every route) must stay apart from an empty set (no route)."""

    assert routes_for("decomposition_malformed") is None
    assert routes_for(_ENGINE_ONLY) == frozenset({EvaluationMode.DETERMINISTIC})
    assert routes_for(_JUDGE_ONLY) == frozenset({EvaluationMode.AI_READY})


def test_every_route_specific_code_is_withheld_from_some_route():
    """A code scoped to a route has to be reported not-applicable elsewhere.

    Otherwise the registry could name a route-specific check that no route ever
    reads as withheld -- a scope that exists in the map but nowhere in a report.
    """

    for route in EvaluationMode:
        for code in not_applicable_here(route):
            assert classify(code, route) is Applicability.NOT_APPLICABLE
            assert not applies_to(code, route)
