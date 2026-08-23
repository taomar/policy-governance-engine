"""Every check that exercises judgement declares what it does NOT fire on.

WHY THIS EXISTS

Two false positives reached a user in one session, both the same shape, and
neither was caught by 3,400 passing tests:

  * `decomposition_malformed` called a back-pointer damage because the check
    read the record without the passage it was cut from, where the antecedent
    sat one sentence away;
  * `not_decidable_as_written` called a fully specified salary rule silent
    because the check read the structured decomposition and not the sentence a
    judge actually reads.

Both were untested *in the exonerating direction*. There were tests proving each
check fires — 26 `assess()` call sites for the first — and none proving what it
must stay quiet about. A check with only positive tests is one nobody has asked
"what would you wrongly accuse?", and the answer then arrives from a user
looking at their own policy.

THE LINE THIS DRAWS

Not every finding needs a negative case, and demanding one everywhere would make
this guard noise. The distinction is whether the check *judges* or *measures*:

  * A check over a canonical record decides whether a policy is deficient. It
    reads a projection of the record, and the projection can be narrower than
    what the decider reads. That is exactly how both false positives happened,
    and those checks must declare what they stay silent on.

  * A check over a file, a parse or a graph reports something that either
    happened or did not — a page that failed to parse, a rotated run, an offset
    that will not resolve. There is no judgement to misapply, and a negative
    case would only restate the positive one.

The split is by module rather than by a hand-kept list of codes, so a new check
lands on the correct side without anyone remembering to classify it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "policy_platform"

#: Modules whose findings judge a policy record. Everything else measures a
#: file, a parse or a graph — see the module docstring for why the two are held
#: to different standards.
_JUDGING_MODULES = (
    "infrastructure/quality/",
    "infrastructure/extraction/",
)

#: Not findings. `snake_case` is the placeholder inside the AI prompt's own JSON
#: template; the `derived*` values label where a quantity came from rather than
#: reporting a defect. Listed with reasons so the population is a decision and
#: not an accident of the regex.
_NOT_A_FINDING: frozenset[str] = frozenset(
    {
        "snake_case",
        "derived",
        "derived_from_stated_quantity",
        "derived_from_stated_bound",
    }
)

_CODE_PATTERNS = (
    re.compile(r'code="([a-z_]+)"'),
    re.compile(r'"category":\s*"([a-z_]+)"'),
)


def _codes_by_module() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        codes = {m for pattern in _CODE_PATTERNS for m in pattern.findall(text)}
        codes -= _NOT_A_FINDING
        if codes:
            found[path.relative_to(_SRC).as_posix()] = codes
    return found


def _judging_codes() -> set[str]:
    return {
        code
        for module, codes in _codes_by_module().items()
        if module.startswith(_JUDGING_MODULES)
        for code in codes
    }


#: Codes with a fixture that resembles the defect and asserts silence, and the
#: test carrying it. The citation is checked for existence below, because a
#: reference nobody can follow is not evidence.
HAS_A_NEGATIVE_CASE: dict[str, str] = {
    "decomposition_malformed": "tests/unit/test_a_backpointer_with_its_antecedent_is_not_damage.py",
    "not_decidable_as_written": "tests/unit/test_a_validation_reads_what_the_decider_reads.py",
    "attribute_not_in_source": "tests/unit/test_extraction_quality_checks.py",
    "condition_not_compiled": "tests/unit/test_route_applicability.py",
    "source_condition_not_captured": (
        "tests/unit/test_a_record_that_decides_nothing_is_informational.py"
    ),
}

#: Judging checks with no negative case yet, and what a fixture would have to
#: look like. Naming the missing fixture is the point: it turns "untested" into
#: a task somebody can pick up, and it is how the two known false positives
#: would have been predicted rather than discovered from a screenshot.
NO_NEGATIVE_CASE_YET: dict[str, str] = {
    "action_fragment": "an action that is short but complete, not a fragment",
    "action_missing": "a record whose effect action is present but terse",
    "ambiguity": "unambiguous wording that nonetheless carries a modal",
    "authority_from_negated_phrase": "an authority named inside a negated clause that IS the authority",
    "conditions_not_projected": "a condition that legitimately projects to nothing",
    "conditions_not_representable": "a condition representable in an unusual shape",
    "conflicting_effect": "two effects that differ without conflicting",
    "contradictory_reading": "two readings differing in emphasis, not outcome",
    "decision_split_across_records": "one decision deliberately stated as a ladder",
    "definition_carries_effect": "a definition mentioning an effect without stating one",
    "degenerate_predicate": "a short predicate that is nonetheless complete",
    "discretion_without_authority": "a delegation that does name its authority",
    "duplicate_extraction": "two records from one passage stating different rules",
    "duplicate_rule": "two rules that resemble each other but decide different cases",
    "duplicate_rule_id": "an id reused across versions, which is legitimate",
    "eligibility_polarity_inversion": "an eligibility rule stated negatively on purpose",
    "expired_rule": "a closed window retained deliberately",
    "invalid_candidate_payload": "a payload with optional fields absent",
    "negation_dropped": "a negation carried by the effect rather than the predicate",
    "no_scope_derived": "a record whose scope is genuinely global",
    "not_runnable_as_stored": "a deterministic record declaring every fact it names",
    "orphan_exception_fact": "an exception fact declared on the parent",
    "party_not_in_source": "a party quoted with different casing or an honorific",
    "polarity_doubled_in_projection": "a double negative that is correct in the source",
    "polarity_lost_in_projection": "polarity carried by the effect type",
    "qualifier_promoted_to_record": "a qualifier that genuinely is its own rule",
    "quantity_dropped": "a quantity carried in the threshold rather than the predicate",
    "record_does_not_stand_alone": "a record that reads alone despite naming its section",
    "record_reference_is_opaque": "an opaque reference resolved by the evidence",
    "review_backlog": "a backlog within tolerance",
    "review_coverage": "coverage below target for a stated reason",
    "stated_quantity_comes_from_a_table_row": "a quantity in prose beside a table",
    "stated_quantity_is_one_clause_of_a_provision": "a provision whose single clause is the quantity",
    "unstable_extraction": "two runs differing only in rule id",
}


def test_the_population_is_not_empty():
    """Positive control. An empty scan satisfies every assertion below."""

    assert len(_judging_codes()) > 20
    assert len(_codes_by_module()) > 5


def test_every_judging_check_is_classified():
    """A check that decides whether a policy is deficient cannot ship without
    somebody deciding what it must not accuse."""

    unclassified = sorted(
        _judging_codes() - set(HAS_A_NEGATIVE_CASE) - set(NO_NEGATIVE_CASE_YET)
    )

    assert not unclassified, (
        "these checks judge a policy record but declare neither a negative case "
        "nor what one would look like. Add each to HAS_A_NEGATIVE_CASE with the "
        "test proving it stays silent on a record resembling the defect, or to "
        "NO_NEGATIVE_CASE_YET describing the fixture that is missing:\n  "
        + "\n  ".join(unclassified)
    )


def test_no_entry_protects_a_code_that_no_longer_exists():
    """The rule the capability quarantine already keeps: an entry protecting
    nothing is removed, so this list shrinks as checks are fixed or deleted."""

    declared = set(HAS_A_NEGATIVE_CASE) | set(NO_NEGATIVE_CASE_YET)
    stale = sorted(declared - _judging_codes())

    assert not stale, (
        "declared here but no longer emitted by a judging module — remove:\n  "
        + "\n  ".join(stale)
    )


def test_a_code_is_not_both_proven_and_excused():
    both = sorted(set(HAS_A_NEGATIVE_CASE) & set(NO_NEGATIVE_CASE_YET))
    assert not both, "declared as both proven and unproven:\n  " + "\n  ".join(both)


@pytest.mark.parametrize("code", sorted(HAS_A_NEGATIVE_CASE))
def test_each_cited_negative_case_exists(code: str):
    path = _ROOT / HAS_A_NEGATIVE_CASE[code]
    assert path.exists(), f"{code} cites {HAS_A_NEGATIVE_CASE[code]}, which does not exist"


def test_measuring_checks_are_exempt_by_module_not_by_omission():
    """The exemption is a stated rule, so a new ingestion diagnostic inherits it
    and a new record check does not.

    Without this, "in neither list" would be indistinguishable from "nobody
    looked" — the state this whole guard exists to end.
    """

    by_module = _codes_by_module()
    measuring = {
        module: codes
        for module, codes in by_module.items()
        if not module.startswith(_JUDGING_MODULES)
    }

    assert measuring, "no measuring modules found; the split has stopped working"

    declared = set(HAS_A_NEGATIVE_CASE) | set(NO_NEGATIVE_CASE_YET)
    judging = _judging_codes()
    misfiled = sorted(
        code
        for codes in measuring.values()
        for code in codes
        if code in declared and code not in judging
    )
    assert not misfiled, (
        "declared as judging checks but only emitted by file-measurement "
        "modules:\n  " + "\n  ".join(misfiled)
    )
