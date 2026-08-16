"""The one place a check declares which route it speaks to.

Route-awareness belongs at a boundary, declared once, not re-derived inside
every detector. This module holds that declaration: a finding code maps to the
routes its assertion is about, and a caller asks here rather than re-reading a
rule's shape for itself. A check absent from the map speaks to every route --
a misquoted source, a dropped negation or a damaged decomposition is wrong
however a rule is decided, so the default is deliberately "applies to all".

The distinction the ``Applicability`` values keep is the one the task insists
on: a check that was not asked of a route is not a check that passed. A record
routed to a judge is never run against the engine, so the engine-runnability
check has nothing to say about it -- and its silence there has to read as *not
applicable*, never as a clean result, or the report claims an assurance it
never established.

This generalises what the suite already did in two places by hand: the
runner-fitness pair asks each route its own question, and
``condition_not_compiled`` is withheld because a condition read by a judge is
the ordinary judged outcome rather than a defect. Both are the same rule --
apply a check where it speaks, and account for it, not ignore it, where it does
not -- and this module is where that rule is now stated.
"""

from __future__ import annotations

from enum import Enum

from policy_platform.contracts.policy import EvaluationMode


class Applicability(str, Enum):
    """Whether a check's assertion speaks to a record's route at all.

    Distinct from the check's verdict on purpose. ``APPLIES`` says the check
    was asked and its finding (or its silence) is a real result. A check that
    is ``NOT_APPLICABLE`` was never asked of this route, so it has produced no
    result to report -- neither a defect nor a pass. Collapsing the second into
    the first is exactly how a skipped check comes to be read as a clean one.
    """

    APPLIES = "applies"
    NOT_APPLICABLE = "not_applicable"


#: Finding codes whose question only makes sense for one route.
#:
#: A code that is not here speaks to every route and needs no entry: the map
#: names the exceptions, so a detector added later reaches every route by
#: default and a genuinely route-specific check has to opt in, deliberately,
#: here. That default is the safe one -- the failure this repairs was a check
#: that silently applied to a route it could not speak to, not one that
#: reached too few.
_ROUTE_SPECIFIC: dict[str, frozenset[EvaluationMode]] = {
    "not_runnable_as_stored": frozenset({EvaluationMode.DETERMINISTIC}),
    "not_decidable_as_written": frozenset({EvaluationMode.AI_READY}),
}


def routes_for(code: str) -> frozenset[EvaluationMode] | None:
    """The routes a code speaks to, or ``None`` when it speaks to every route.

    ``None`` is not the empty set: it means "applies everywhere", where the
    empty set would mean "applies nowhere". Keeping them apart is why a
    route-neutral check reads as universal here rather than as speaking to no
    route at all.
    """

    return _ROUTE_SPECIFIC.get(code)


def applies_to(code: str, route: EvaluationMode) -> bool:
    """Whether ``code``'s check speaks to a record on ``route``."""

    routes = _ROUTE_SPECIFIC.get(code)
    return routes is None or route in routes


def classify(code: str, route: EvaluationMode) -> Applicability:
    """Whether ``code``'s check applies to ``route``, as an explicit state.

    Returns ``NOT_APPLICABLE`` rather than a bare ``False`` so a caller has to
    handle the skip as its own outcome, distinct from a passing check, instead
    of dropping it into the same silence as a check that ran and found nothing.
    """

    return Applicability.APPLIES if applies_to(code, route) else Applicability.NOT_APPLICABLE


def not_applicable_here(route: EvaluationMode) -> tuple[str, ...]:
    """The route-specific codes whose check does not speak to ``route``.

    A stated list of what was not asked, so a skip is a fact a caller can read
    off rather than an absence it has to notice. A code named here was withheld
    from this route because it had nothing to assert about it; that is not the
    same as the code having run and passed.
    """

    return tuple(
        code for code, routes in _ROUTE_SPECIFIC.items() if route not in routes
    )
