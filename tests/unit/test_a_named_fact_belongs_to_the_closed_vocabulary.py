"""A named fact belongs to the vocabulary the records declare, or it is not named.

WHAT THIS FILE HOLDS

M1 built :func:`selector_catalogue` and deliberately did not enforce it, so that
``missing_information[].fact`` would not change before a stage existed that was
entitled to change it. This is that enforcement, and this file is its acceptance.

The defect it closes is RC-4. A blocked receipt says *which value is outstanding*,
and that name is the one part of the receipt a caller acts on: they go and fetch
the thing it names. A name the model composed for the occasion reads exactly like
one the policy declared, so a caller cannot tell "the policy turns on this" from
"a model called it this", and two runs of the same question can name the same
outstanding value differently.

Four claims:

  * **A name the records never declared is dropped, and the drop is reported.**
    A check that is only ever performed and never seen to refuse anything is a
    validator that could not fail -- the same standard `fabricated_citations`
    is held to.
  * **Any spelling the records do use still resolves.** Enforcement must narrow
    what may be named, not what may be *written*. A catalogue that only accepted
    its own preferred spelling would refuse the model for using the document's
    words.
  * **An undeclared corpus enforces nothing.** With no vocabulary to check
    against, refusing every name would blame the model for a deficiency in the
    records.
  * **Dropping never buys an answer.** This is the sharp edge: enforcement
    removes facts, and removing facts is exactly how a blocked case used to
    become an answered one. A reply that named outstanding values and had all of
    them refused must not be reported as a determination.

NOTHING HERE NAMES A DOMAIN

The records are a berthing tariff, a kennel licence and a procurement threshold.
What is asserted is the relationship between a record's declarations and what may
be named as outstanding, which holds for any governance corpus.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402
from policy_platform.infrastructure.assistants.ai_case_intent import (  # noqa: E402
    ANSWERED,
    DECLINED,
    MISSING_REQUIRED_FACTS,
    SELECTOR_CATALOGUE_VERSION,
)

_SPANS = {"S1": {"text": "A sentence the document wrote."}}


def _rule(*, required=None, attributes=None, facts=None) -> dict:
    rule: dict = {"rule_id": "R-ONE", "evidence_refs": ["S1"]}
    if required is not None:
        rule["required_facts"] = required
    if attributes is not None:
        rule["attributes"] = attributes
    if facts is not None:
        rule["facts"] = facts
    return rule


def _parsed(*, named: list[str], status: str = MISSING_REQUIRED_FACTS) -> dict:
    """A reply that names some outstanding values, in both structured fields."""

    return {
        "status": status,
        "answer": "The records set out the position and a value is outstanding.",
        "verdict": "A determination." if status == ANSWERED else "",
        "cited_rule_ids": ["R-ONE"],
        "missing_required_facts": list(named),
        "missing_required_facts_detail": [
            {
                "fact": name,
                "label": f"Label for {name}",
                "why_needed": "The outcome is set separately for each.",
                "required_by_rule_ids": ["R-ONE"],
            }
            for name in named
        ],
        "declined": False,
        "note": "",
    }


def _decide(parsed: dict, rules: list[dict]) -> dict:
    return ai_case_intent._decision_from_parsed(parsed, rules=rules, spans=_SPANS)


class TestAnUndeclaredNameIsRefused:
    def test_a_fact_the_records_never_declared_is_dropped_and_reported(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(_parsed(named=["vessel displacement tonnage"]), rules)

        assert "vessel displacement tonnage" not in decision["missing_required_facts"]
        assert decision["missing_required_facts"] == []
        assert decision["missing_information"] == []
        assert decision["grounding"]["selectors_out_of_catalogue"] == [
            "vessel displacement tonnage"
        ]

    def test_the_valid_names_survive_beside_the_refused_one(self) -> None:
        """A partial refusal is not an excuse to discard the rest."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _parsed(named=["berth occupancy hours", "vessel displacement tonnage"]),
            rules,
        )

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["missing_required_facts"] == ["berth occupancy hours"]
        assert decision["grounding"]["selectors_out_of_catalogue"] == [
            "vessel displacement tonnage"
        ]

    def test_the_refusal_is_reported_under_a_named_version(self) -> None:
        """A list of refused strings nobody can re-derive is not auditable."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(_parsed(named=["berth occupancy hours"]), rules)

        assert decision["grounding"]["selector_catalogue_version"] == SELECTOR_CATALOGUE_VERSION


class TestADeclaredNameStillResolves:
    """The control. Without it every assertion above is satisfied by refusing
    everything, which would be a worse product and a passing test file."""

    @pytest.mark.parametrize(
        "written",
        ["berth occupancy hours", "Berth Occupancy Hours", "berth_occupancy_hours",
         "BERTH-OCCUPANCY-HOURS", "berth  occupancy   hours"],
    )
    def test_any_spelling_of_a_declared_fact_is_accepted(self, written: str) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(_parsed(named=[written]), rules)

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["missing_required_facts"] == ["berth occupancy hours"]
        assert decision["grounding"]["selectors_out_of_catalogue"] == []

    def test_a_fact_declared_only_through_an_attribute_is_still_a_member(self) -> None:
        """The catalogue is closed, not narrow: every structural slot a record
        declares through is a way in."""

        rules = [
            _rule(
                required=[{"phrase": "berth occupancy hours"}],
                attributes={"applies": [{"attribute": "vessel-length"}]},
            )
        ]
        decision = _decide(_parsed(named=["vessel-length"]), rules)

        assert decision["grounding"]["selectors_out_of_catalogue"] == []
        assert decision["missing_required_facts"] == ["vessel-length"]


class TestAnUndeclaredCorpusEnforcesNothing:
    def test_records_that_declare_no_vocabulary_refuse_no_name(self) -> None:
        """Refusing every name against an empty catalogue would blame the model
        for a deficiency in the records. The same distinction the projection gate
        draws between a check that failed and one that could not be made."""

        rules = [_rule(required=[])]
        decision = _decide(_parsed(named=["kennel occupancy count"]), rules)

        assert decision["status"] == MISSING_REQUIRED_FACTS
        # Emitted under its derived key rather than the raw spelling, because with
        # nothing declared there is no record-supplied name to prefer. That is the
        # pre-existing naming rule and enforcement does not touch it -- what
        # matters here is that the name was not *refused*.
        assert decision["missing_required_facts"] == ["kennel-occupancy-count"]
        assert decision["grounding"]["selectors_out_of_catalogue"] == []


class TestDroppingNeverBuysAnAnswer:
    """The sharp edge of enforcement, and the reason this file exists.

    Removing facts is precisely how a blocked case used to become an answered
    one. A check that removes facts therefore has to be built so it cannot become
    a new route to the same defect.
    """

    def test_an_answered_reply_whose_every_named_fact_is_refused_is_not_answered(
        self,
    ) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _parsed(named=["vessel displacement tonnage"], status=ANSWERED), rules
        )

        assert decision["status"] == DECLINED
        assert decision["verdict"] == "", "a refused vocabulary must not carry a verdict out"
        assert decision["grounding"]["selectors_out_of_catalogue"] == [
            "vessel displacement tonnage"
        ]

    def test_a_blocked_reply_whose_every_named_fact_is_refused_is_not_answered(
        self,
    ) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(_parsed(named=["vessel displacement tonnage"]), rules)

        assert decision["status"] == DECLINED
        assert decision["verdict"] == ""

    def test_an_answered_reply_naming_a_declared_fact_is_still_relabelled_blocked(
        self,
    ) -> None:
        """The pre-existing repair still fires. Enforcement narrowed which names
        reach it; it must not have disabled it."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _parsed(named=["berth occupancy hours"], status=ANSWERED), rules
        )

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["verdict"] == ""

    def test_an_answer_that_names_nothing_outstanding_is_untouched(self) -> None:
        """Control: enforcement does not reach a reply with no facts to refuse."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        parsed = _parsed(named=[], status=ANSWERED)
        decision = _decide(parsed, rules)

        assert decision["status"] == ANSWERED
        assert decision["verdict"] == "A determination."
        assert decision["grounding"]["selectors_out_of_catalogue"] == []


class TestTheRuleHoldsInAnyDomain:
    @pytest.mark.parametrize(
        ("declared", "invented"),
        [
            ("berth occupancy hours", "vessel displacement tonnage"),
            ("kennel occupancy count", "veterinary licence expiry"),
            ("order value", "supplier incorporation date"),
            ("qeltrub vashnori", "mirethal quandor"),
        ],
    )
    def test_the_same_separation_holds_across_unrelated_vocabularies(
        self, declared: str, invented: str
    ) -> None:
        """Including one written in vocabulary that means nothing in any language,
        so a rule that recognised subjects rather than structure has nothing to
        recognise."""

        rules = [_rule(required=[{"phrase": declared}])]

        accepted = _decide(_parsed(named=[declared]), rules)
        refused = _decide(_parsed(named=[invented]), rules)

        assert accepted["missing_required_facts"] == [declared]
        assert accepted["grounding"]["selectors_out_of_catalogue"] == []
        assert refused["missing_required_facts"] == []
        assert refused["grounding"]["selectors_out_of_catalogue"] == [invented]


class TestTheMappingIsDeterministic:
    """The assertion the no-caching decision made load-bearing (AD-5).

    Reuse was rejected, so nothing guarantees that asking the same question twice
    produces the same receipt — the model is sampled and may word itself
    differently each time. What *can* be guaranteed, and is the whole of what
    replaces reuse, is that the step from a settled structured reply to the
    contract output invents nothing and varies in nothing: given identical parsed
    input, the emitted decision is byte-identical every time.

    Without this, a difference between two receipts could originate anywhere.
    With it, any difference is attributable to the model's reply and to nothing
    downstream of it, which is what makes the measured stability floors in the
    live suite mean anything at all.
    """

    @staticmethod
    def _fingerprint(decision: dict) -> str:
        return json.dumps(decision, sort_keys=True, ensure_ascii=False, default=str)

    def test_a_fixed_reply_maps_to_a_byte_identical_decision_a_hundred_times(
        self,
    ) -> None:
        rules = [
            _rule(
                required=[{"phrase": "berth occupancy hours"}, {"name": "vessel-length"}],
                attributes={"applies": [{"attribute": "tariff-band"}]},
            )
        ]
        parsed = _parsed(named=["berth occupancy hours", "vessel-length"])

        first = self._fingerprint(_decide(parsed, rules))
        for _ in range(99):
            assert self._fingerprint(_decide(parsed, rules)) == first

    def test_a_reply_carrying_a_refusal_is_equally_deterministic(self) -> None:
        """The refusal path allocates and orders too, so it is pinned as well —
        a counter that varied in order would move a receipt's contents without
        anything about the decision having changed."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        parsed = _parsed(
            named=["vessel displacement tonnage", "berth occupancy hours", "quay crane hours"]
        )

        first = self._fingerprint(_decide(parsed, rules))
        for _ in range(99):
            assert self._fingerprint(_decide(parsed, rules)) == first

    def test_the_refusal_list_keeps_the_order_the_reply_used(self) -> None:
        """Deterministic and *meaningful*: the refused names come back in the
        order the model named them, not in whatever order a set iterated."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _parsed(named=["zulu absent fact", "alpha absent fact", "berth occupancy hours"]),
            rules,
        )

        assert decision["grounding"]["selectors_out_of_catalogue"] == [
            "zulu absent fact",
            "alpha absent fact",
        ]
