"""The skip ledger counts declined passages, not rejection events.

The ledger answers "what did this run decline about my document", and a reviewer
reads its length as a count. It was appended to once per rejection, so a passage
the model returned twice — the same sentence emitted as two canonical policies,
both non-normative — was declined once and recorded twice. Every number built on
it inherited that overstatement.

Measured before the fix, across four runs on two documents: 44 entries for 39
distinct passages. All five repeats were the same passage, same kind, same
reason. None was a passage declined for two different reasons.

The distinction these tests exist to hold is that both shapes are real and they
are not the same:

  - the same passage rejected twice for one reason is one decline, recorded once
  - the same passage declined for two different reasons is two facts, kept apart

and identity is a source reference rather than the text, because a document may
state the same sentence in two places and those are two passages.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.extraction.formulation_mapping import (
    SKIP_BATCH_UNREAD,
    SKIP_DISCARDED,
    SKIP_NOT_EXTRACTED,
    _skip_identity,
    record_skip,
    skip_breaks_coverage,
    skip_counts,
)


class _Source:
    def __init__(self, clause_ref: str | None) -> None:
        self.clause_ref = clause_ref
        self.end_clause_ref = None


class _Passage:
    """The shape `_passage_matches_for_policy` reads: `.text` and `.source`."""

    def __init__(self, text: str, clause_ref: str | None = None) -> None:
        self.text = text
        self.source = _Source(clause_ref)


# Two passages a bilingual handbook might genuinely carry. The second is the
# real duplicated item measured on the GMU run, truncated the way the ledger
# truncates it for display.
_ALPHA = "Employees shall submit the annual leave request fourteen days in advance."
_BETA = "Gulf Medical University is committed to recruiting and retaining qualified staff."


def _ledger_of(*entries: tuple[str, str, str, str | None]) -> list[dict]:
    ledger: list[dict] = []
    for item, reason, kind, identity in entries:
        record_skip(ledger, item=item, reason=reason, kind=kind, identity=identity)
    return ledger


class TestOnePassageDeclinedTwiceIsOneEntry:
    def test_same_passage_same_reason_merges(self) -> None:
        ledger = _ledger_of(
            (_BETA, "rule_type 'non_normative' carries no policy rule", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "rule_type 'non_normative' carries no policy rule", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
        )
        assert len(ledger) == 1

    def test_the_event_count_is_kept_not_discarded(self) -> None:
        # Merging must not hide that the model emitted it twice. That is a fact
        # about the run worth diagnosing, it is simply not a fact about the
        # document, so it travels on the entry rather than in the count.
        ledger = _ledger_of(
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
        )
        assert len(ledger) == 1
        assert ledger[0]["occurrences"] == 3

    def test_first_seen_item_text_is_the_one_kept(self) -> None:
        ledger = _ledger_of(
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            ("a differently truncated rendering", "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
        )
        assert ledger[0]["item"] == _BETA


class TestTwoReasonsAreTwoFacts:
    """The shape that must survive: one passage, two different reasons.

    Measured zero times in the corpus, which is exactly why it needs a test.
    A dedup written against only the observed data would collapse it, and
    nothing in production would have caught that.
    """

    def test_same_passage_different_reason_stays_two_entries(self) -> None:
        ledger = _ledger_of(
            (_ALPHA, "canonical policy carried no rule", SKIP_DISCARDED, "clauses:p2-E7"),
            (_ALPHA, "no platform mapping for rule_type 'advisory'", SKIP_DISCARDED, "clauses:p2-E7"),
        )
        assert len(ledger) == 2
        assert {e["reason"] for e in ledger} == {
            "canonical policy carried no rule",
            "no platform mapping for rule_type 'advisory'",
        }

    def test_same_passage_different_kind_stays_two_entries(self) -> None:
        # Kind decides whether coverage is broken, so merging across it would
        # let an unread batch be absorbed into a read-and-judged entry and
        # disappear from the coverage answer entirely.
        ledger = _ledger_of(
            (_ALPHA, "same words", SKIP_BATCH_UNREAD, "clauses:p2-E7"),
            (_ALPHA, "same words", SKIP_NOT_EXTRACTED, "clauses:p2-E7"),
        )
        assert len(ledger) == 2
        assert [skip_breaks_coverage(e) for e in ledger] == [True, False]


class TestIdentityIsTheSourceNotTheText:
    def test_one_sentence_stated_in_two_places_is_two_passages(self) -> None:
        # A handbook that repeats an obligation under two headings has declined
        # two passages. Text-hash identity would report one and lose a location
        # the reviewer needs. This is the same distinction already made for
        # records, where a document can state one obligation twice.
        ledger = _ledger_of(
            (_ALPHA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p2-E7"),
            (_ALPHA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p9-E31"),
        )
        assert len(ledger) == 2

    def test_different_passages_sharing_a_truncated_prefix_stay_apart(self) -> None:
        # `item` is cut at 200 characters for display and 15 of 44 measured
        # entries sat exactly at that cap, so two different passages can present
        # an identical string. Identity is not read from it.
        shared_prefix = "The University shall provide "
        ledger = _ledger_of(
            (shared_prefix, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p2-E7"),
            (shared_prefix, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p2-E8"),
        )
        assert len(ledger) == 2

    def test_unidentified_entries_never_merge(self) -> None:
        # Not knowing what was skipped must fail towards a count that is too
        # high, never towards a decline that vanishes — the same asymmetry that
        # makes an untagged skip count against coverage.
        ledger = _ledger_of(
            ("something", "reason", SKIP_DISCARDED, None),
            ("something", "reason", SKIP_DISCARDED, None),
        )
        assert len(ledger) == 2

    def test_identity_resolves_from_the_passages_a_skip_site_already_holds(self) -> None:
        passages = [_Passage(_ALPHA, "p2-E7"), _Passage(_BETA, "p4-E12")]
        refs = [["p2-E7"], ["p4-E12"]]
        assert _skip_identity(_ALPHA, passages, refs) == "clauses:p2-E7"
        assert _skip_identity(_BETA, passages, refs) == "clauses:p4-E12"

    def test_unresolvable_identity_is_none_rather_than_a_text_fallback(self) -> None:
        passages = [_Passage(_ALPHA, "p2-E7")]
        refs = [["p2-E7"]]
        assert _skip_identity("a sentence from no passage", passages, refs) is None
        assert _skip_identity(_ALPHA, None, None) is None
        assert _skip_identity(_ALPHA, passages, []) is None


class TestTheCountsReadersSee:
    """The surface inherits correctness from the ledger, so assert it does."""

    def test_coverage_counters_count_passages_not_events(self) -> None:
        ledger = _ledger_of(
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_ALPHA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p2-E7"),
        )
        counts = skip_counts(ledger)
        events = sum(s["occurrences"] for s in ledger)
        assert counts["read_not_extracted"] == 2, "two passages were declined"
        assert events == 4, "four rejections produced them"
        assert counts["read_not_extracted"] != events, (
            "the two numbers must not be interchangeable"
        )

    def test_every_counter_is_in_passages(self) -> None:
        ledger = _ledger_of(
            ("batch-9", "extractor failed", SKIP_BATCH_UNREAD, "batch:batch-9"),
            ("batch-9", "extractor failed", SKIP_BATCH_UNREAD, "batch:batch-9"),
            ("p1-E4", "not verbatim", SKIP_DISCARDED, "clauses:p1-E4"),
            ("p1-E4", "not verbatim", SKIP_DISCARDED, "clauses:p1-E4"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
        )
        assert skip_counts(ledger) == {
            "batches_unread": 1,
            "passages_discarded": 1,
            "read_not_extracted": 1,
        }
        assert sum(s["occurrences"] for s in ledger) == 6

    def test_the_reviewer_sentence_says_the_number_of_passages(self) -> None:
        ledger = _ledger_of(
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
        )
        read_but_dropped = [s for s in ledger if not skip_breaks_coverage(s)]
        note = (
            f"{len(read_but_dropped)} sentence(s) were read and not extracted; "
            "see the skip list to check that judgement."
        )
        assert note.startswith("1 sentence(s)"), note

    def test_coverage_verdict_is_unchanged_by_merging(self) -> None:
        # Merging must not be able to talk a broken run into looking complete.
        ledger = _ledger_of(
            ("batch-9", "passage extractor failed", SKIP_BATCH_UNREAD, "batch:batch-9"),
            ("batch-9", "passage extractor failed", SKIP_BATCH_UNREAD, "batch:batch-9"),
        )
        assert len(ledger) == 1
        assert [s for s in ledger if skip_breaks_coverage(s)], "coverage still broken"


class TestTheDetectorStillSees:
    """Guards against a fixture that would pass whatever the code did."""

    def test_the_merging_fixtures_actually_contain_repeats(self) -> None:
        # If every fixture used distinct identities, every merge test would pass
        # against a `record_skip` that never merged at all.
        raw = [
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
            (_BETA, "non_normative", SKIP_NOT_EXTRACTED, "clauses:p4-E12"),
        ]
        keys = [(i, r, k) for _, r, k, i in raw]
        assert len(keys) > len(set(keys)), "fixture has no repeat to merge"

    def test_the_preserving_fixtures_actually_share_an_identity(self) -> None:
        # And if the two-reasons fixture used two identities, it would pass
        # against a `record_skip` that merged everything indiscriminately.
        raw = [
            (_ALPHA, "canonical policy carried no rule", SKIP_DISCARDED, "clauses:p2-E7"),
            (_ALPHA, "no platform mapping for rule_type 'advisory'", SKIP_DISCARDED, "clauses:p2-E7"),
        ]
        assert len({i for _, _, _, i in raw}) == 1, "fixture does not share an identity"
        assert len({r for _, r, _, _ in raw}) == 2, "fixture does not differ in reason"

    def test_passage_texts_are_distinct_enough_to_match_separately(self) -> None:
        # `_skip_identity` matches on text similarity. If the two fixture
        # passages were near-identical they could resolve to the same passage
        # and the identity tests would pass for the wrong reason.
        assert _ALPHA != _BETA
        passages = [_Passage(_ALPHA, "p2-E7"), _Passage(_BETA, "p4-E12")]
        refs = [["p2-E7"], ["p4-E12"]]
        assert _skip_identity(_ALPHA, passages, refs) != _skip_identity(_BETA, passages, refs)


@pytest.mark.parametrize(
    "kind", [SKIP_BATCH_UNREAD, SKIP_DISCARDED, SKIP_NOT_EXTRACTED]
)
def test_every_kind_records_the_fields_downstream_reads(kind: str) -> None:
    ledger: list[dict] = []
    record_skip(ledger, item="x", reason="r", kind=kind, identity="clauses:p1-E1")
    entry = ledger[0]
    assert set(entry) >= {"item", "reason", "kind", "identity", "occurrences"}
    assert entry["kind"] == kind
