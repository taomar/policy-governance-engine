"""The methodology version has to move when the method does, and only then.

`quality_runs.methodology_version` is what stops a trend being drawn across
an instrument change: `QualityPage.tsx:475-481` accepts a prior run to diff
against only when the version matches. The guard was correct and inert,
because the value was a hand-maintained constant that stayed at ``"2"``
while the detector suite changed enough to take one unchanged 273-record
set from 23 findings to 99.

These tests pin the mechanism, not the value. The version is *expected* to
change whenever the suite does -- pinning the current digest would recreate
the defect, turning it into a literal somebody edits to make a test pass.
What is pinned is that it changes for the right reasons and not for the
wrong ones.
"""
from __future__ import annotations

import ast
import inspect
import sys
from typing import Any

import pytest

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.quality import ai_quality
from policy_platform.infrastructure.quality.methodology import (
    composed_detectors,
    derive_methodology_version,
    observed_shape,
)

# ---------------------------------------------------------------------------
# Stand-in detectors. Deliberately not the real ones: this file tests the
# derivation, and using real detectors would couple it to their behaviour.
# ---------------------------------------------------------------------------


def _alpha(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    return [
        {
            "severity": "high",
            "category": "alpha",
            "affected_rule_ids": [r.rule_id],
            "finding": "alpha fired",
        }
        for r in rules[:1]
    ]


def _beta(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    return [
        {
            "severity": "low",
            "category": "beta",
            "affected_rule_ids": [r.rule_id],
            "finding": "beta fired",
        }
        for r in rules[:1]
    ]


def _silent(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    # A detector that finds nothing on the probe corpus. Invisible to the
    # behaviour half by construction, so only the inventory can see it.
    return []


def _suite_with_silent_detector_added(
    rules: list[CanonicalRule],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(_alpha(rules))
    findings.extend(_silent(rules))
    return findings


def _alpha_reclassified(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    # Same records, same category, one severity re-ranked. Written out rather
    # than delegating to `_alpha`, which this replaces by monkeypatch.
    return [
        {
            "severity": "medium",
            "category": "alpha",
            "affected_rule_ids": [r.rule_id],
            "finding": "alpha fired",
        }
        for r in rules[:1]
    ]


def _suite(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(_alpha(rules))
    return findings


def _suite_reformatted(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    # Same calls, rewritten: a new comment, different local name, the call
    # split over several lines. Nothing about the method has changed.
    collected: list[dict[str, Any]] = []
    collected.extend(
        _alpha(
            rules,
        )
    )
    return collected


def _suite_with_detector_added(rules: list[CanonicalRule]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(_alpha(rules))
    findings.extend(_beta(rules))
    return findings





# ---------------------------------------------------------------------------
# It moves when the method moves.
# ---------------------------------------------------------------------------


def test_adding_a_detector_moves_the_version() -> None:
    before = derive_methodology_version(_suite)
    after = derive_methodology_version(_suite_with_detector_added)

    assert before != after, (
        "Adding a detector to the suite left the methodology version "
        f"unchanged at {before!r}. That is the defect this replaced: two runs "
        "scored by different suites would claim the same methodology, and "
        "QualityPage would diff them as a trend."
    )


def test_reclassifying_a_severity_moves_the_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Isolates the behaviour half. `_suite` is not edited, so its syntax tree
    # and therefore its inventory are byte-identical across both derivations;
    # only what `_alpha` reports changes. An earlier version of this test
    # expressed the change by rewriting the suite, which also changed its
    # inventory -- so it passed with the behaviour half switched off entirely
    # and proved nothing.
    before = derive_methodology_version(_suite)
    monkeypatch.setattr(sys.modules[__name__], "_alpha", _alpha_reclassified)
    after = derive_methodology_version(_suite)

    assert before != after, (
        "Re-ranking a finding's severity left the methodology version "
        f"unchanged at {before!r}. The suite's source is identical in both "
        "derivations, so the inventory cannot see this; only the behaviour "
        "half can. Without it, the faithfulness severity axis could be "
        "re-ranked and every run would still claim the same method."
    )


def test_a_detector_that_finds_nothing_still_moves_the_version() -> None:
    # The case that separates the two halves. `_silent` reports nothing on the
    # probe corpus, so the behaviour half sees an identical result; only the
    # inventory can tell the suites apart. Without it, a detector could be
    # added, wired and left dormant, and the version would keep claiming the
    # method was unchanged right up until the corpus first tripped it.
    before = derive_methodology_version(_suite)
    after = derive_methodology_version(_suite_with_silent_detector_added)

    assert before != after, (
        "Adding a detector that fires on nothing left the version unchanged at "
        f"{before!r}. Behaviour on the probe corpus is identical in both "
        "suites, so this is the inventory half's job; if it is not doing it, "
        "the derivation only notices detectors the corpus happens to trip."
    )


# ---------------------------------------------------------------------------
# And it holds still when nothing did.
# ---------------------------------------------------------------------------


def test_a_cosmetic_edit_does_not_move_the_version() -> None:
    original = derive_methodology_version(_suite)
    reformatted = derive_methodology_version(_suite_reformatted)

    assert original == reformatted, (
        "Reformatting the suite changed the methodology version from "
        f"{original!r} to {reformatted!r}. A version that moves on comment and "
        "whitespace edits makes every run incomparable with every other, which "
        "is the same field being useless in the opposite direction."
    )


def test_the_version_is_stable_across_reads() -> None:
    values = {derive_methodology_version(_suite) for _ in range(5)}

    assert len(values) == 1, (
        f"Five reads of one unchanged suite produced {sorted(values)}. A "
        "version that varies between reads cannot establish that two runs "
        "share a method."
    )


def test_the_derivation_can_tell_two_suites_apart_at_all() -> None:
    # Negative control. Every assertion above is worthless if the derivation
    # returns something different every time or something constant every time.
    assert derive_methodology_version(_suite) != derive_methodology_version(
        _suite_with_detector_added
    )
    assert derive_methodology_version(_suite) == derive_methodology_version(_suite)


# ---------------------------------------------------------------------------
# The real suite.
# ---------------------------------------------------------------------------


def test_the_real_version_is_derived_and_not_the_constant_it_replaced() -> None:
    version = ai_quality.QUALITY_METHODOLOGY_VERSION

    assert version != "2", (
        "The methodology version is still the hand-maintained '2'. Seven "
        "recorded runs carry that value across a suite change that quadrupled "
        "the finding count; a new run must not claim to share their method."
    )
    assert version.startswith("3-") and len(version) > 2, (
        f"Expected a derived version shaped '3-<digest>', got {version!r}."
    )


def test_the_version_fits_the_column_that_stores_it() -> None:
    # domain/models.py:683 -- String(20).
    version = ai_quality.QUALITY_METHODOLOGY_VERSION

    assert len(version) <= 20, (
        f"Version {version!r} is {len(version)} characters; "
        "quality_runs.methodology_version is varchar(20), so recording a run "
        "would fail at the database rather than here."
    )


def test_every_composed_detector_is_in_the_inventory() -> None:
    inventory = composed_detectors(ai_quality._deterministic_findings)

    assert len(inventory) >= 12, (
        f"The inventory found {len(inventory)} detectors {inventory}, fewer "
        "than the 12 the suite composes. A detector missing from the inventory "
        "is one that can be changed without moving the version."
    )
    assert "_logic_faithfulness_findings" in inventory, (
        "The faithfulness detector is absent from the inventory. Wiring it in "
        "contributed 60 of the 76-finding instrument change that motivated "
        f"this; inventory was {inventory}."
    )


#: What the probe corpus currently reaches. Pinned so that behavioural
#: coverage is a stated fact rather than an assumption -- the derivation is
#: blind to any detector absent from this set, and losing one should fail
#: here rather than quietly weaken the fingerprint.
_COVERED_CATEGORIES = {
    "ambiguity",
    "attribute_not_in_source",
    "decomposition_malformed",
    "duplicate_rule_id",
    "expired_rule",
    "not_decidable_as_written",
    "orphan_exception_fact",
}


def test_the_probe_corpus_still_reaches_what_it_is_recorded_as_reaching() -> None:
    reached = {category for category, _severity, _ids in observed_shape(
        ai_quality._deterministic_findings
    )}

    missing = _COVERED_CATEGORIES - reached
    assert not missing, (
        f"The probe corpus no longer reaches {sorted(missing)}. Expected it to "
        f"reach at least {sorted(_COVERED_CATEGORIES)}; it reached "
        f"{sorted(reached)}. Behavioural coverage shrinking silently is how "
        "the fingerprint stops noticing changes inside a detector."
    )


def test_no_call_site_reads_the_constant_as_a_module_global() -> None:
    """The constant is served by PEP 562 module __getattr__, which is NOT
    consulted for a bare global lookup inside this module's own functions.

    Such a lookup raises NameError, and only at call time -- when someone
    actually evaluates a policy set. A grep looks correct; the code is broken.
    In-module readers must call `_quality_methodology_version()`.
    """
    tree = ast.parse(inspect.getsource(ai_quality))

    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Name)
                and inner.id == "QUALITY_METHODOLOGY_VERSION"
                and isinstance(inner.ctx, ast.Load)
            ):
                offenders.append(inner.lineno)

    assert not offenders, (
        f"ai_quality.py reads QUALITY_METHODOLOGY_VERSION as a module global "
        f"inside a function at line(s) {sorted(offenders)}. Module __getattr__ "
        "does not serve global name resolution, so each of those raises "
        "NameError when the function runs. Expected zero such reads; call "
        "_quality_methodology_version() instead."
    )
