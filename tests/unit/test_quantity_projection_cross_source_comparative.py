"""The quantity compiler across two sources: threshold magnitude vs predicate.

`project_stated_quantity` reads the threshold's magnitude and, when the
threshold states no comparison of its own, is allowed to borrow one from the
predicate. That borrowing is safe only when the predicate's comparison has
nothing of its own to govern. Where the predicate carries its own number, the
comparison there is attached to *that* number -- `stated_comparison` binds a
comparative to the number nearest it -- and lifting it onto the threshold's
magnitude asserts a limit the sentence states about something else.

The canonical shape is a bare count paired with an unrelated deadline: a
magnitude with no relation attached (the module's own example is "3 doses")
sitting beside "no later than 30 days", whose comparison governs the days, not
the count. Compiling that as "doses <= 3" manufactures a limit the document
never stated -- the exact failure the compiler exists to refuse.

Phrasings here are constructed rather than lifted from any document the project
holds, and the numerals are illustrative constituents of those constructions,
not counts observed in a corpus. The suite asserts the reader handles a
*construction* -- a comparison in a number-bearing predicate -- not a document.
"""

from __future__ import annotations

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.extraction.quantity_projection import (
    QuantityRefusal,
    project_stated_quantity,
)


def _rule(**kwargs) -> CanonicalPolicyRule:
    base = {
        "rule_type": CanonicalRuleType.OBLIGATION,
        "subject": "the administered course",
        "predicate": "is recorded",
    }
    base.update(kwargs)
    return CanonicalPolicyRule(**base)


def test_a_predicate_comparison_governing_its_own_number_does_not_bind_the_threshold() -> None:
    """A borrowed comparison must not be applied to a magnitude it never governed.

    The threshold is a bare count with no comparison of its own. The predicate
    carries a comparison, but it is attached to the predicate's own number -- a
    deadline -- and says nothing about the count. Reading it as the count's
    limit compiles a threshold the document never stated: it looks computable
    and will be computed. A manufactured limit is worse than an absent one, so
    the only correct outcome is a refusal, not a compiled comparison.
    """

    projection = project_stated_quantity(
        _rule(
            threshold="3 doses",
            predicate="administered no later than 30 days after exposure",
        )
    )

    assert projection is not None
    assert not projection.compiled
    assert projection.condition is None
    assert projection.refusal is QuantityRefusal.NO_COMPARISON


def test_a_predicate_comparison_still_binds_when_it_governs_no_number_of_its_own() -> None:
    """The intended borrowing is preserved: a number-free predicate still lifts.

    Here the predicate's comparison has no number of its own to govern, so it
    is a statement about the threshold's magnitude and lifting it is the right
    read. This is the boundary's other side -- the fix refuses only when the
    predicate has a competing number, never a number-free predicate comparison.
    """

    projection = project_stated_quantity(
        _rule(
            threshold="3 doses",
            predicate="must not exceed the stated allowance",
        )
    )

    assert projection is not None
    assert projection.compiled
