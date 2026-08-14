"""A restatement is not a second fact, and an unknown is not a match.

Duplicates were accumulating because identity was computed *after* persistence:
nothing could recognise a repeat at the moment of writing, so the store took
them from any source. Identity is now established before the write.

Three distinctions have to survive that change, and each was established by
measuring the live store rather than by reasoning about it:

* A document can genuinely state the same obligation in two places. Those are
  two facts about the document, not one, and collapsing on content alone would
  silently delete one of them.
* One sentence can legitimately yield several rules that cite the same clause
  and share a semantic fingerprint while differing in what they say. Keying on
  the fingerprint would have merged 12 such groups.
* Where identity cannot be established at all, nothing may be discarded.
  "Unknown" is not a value that can match another "unknown".
"""

from __future__ import annotations

import ast
from pathlib import Path

from policy_platform.infrastructure.extraction.ai_extraction import (
    _EMISSION_FIELDS,
    _repetition_key,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXTRACTION = (
    _REPO_ROOT / "src" / "policy_platform" / "infrastructure" / "extraction" / "ai_extraction.py"
)


def _rule(clause: str = "clause-1", **fields) -> dict:
    payload = {
        "title": "Employees must sign the attendance book",
        "description": "Attendance is recorded on entry and exit.",
        "attributes": {"party": "employees", "predicate": "must sign"},
        "evidence": [{"clause_id": clause, "page": 3}],
    }
    payload.update(fields)
    return payload


# --------------------------------------------------------------------------
# What repetition is
# --------------------------------------------------------------------------


def test_the_same_rule_restated_from_the_same_clause_is_one_fact() -> None:
    first = _repetition_key(_rule())
    second = _repetition_key(_rule())
    assert first is not None
    assert first == second


def test_a_fresh_identifier_does_not_make_it_a_different_rule() -> None:
    """The observed duplicates all carried differing identifiers.

    That is what proved they were model repetition rather than a retry. If the
    identifier counted towards identity, none of them would be recognised.
    """
    first = _repetition_key(_rule(rule_id="rule-aaa"))
    second = _repetition_key(_rule(rule_id="rule-bbb"))
    assert first == second, (
        "two identical rules differing only in their assigned identifier produced "
        f"different keys ({first!r} vs {second!r}). Every duplicate observed in the live "
        "store differs in exactly this way, so none of them would be caught."
    )


def test_every_excluded_field_is_excluded_for_that_reason() -> None:
    """Each emission field must be individually incapable of splitting a key."""
    base = _repetition_key(_rule())
    for field in _EMISSION_FIELDS:
        altered = _repetition_key(_rule(**{field: {"changed": "value"}}))
        assert altered == base, (
            f"{field!r} is listed as an emission field but still changes the repetition "
            f"key ({altered!r} vs {base!r})."
        )


# --------------------------------------------------------------------------
# What repetition is not
# --------------------------------------------------------------------------


def test_the_same_wording_from_a_different_clause_is_two_facts() -> None:
    """A document may state one obligation in two places. Both must survive."""
    here = _repetition_key(_rule(clause="clause-1"))
    there = _repetition_key(_rule(clause="clause-2"))
    assert here is not None and there is not None
    assert here != there, (
        f"two rules with identical wording, cited from different clauses, produced the "
        f"same repetition key ({here!r}). That collapses two facts about the document "
        "into one and deletes a real provision."
    )


def test_one_sentence_may_yield_several_distinct_rules() -> None:
    """"Disclosure, distribution or copying is prohibited" is three rules.

    They share a clause and would share a semantic fingerprint. Only the
    statement itself tells them apart.
    """
    keys = {
        _repetition_key(
            _rule(
                title=f"{verb} is prohibited",
                attributes={"party": "employees", "predicate": f"{verb} is prohibited"},
            )
        )
        for verb in ("Disclosure", "Distribution", "Copying")
    }
    assert None not in keys
    assert len(keys) == 3, (
        f"three rules drawn from one sentence produced {len(keys)} distinct key(s). "
        "Merging them would delete real provisions from the register."
    )


def test_a_difference_a_reviewer_can_see_keeps_rules_apart() -> None:
    assert _repetition_key(_rule()) != _repetition_key(_rule(description="Something else."))
    assert _repetition_key(_rule()) != _repetition_key(
        _rule(attributes={"party": "contractors", "predicate": "must sign"})
    )


# --------------------------------------------------------------------------
# Where identity cannot be established, nothing is discarded
# --------------------------------------------------------------------------


def test_a_rule_citing_no_clause_is_never_a_repetition() -> None:
    assert _repetition_key({"title": "x", "evidence": []}) is None
    assert _repetition_key({"title": "x"}) is None


def test_two_unidentifiable_rules_do_not_match_each_other() -> None:
    first = _repetition_key({"title": "x", "evidence": []})
    second = _repetition_key({"title": "x", "evidence": []})
    assert first is None and second is None, (
        f"an unidentifiable rule produced a matchable key ({first!r}). Unknown must "
        "never equal unknown, or rules that merely lack provenance would be deleted as "
        "duplicates of each other."
    )


def test_malformed_evidence_does_not_crash_or_match() -> None:
    assert _repetition_key({"title": "x", "evidence": ["not-a-dict", None]}) is None


def test_a_statement_of_nothing_but_identifiers_is_not_matchable() -> None:
    """Provenance without a statement is not something that can repeat."""
    assert _repetition_key({"rule_id": "a", "evidence": [{"clause_id": "c"}]}) is None
    assert _repetition_key({"rule_id": "a"}) is None
    assert _repetition_key({"title": "x", "evidence": [{"clause_id": "c"}]}) is not None


def test_the_order_citations_were_emitted_in_is_not_a_difference() -> None:
    a = _repetition_key({"title": "x", "evidence": [{"clause_id": "a"}, {"clause_id": "b"}]})
    b = _repetition_key({"title": "x", "evidence": [{"clause_id": "b"}, {"clause_id": "a"}]})
    assert a is not None
    assert a == b, (
        f"the same rule citing the same two clauses in a different order produced "
        f"different keys ({a!r} vs {b!r}). Emission order is not a claim about the "
        "document."
    )


# --------------------------------------------------------------------------
# The rule is actually applied at the seam
# --------------------------------------------------------------------------


def _seam() -> ast.Module:
    assert _EXTRACTION.is_file(), f"the extraction module is not at {_EXTRACTION}"
    return ast.parse(_EXTRACTION.read_text(encoding="utf-8"))


def test_identity_is_established_before_the_write() -> None:
    """The defect was ordering: identity computed after persistence.

    `_repetition_key` must be called, and it must be called before the row is
    created — otherwise the key is computed and the duplicate written anyway.
    """
    tree = _seam()
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_repetition_key"
    ]
    assert calls, (
        "_repetition_key is never called. Identity would again be established only "
        "after the write, which is the defect this exists to close."
    )

    creates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "candidate_repo"
    ]
    assert creates, "no candidate_repo.create(...) call found; this guard is watching nothing"
    first_key, first_write = min(c.lineno for c in calls), min(c.lineno for c in creates)
    assert first_key < first_write, (
        f"identity is established at line {first_key} but the row is written at line "
        f"{first_write}. Computing identity after the write is exactly the ordering that "
        "let duplicates accumulate."
    )


def test_an_unidentifiable_rule_is_still_written() -> None:
    """The repetition check must be guarded by `key is not None`.

    Absence of identity must never be grounds for discarding a rule.
    """
    tree = _seam()
    guarded = any(
        isinstance(node, ast.BoolOp)
        and isinstance(node.op, ast.And)
        and "IsNot" in ast.dump(node)
        and "'key'" in ast.dump(node).replace('"', "'")
        for node in ast.walk(tree)
    )
    assert guarded, (
        "the repetition check is not guarded by `key is not None`. Without that guard a "
        "rule with no establishable identity could be discarded as a duplicate of another "
        "rule with no establishable identity."
    )


def test_a_repetition_is_not_counted_as_a_coverage_shortfall() -> None:
    """`repeated` and `skipped` are different ledgers and must stay apart.

    A skip is material this system did not read. A repetition is a fact already
    recorded. Appending repetitions to `skipped` would mark a run
    `completed_with_gaps` for having read the document correctly.
    """
    tree = _seam()
    ledgers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "append" or not isinstance(node.func.value, ast.Name):
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if (
                    isinstance(sub, ast.Constant)
                    and isinstance(sub.value, str)
                    and "restated" in sub.value
                ):
                    ledgers.add(node.func.value.id)

    assert ledgers, "no ledger records a restated rule; this guard is watching nothing"
    assert "skipped" not in ledgers, (
        f"a restatement is recorded in {sorted(ledgers)}, which includes the skip ledger. "
        "That would report a run as having incomplete coverage because the model repeated "
        "itself."
    )


def test_the_repetition_ledger_reaches_the_caller() -> None:
    """A dropped row that nobody is told about is a silent reduction."""
    source = _EXTRACTION.read_text(encoding="utf-8")
    assert '"repeated": repeated' in source, (
        "the repetition ledger is not returned to the caller, so rows would be dropped "
        "without the reader ever being told."
    )
