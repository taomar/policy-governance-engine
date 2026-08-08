"""Delta classification: what a re-extraction actually changed.

These tests pin the behaviour a reviewer depends on. The load-bearing one is
`test_reworded_identical_rule_is_unchanged`: the language model rewrites prose on
every run, so if rewording counted as a change the delta feature would report
every rule as changed and be worth nothing.
"""

from __future__ import annotations

from policy_platform.infrastructure.rule_delta import (
    SIMILARITY_THRESHOLD,
    diff_runs,
    identify,
    jaccard,
)


def rule(
    *,
    rule_id: str = "AI-abc123",
    title: str = "Encryption required",
    description: str = "All laptops must be encrypted.",
    source_text: str = "Every device must carry full-disk encryption before issue.",
    effect: str = "deny",
    priority: int = 100,
    condition: dict | None = None,
) -> dict:
    return {
        "rule_id": rule_id,
        "rule_revision": 1,
        "title": title,
        "description": description,
        "rule_type": "obligation",
        "scope": {"applies_to": ["laptop"]},
        "condition": condition or {"op": "eq", "field": "encrypted", "value": False},
        "effect": effect,
        "priority": priority,
        "exceptions": [],
        "required_facts": ["encrypted"],
        "effective_from": "2026-08-08",
        "lineage": {"extracted_by": "run-1"},
        "formulation": {"source_text": source_text},
    }


class TestIdentity:
    def test_volatile_fields_do_not_affect_content_fingerprint(self):
        """rule_id is random per rule and effective_from is date.today().

        Either one leaking into identity would make every re-extraction report
        every rule as changed.
        """
        a = identify(rule(rule_id="AI-111"))
        b = identify(rule(rule_id="AI-999"))
        b_payload = rule(rule_id="AI-999")
        b_payload["effective_from"] = "2027-01-01"
        b_payload["lineage"] = {"extracted_by": "run-2"}
        assert a.content_fingerprint == b.content_fingerprint
        assert a.content_fingerprint == identify(b_payload).content_fingerprint

    def test_prose_is_not_part_of_content_identity(self):
        a = identify(rule(title="Encryption required"))
        b = identify(rule(title="Devices shall be encrypted", description="Different words."))
        assert a.content_fingerprint == b.content_fingerprint
        assert a.prose_fingerprint != b.prose_fingerprint

    def test_semantic_change_changes_content_fingerprint(self):
        assert identify(rule(effect="deny")).content_fingerprint != identify(rule(effect="allow")).content_fingerprint
        assert identify(rule(priority=100)).content_fingerprint != identify(rule(priority=50)).content_fingerprint

    def test_anchor_ignores_whitespace_and_case(self):
        a = identify(rule(source_text="Every device must carry full-disk encryption."))
        b = identify(rule(source_text="  EVERY   device must carry FULL-DISK encryption.  "))
        assert a.anchor_fingerprint == b.anchor_fingerprint

    def test_anchor_falls_back_to_description_when_there_is_no_passage(self):
        """AI-composed and hand-authored rules have no document passage.

        Without a fallback they would all share one empty anchor and match each
        other indiscriminately.
        """
        payload = rule(description="A manually written rule.")
        payload["formulation"] = {}
        assert identify(payload).anchor_tokens == frozenset(
            {"a", "manually", "written", "rule"}
        )

    def test_non_ascii_source_text_produces_tokens(self):
        """An ASCII-only tokeniser would reduce this to an empty set."""
        identity = identify(rule(source_text="يجب تشفير جميع الأجهزة"))
        assert len(identity.anchor_tokens) == 4


class TestJaccard:
    def test_empty_sets_never_match(self):
        assert jaccard(frozenset(), frozenset()) == 0.0
        assert jaccard(frozenset({"a"}), frozenset()) == 0.0

    def test_identical_sets_are_one(self):
        assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0

    def test_partial_overlap(self):
        assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == 1 / 3


class TestDiffRuns:
    def test_first_run_is_all_baseline(self):
        result = diff_runs([("n1", rule()), ("n2", rule(rule_id="AI-2"))], [])
        assert {m.delta_status for m in result.matches.values()} == {"baseline"}
        assert result.removed_keys == []
        assert result.has_changes is False

    def test_identical_rerun_reports_no_changes(self):
        """The headline case: re-extracting an unchanged document.

        Nothing should reach the reviewer, but the run must still be recorded.
        """
        rules = [("a", rule(rule_id="AI-1")), ("b", rule(rule_id="AI-2", source_text="Second clause text here."))]
        rerun = [("x", rule(rule_id="AI-9")), ("y", rule(rule_id="AI-8", source_text="Second clause text here."))]
        result = diff_runs(rerun, rules)
        assert result.counts["unchanged"] == 2
        assert result.has_changes is False

    def test_reworded_identical_rule_is_unchanged(self):
        baseline = [("a", rule())]
        rerun = [("x", rule(title="Full-disk encryption mandatory", description="Rephrased entirely."))]
        result = diff_runs(rerun, baseline)
        match = result.matches["x"]
        assert match.delta_status == "unchanged"
        assert match.reworded is True
        assert result.has_changes is False

    def test_same_passage_different_semantics_is_changed(self):
        """Same source text, different answer: the extractor changed its mind."""
        baseline = [("a", rule(effect="deny"))]
        rerun = [("x", rule(effect="allow"))]
        result = diff_runs(rerun, baseline)
        assert result.matches["x"].delta_status == "changed"
        assert result.matches["x"].baseline_key == "a"
        assert result.matches["x"].similarity == 1.0
        assert result.has_changes is True

    def test_revised_passage_is_changed_not_new(self):
        baseline = [("a", rule(source_text="Every device must carry full-disk encryption before issue."))]
        rerun = [
            (
                "x",
                rule(
                    source_text="Every device must carry full-disk encryption before issue to staff.",
                    effect="allow",
                ),
            )
        ]
        result = diff_runs(rerun, baseline)
        assert result.matches["x"].delta_status == "changed"
        assert result.matches["x"].baseline_key == "a"
        assert result.removed_keys == []

    def test_unrelated_rule_is_new_and_leaves_baseline_removed(self):
        baseline = [("a", rule(source_text="Every device must carry full-disk encryption before issue."))]
        rerun = [("x", rule(source_text="Annual leave accrues at two point five days each month."))]
        result = diff_runs(rerun, baseline)
        assert result.matches["x"].delta_status == "new"
        assert result.removed_keys == ["a"]
        assert result.has_changes is True

    def test_removed_rule_alone_counts_as_a_change(self):
        """A rule the previous run found and this one did not is a change.

        It produces no new row, so nothing else in the system would notice it.
        """
        baseline = [
            ("a", rule(rule_id="AI-1")),
            ("b", rule(rule_id="AI-2", source_text="A clause that vanished in the new variant.")),
        ]
        rerun = [("x", rule(rule_id="AI-9"))]
        result = diff_runs(rerun, baseline)
        assert result.counts["unchanged"] == 1
        assert result.removed_keys == ["b"]
        assert result.has_changes is True

    def test_baseline_rule_is_claimed_only_once(self):
        """Two new rules must not both point at one baseline rule.

        If they could, the second would be reported as an edit of a rule already
        accounted for and the removed set would under-report.
        """
        baseline = [("a", rule())]
        rerun = [("x", rule()), ("y", rule())]
        result = diff_runs(rerun, baseline)
        statuses = sorted(m.delta_status for m in result.matches.values())
        assert statuses == ["new", "unchanged"]
        assert result.removed_keys == []

    def test_exact_match_is_never_stolen_by_a_fuzzy_one(self):
        """Tier ordering: an identical rule wins its baseline before a near match.

        Processed rule-by-rule instead of tier-by-tier, the near-identical `x`
        could claim `a` first and force the exact match `y` to report as new.
        """
        baseline = [("a", rule(source_text="Every device must carry full-disk encryption before issue."))]
        rerun = [
            ("x", rule(source_text="Every device must carry full-disk encryption before issue now.", effect="allow")),
            ("y", rule(source_text="Every device must carry full-disk encryption before issue.")),
        ]
        result = diff_runs(rerun, baseline)
        assert result.matches["y"].delta_status == "unchanged"
        assert result.matches["y"].baseline_key == "a"
        assert result.matches["x"].delta_status == "new"

    def test_below_threshold_similarity_does_not_match(self):
        baseline = [("a", rule(source_text="alpha beta gamma delta epsilon zeta"))]
        rerun = [("x", rule(source_text="alpha beta omega sigma tau upsilon", effect="allow"))]
        result = diff_runs(rerun, baseline)
        assert jaccard(
            identify(rule(source_text="alpha beta gamma delta epsilon zeta")).anchor_tokens,
            identify(rule(source_text="alpha beta omega sigma tau upsilon")).anchor_tokens,
        ) < SIMILARITY_THRESHOLD
        assert result.matches["x"].delta_status == "new"

    def test_result_is_deterministic_regardless_of_input_order(self):
        baseline = [
            ("a", rule(rule_id="AI-1", source_text="First clause about encryption of devices.")),
            ("b", rule(rule_id="AI-2", source_text="Second clause about annual leave accrual.")),
        ]
        rerun = [
            ("x", rule(rule_id="AI-7", source_text="First clause about encryption of devices.")),
            ("y", rule(rule_id="AI-8", source_text="Second clause about annual leave accrual.")),
        ]
        first = diff_runs(rerun, baseline)
        second = diff_runs(list(reversed(rerun)), baseline)
        assert first.matches["x"].baseline_key == second.matches["x"].baseline_key
        assert first.matches["y"].baseline_key == second.matches["y"].baseline_key

    def test_counts_cover_every_rule(self):
        baseline = [("a", rule()), ("b", rule(rule_id="AI-2", source_text="Vanished clause text."))]
        rerun = [
            ("x", rule()),
            ("y", rule(rule_id="AI-3", source_text="Brand new unrelated clause about parking permits.")),
        ]
        result = diff_runs(rerun, baseline)
        counts = result.counts
        assert counts["unchanged"] + counts["changed"] + counts["new"] + counts["baseline"] == len(rerun)
        assert counts["removed"] == 1
