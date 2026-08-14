"""An identity that omits what a rule decides forges approvals.

When a document is re-extracted, `diff_runs` decides for each new rule whether
we have seen it before. A verdict of `unchanged` is not a report — it causes the
previous run's `review_status`, `reviewed_by` and `reviewed_at` to be copied
onto the new row. So if two genuinely different rules are called the same rule,
a named human is recorded as having approved a rule they never read, and nothing
downstream can tell: the row looks like any other approved row.

The first version of the content fingerprint hashed an allowlist of ten
top-level fields. The canonical rule core — subject, predicate, trigger,
deadline, temporal constraint — was in none of them. Three pairs of genuinely
different rules in one live run hashed identically and matched as `unchanged`;
the pairs below are modelled on them.

The corroboration `diff_runs` already applies does not save it. Tier 1 requires
the source passage to agree before it will call a match `unchanged`, on the
stated grounds that carrying an approval across clauses "would move a citation
without anyone deciding to". But two rules extracted from *one* clause share
that passage exactly, so the corroboration confirms and the wrong verdict
stands. The corroboration guards the wrong axis; the identity has to be right.

These tests pin the property rather than the field list: whatever the fingerprint
is built from, a difference in what the rule decides must reach it.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.projection.rule_delta import (
    diff_runs,
    identify,
    semantic_core,
)

SHARED_PASSAGE = (
    "The employee shall return all issued equipment, and shall confirm the "
    "return in writing to the department that issued it."
)


def _rule(rule_id: str, **core: object) -> dict:
    """A payload shaped like a real one, with the rule core where it really lives.

    Two rules built by this helper differ only in the core fields passed in, so a
    test that asserts they are distinguished is asserting exactly one thing.
    """
    rule = {
        "subject": "the employee",
        "predicate": "shall return",
        "object": "all issued equipment",
        "modality": "obligation",
        "trigger": None,
        "deadline": None,
        "temporal_constraint": None,
    }
    rule.update(core)
    return {
        "rule_id": rule_id,
        "rule_type": "obligation",
        "effect": "permit",
        "scope": None,
        "condition": None,
        "title": "Return of equipment",
        "description": "The employee returns issued equipment.",
        "effective_from": "2024-01-01",
        "lineage": {"run": rule_id},
        "evidence": [{"page": 3}],
        "formulation": {
            "source_text": SHARED_PASSAGE,
            "canonical": {"source_text": SHARED_PASSAGE, "rule": rule},
        },
        "attributes": {"subject": rule["subject"]},
    }


CORE_DIFFERENCES = [
    pytest.param(
        {"trigger": "In the event of termination from employment"},
        {"trigger": "upon request by the issuing department"},
        id="trigger: two different occasions to act",
    ),
    pytest.param(
        {"subject": "the receipt of the equipment"},
        {"subject": "the issue of the equipment"},
        id="subject: two different things acted on",
    ),
    pytest.param(
        {"temporal_constraint": "at the end of the probationary period"},
        {"temporal_constraint": "during the probationary period"},
        id="temporal: a boundary against a span",
    ),
    pytest.param(
        {"predicate": "shall return"},
        {"predicate": "shall not return"},
        id="predicate: a dropped negation",
    ),
    pytest.param(
        {"deadline": None},
        {"deadline": "immediately"},
        id="deadline: absent against stated",
    ),
    pytest.param(
        {"modality": "obligation"},
        {"modality": "permission"},
        id="modality: must against may",
    ),
]


@pytest.mark.parametrize(("left_core", "right_core"), CORE_DIFFERENCES)
def test_a_difference_in_what_the_rule_decides_reaches_the_fingerprint(
    left_core: dict, right_core: dict
) -> None:
    left = identify(_rule("AI-left", **left_core))
    right = identify(_rule("AI-right", **right_core))

    assert left.content_fingerprint != right.content_fingerprint, (
        "expected two rules that decide different things to fingerprint "
        f"differently; got the same fingerprint for {left_core} and {right_core}"
    )


@pytest.mark.parametrize(("left_core", "right_core"), CORE_DIFFERENCES)
def test_two_rules_from_one_clause_that_decide_differently_are_not_unchanged(
    left_core: dict, right_core: dict
) -> None:
    """The end-to-end consequence, on the path that copies the approval.

    `unchanged` is the verdict that carries `review_status` forward. Asserting on
    the fingerprint alone would leave the possibility that some later tier
    reaches the same wrong answer by another route.
    """
    result = diff_runs(
        new_rules=[("right", _rule("AI-right", **right_core))],
        baseline_rules=[("left", _rule("AI-left", **left_core))],
    )

    verdicts = {match.delta_status for match in result.matches.values()}
    assert "unchanged" not in verdicts, (
        "expected a rule deciding something different from the baseline not to "
        f"be carried forward as unchanged; got {sorted(verdicts)} for "
        f"{left_core} against {right_core}"
    )


def test_the_same_rule_reworded_is_still_carried_forward() -> None:
    """The positive control, and the reason the fix is not simply "hash it all".

    Rewording is the case cross-run identity exists to absorb: the model writes
    the same rule differently every run, and a reviewer who approved it should
    not be asked again. If widening the fingerprint swept prose in, every rule
    would come back `changed` and carry-forward would stop working — a fix that
    breaks the feature it was protecting.
    """
    baseline = _rule("AI-baseline")
    reworded = _rule("AI-reworded")
    reworded["title"] = "Equipment must be given back"
    reworded["description"] = "Kit issued to staff is handed back on leaving."

    result = diff_runs(
        new_rules=[("reworded", reworded)],
        baseline_rules=[("baseline", baseline)],
    )

    (match,) = result.matches.values()
    assert match.delta_status == "unchanged", (
        "expected a reworded but semantically identical rule to stay unchanged; "
        f"got {match.delta_status}"
    )
    assert match.reworded is True, (
        "expected the rewrite to be reported so a reviewer can see it; got reworded=False"
    )


def test_identity_ignores_a_rules_position_in_the_models_output() -> None:
    """Position is not something a rule decides.

    The model emits an array of canonical policies; a record's index in it, and a
    DMN decision's back-references to those indexes, describe the shape of one
    response rather than the policy. Two records alike but for these are the same
    record emitted twice.
    """
    first = _rule("AI-first")
    first["formulation"]["source_index"] = 0
    first["formulation"]["decisions"] = [{"source_rule_indexes": [0]}]
    second = _rule("AI-second")
    second["formulation"]["source_index"] = 3
    second["formulation"]["decisions"] = [{"source_rule_indexes": [3]}]

    assert identify(first).content_fingerprint == identify(second).content_fingerprint, (
        "expected two records differing only in their position in the model's "
        "output array to share an identity; got different fingerprints"
    )


def test_provenance_does_not_make_a_rule_a_different_rule() -> None:
    """Otherwise every rule is new every run and the delta reports nothing."""
    first = _rule("AI-first")
    second = _rule("AI-second")
    second["effective_from"] = "2025-06-01"
    second["lineage"] = {"run": "a completely different run"}
    second["evidence"] = [{"page": 99}]

    assert identify(first).content_fingerprint == identify(second).content_fingerprint, (
        "expected a rule's identity to survive a change of provenance; got "
        "different fingerprints"
    )


def test_an_unclassified_field_is_included_rather_than_ignored() -> None:
    """The direction the definition fails in, asserted rather than assumed.

    This is the whole argument for excluding rather than listing. A field added
    next year that nobody classifies must make two rules look *different* — that
    costs a reviewer a question. The other way round it costs a reviewer their
    signature on a rule they never read.
    """
    known = _rule("AI-known")
    with_new_field = _rule("AI-new")
    with_new_field["a_field_no_one_has_classified_yet"] = "carries meaning"

    assert semantic_core(known) != semantic_core(with_new_field), (
        "expected an unclassified field to be part of the core, so that the "
        "definition fails towards asking rather than towards assuming"
    )
