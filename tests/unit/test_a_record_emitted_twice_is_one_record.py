"""A record emitted twice is one record — and everything that is not that.

This is the first pass in the system that removes anything, so most of what is
pinned here is what it must decline to remove. The happy path is one test; the
refusals are the rest, because each of them is a way to delete policy.

The failure this exists to fix is real and measured: across four live runs the
model emitted byte-identical records twice for a single source span, differing
only in their position in its own output array. No prompt reliably suppresses a
sampling artefact, and identity is currently computed after persistence, so
nothing can catch it at write time either.
"""

from __future__ import annotations

from policy_platform.infrastructure.consolidation.duplicate_records import (
    record_key,
    repeated_records,
    source_span,
)

SPAN = "p7-E000112"


def _record(**overrides) -> dict:
    """A payload shaped like a real one, placed in SPAN unless told otherwise."""
    rule = {
        "subject": "the employee",
        "predicate": "shall submit",
        "object": "a medical certificate",
        "modality": "obligation",
    }
    rule.update(overrides.pop("rule", {}))
    payload = {
        "rule_id": overrides.pop("rule_id", "AI-000000"),
        "rule_type": "obligation",
        "effect": "permit",
        "title": "Medical certificate",
        "description": "A certificate is submitted.",
        "lineage": {"source_elements": overrides.pop("span", SPAN)},
        "evidence": [{"page": 7}],
        "formulation": {
            "source_text": "The employee shall submit a medical certificate.",
            "canonical": {
                "source_text": "The employee shall submit a medical certificate.",
                "rule": rule,
            },
        },
        "attributes": {"subject": rule["subject"]},
    }
    payload.update(overrides)
    return payload


def test_the_same_record_emitted_twice_for_one_span_is_one_record() -> None:
    """The measured defect: identical but for a position in the model's output."""
    first = _record(rule_id="AI-first")
    first["formulation"]["source_index"] = 0
    second = _record(rule_id="AI-second")
    second["formulation"]["source_index"] = 4

    found = repeated_records([("a", first), ("b", second)])

    assert len(found) == 1, f"expected one repetition; got {len(found)}"
    assert found[0].copies == 2
    assert found[0].keep == "a"
    assert found[0].redundant == ("b",)


def test_a_span_that_states_two_different_things_keeps_both() -> None:
    """One span often yields several genuine records. That is normal extraction."""
    obligation = _record(rule_id="AI-a")
    permission = _record(rule_id="AI-b", rule={"modality": "permission"})

    assert repeated_records([("a", obligation), ("b", permission)]) == []


def test_the_same_obligation_stated_twice_in_a_document_is_two_facts() -> None:
    """Same content is not the test — same *span* is.

    A document that states one obligation in two places has said it twice, and
    which places it said it in is a fact about the document. Collapsing them
    would rewrite what the document does.
    """
    here = _record(rule_id="AI-a", span="p3-E000041")
    there = _record(rule_id="AI-b", span="p19-E000390")

    assert record_key(here) == record_key(there), (
        "fixture is not exercising the guard: these two records must have "
        "identical content, differing only in where they were cut from"
    )
    assert repeated_records([("a", here), ("b", there)]) == [], (
        "expected one obligation stated in two places to remain two records"
    )


def test_records_that_cannot_be_placed_never_match_each_other() -> None:
    """An absent span is not a span two records share.

    This is not hypothetical: an entire live run of 242 rows carries no
    fingerprint, because the pass that writes them runs after every batch and
    that run stalled first. Matching absence against absence would have
    discarded records across the whole of it.
    """
    first = _record(rule_id="AI-a")
    second = _record(rule_id="AI-b")
    for payload in (first, second):
        payload["lineage"] = {}
        payload["evidence"] = []

    assert source_span(first) is None
    assert repeated_records([("a", first), ("b", second)]) == [], (
        "expected two unplaceable records to stay two records"
    )


def test_records_with_nothing_to_compare_never_match_each_other() -> None:
    """A missing rule core is an absence too, and absences do not match."""
    first = _record(rule_id="AI-a")
    second = _record(rule_id="AI-b")
    for payload in (first, second):
        payload["formulation"] = {"canonical": {"rule": {}}}

    assert repeated_records([("a", first), ("b", second)]) == [], (
        "expected two records with no readable core to stay two records"
    )


def test_a_difference_in_wording_is_not_this_tiers_business() -> None:
    """Within one run, differing prose means it is not the repetition being removed.

    Deciding that two differently-worded records are really one decision is a
    judgement, and this tier is the one with no judgement in it. Note this is the
    opposite of what the cross-run delta does with prose, and for the same
    reason: there, rewording between runs must be seen through; here, there is
    nothing to see through.
    """
    first = _record(rule_id="AI-a")
    second = _record(rule_id="AI-b")
    second["description"] = "Staff hand in a doctor's note."

    assert repeated_records([("a", first), ("b", second)]) == []


def test_provenance_does_not_stop_two_copies_being_two_copies() -> None:
    """Otherwise nothing is ever a duplicate: every row has its own provenance."""
    first = _record(rule_id="AI-a")
    second = _record(rule_id="AI-b")
    second["evidence"] = [{"page": 7, "extracted_at": "later"}]

    found = repeated_records([("a", first), ("b", second)])

    assert len(found) == 1, (
        "expected two copies differing only in provenance to be one record; "
        f"got {len(found)} groups"
    )


def test_running_it_again_after_the_copies_are_gone_finds_nothing() -> None:
    """Idempotence, as an effect rather than a promise."""
    records = [
        ("a", _record(rule_id="AI-a")),
        ("b", _record(rule_id="AI-b")),
        ("c", _record(rule_id="AI-c")),
    ]

    first_pass = repeated_records(records)
    assert first_pass[0].redundant == ("b", "c")

    discarded = set(first_pass[0].redundant)
    survivors = [(key, payload) for key, payload in records if key not in discarded]

    assert repeated_records(survivors) == [], (
        "expected a second pass over the survivors to find nothing to do"
    )


def test_the_answer_does_not_depend_on_the_order_records_arrive_in() -> None:
    """Two callers holding the same records must be told the same thing."""
    records = [
        ("a", _record(rule_id="AI-a")),
        ("b", _record(rule_id="AI-b")),
        ("z", _record(rule_id="AI-z", rule={"modality": "permission"})),
    ]

    forwards = repeated_records(records)
    backwards = repeated_records(list(reversed(records)))

    assert forwards == backwards, (
        f"expected order-independence; got {forwards} against {backwards}"
    )


def test_nothing_is_discarded_without_being_named() -> None:
    """Reversibility starts here: the pass reports, it does not remove.

    Supersession has already fired during a run that then failed and left a
    reviewer with fewer records than they started with. A pass that returns the
    keys it would discard lets the caller record the removal in a form it can
    undo.
    """
    records = [("a", _record(rule_id="AI-a")), ("b", _record(rule_id="AI-b"))]
    before = [dict(payload) for _, payload in records]

    found = repeated_records(records)

    assert [dict(payload) for _, payload in records] == before, (
        "expected the pass to leave its input untouched"
    )
    assert found[0].keep not in found[0].redundant, (
        "expected the surviving record never to appear among the discarded"
    )


def test_three_copies_leave_one() -> None:
    records = [(k, _record(rule_id=f"AI-{k}")) for k in ("a", "b", "c", "d")]

    (found,) = repeated_records(records)

    assert found.copies == 4
    assert found.keep == "a"
    assert found.redundant == ("b", "c", "d")
