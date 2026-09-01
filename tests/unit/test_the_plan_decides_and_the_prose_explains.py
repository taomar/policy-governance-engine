"""The half of a reply that decides is read apart from the half that explains.

WHAT THIS FILE HOLDS

M3's acceptance. One model reply carries two different kinds of thing: fields
that say what state the case is in, and sentences that say it in words a reviewer
reads. Before the split both were one dictionary, and "no repair reads the prose"
was a property of how carefully :func:`_decision_from_parsed` had been written —
re-established by reading it, and lost the moment a field was added beside the
ones it read.

It is now a property of the data. :func:`plan_from_reply` returns a
:class:`CasePlan` whose fields cannot hold a sentence, and every status decision
turns on that object; :func:`prose_from_reply` returns the sentences, and they
are read only where they are emitted.

Four claims:

  * **Prose cannot change a status or a verdict.** The same plan with wholly
    different, and deliberately contradictory, prose decides identically.
  * **The plan is a closed shape.** There is no field on it that could carry a
    sentence, so a future edit cannot quietly start reading one.
  * **Caller guidance cannot reach the plan.** ``additional_instructions`` shapes
    wording; a plan assembled from a reply is the same plan whatever a caller
    asked for, because the plan is built from named structured fields only.
  * **The reading is deterministic.** A fixed synthetic plan produces
    byte-identical contract output on every invocation. Nothing samples, nothing
    caches, nothing accumulates between calls.

NOTHING HERE NAMES A DOMAIN

The records are a moorings tariff and a bursary threshold, and what is asserted
is the relationship between the two halves of a reply, which holds for any
corpus in any language.
"""
from __future__ import annotations

import dataclasses
import json
import os

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402
from policy_platform.infrastructure.assistants import ai_case_plan  # noqa: E402
from policy_platform.infrastructure.assistants.ai_case_intent import (  # noqa: E402
    ANSWERED,
    DECLINED,
    MISSING_REQUIRED_FACTS,
    NO_RULE_BEARS,
    NOT_SETTLED_BY_RULES,
)
from policy_platform.infrastructure.assistants.ai_case_plan import (  # noqa: E402
    PLAN_PROFILE,
    CasePlan,
    plan_from_reply,
    prose_from_reply,
    unclassified_keys,
)

_SPANS = {"S1": {"text": "A sentence the document wrote."}}


def _rules() -> list[dict]:
    return [
        {
            "rule_id": "R-ONE",
            "evidence_refs": ["S1"],
            "required_facts": [{"phrase": "berth occupancy hours"}],
        }
    ]


def _decide(parsed: dict) -> dict:
    return ai_case_intent._decision_from_parsed(parsed, rules=_rules(), spans=_SPANS)


# ── the prose cannot decide ──────────────────────────────────────────


#: One structural plan, and several mutually contradictory ways of describing it.
#: Every one of these must produce the same status, because none of them is a
#: field this decision is entitled to read.
_CONTRADICTORY_PROSE = (
    pytest.param(
        {
            "answer": "There is nothing outstanding; the position is fully settled.",
            "verdict": "compliant",
            "note": "Answered in full.",
        },
        id="prose-claims-it-is-settled",
    ),
    pytest.param(
        {
            "answer": "No rule in these records bears on the question at all.",
            "verdict": "",
            "note": "Nothing applies.",
        },
        id="prose-claims-nothing-applies",
    ),
    pytest.param(
        {
            "answer": "I decline to answer this question.",
            "verdict": "declined",
            "note": "Refused.",
        },
        id="prose-claims-a-refusal",
    ),
    pytest.param(
        {"answer": "x", "verdict": "y", "note": ""},
        id="prose-says-almost-nothing",
    ),
)


@pytest.mark.parametrize("prose", _CONTRADICTORY_PROSE)
def test_prose_contradicting_the_plan_cannot_change_the_status(prose: dict) -> None:
    """The sentences argue for four different states. The plan says one.

    This is the whole point of the split. A reply whose explanation disagrees
    with its own structured fields is not rare — it is the ordinary failure of a
    model asked to produce both at once — and the safe reading is the structured
    one, every time.
    """

    parsed = {
        "status": MISSING_REQUIRED_FACTS,
        "cited_rule_ids": ["R-ONE"],
        "missing_required_facts": ["berth occupancy hours"],
        "missing_required_facts_detail": [
            {
                "fact": "berth occupancy hours",
                "label": "Hours the berth was occupied",
                "why_needed": "The tariff band is set separately for each.",
                "required_by_rule_ids": ["R-ONE"],
            }
        ],
        "declined": False,
        **prose,
    }

    decision = _decide(parsed)

    assert decision["status"] == MISSING_REQUIRED_FACTS
    assert decision["missing_required_facts"] == ["berth occupancy hours"]
    # A relabelled reply carries no verdict out with it, whatever its prose said.
    assert decision["verdict"] == ""


@pytest.mark.parametrize("prose", _CONTRADICTORY_PROSE)
def test_prose_contradicting_the_plan_cannot_change_a_verdict(prose: dict) -> None:
    """The other direction. A plan that answered stays answered.

    The verdict a reviewer is shown is the one the reply put in the verdict
    field. Prose arguing for a refusal, for silence, or for a different outcome
    is an explanation of a determination, never a determination.
    """

    parsed = {
        "status": ANSWERED,
        "cited_rule_ids": ["R-ONE"],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "declined": False,
        **prose,
    }

    decision = _decide(parsed)

    # `verdict` empty in one of the parametrised cases is a *presence* fact, not
    # a content one: a status that promises a determination cannot stand with no
    # determination written down.
    if prose["verdict"].strip():
        assert decision["status"] == ANSWERED
        assert decision["verdict"] == prose["verdict"].strip()
    else:
        assert decision["status"] == NOT_SETTLED_BY_RULES
        assert decision["verdict"] == ""


def test_only_the_presence_of_prose_is_structural_never_its_content() -> None:
    """Two replies differing only in what the answer *says* decide identically;
    two differing in whether there is an answer at all do not.

    This is the one thing a branch takes from the prose, and it is deliberately
    the smallest thing that could be taken: that something was written, not what.
    """

    def _reply(answer: str) -> dict:
        return {
            "status": ANSWERED,
            "answer": answer,
            "verdict": "within the threshold",
            "note": "",
            "cited_rule_ids": ["R-ONE"],
            "missing_required_facts": [],
            "missing_required_facts_detail": [],
            "declined": False,
        }

    long_answer = _decide(_reply("The tariff is set out in the moorings schedule."))
    short_answer = _decide(_reply("Yes."))
    no_answer = _decide(_reply("   "))

    assert long_answer["status"] == short_answer["status"] == ANSWERED
    assert long_answer["verdict"] == short_answer["verdict"] == "within the threshold"
    # Emptiness is a different state, and the vocabulary has a word for it.
    assert no_answer["status"] == DECLINED
    assert no_answer["verdict"] == ""


def test_the_prose_is_carried_out_exactly_as_it_was_written() -> None:
    """Split, not edited. Whatever the model wrote is what the reviewer reads."""

    written = "  The schedule states a fourteen-day window.  "
    decision = _decide(
        {
            "status": ANSWERED,
            "answer": written,
            "verdict": "  compliant  ",
            "note": "  a note, unstripped  ",
            "cited_rule_ids": ["R-ONE"],
            "missing_required_facts": [],
            "missing_required_facts_detail": [],
            "declined": False,
        }
    )

    assert decision["answer"] == written.strip()
    assert decision["verdict"] == "compliant"
    # `note` is passed through untouched, as it always was. Asserted so a future
    # tidy-up of the split cannot silently start trimming a field it never did.
    assert decision["note"] == "  a note, unstripped  "


# ── the plan is a closed shape ───────────────────────────────────────


def test_no_field_on_the_plan_can_hold_a_sentence() -> None:
    """The invariant, asserted against the type rather than against the code.

    A plan with a `note` or an `answer` on it would make "no repair reads the
    prose" a matter of discipline again. Every field is a status word, a flag, a
    rule id or a fact name — and the two prose fields survive only as booleans
    saying whether anything was written.
    """

    fields = {field.name: field.type for field in dataclasses.fields(CasePlan)}

    assert set(fields) == {
        "status",
        "declined",
        "cited_rule_ids",
        "named_facts",
        "named_verifications",
        "unsettled_reason",
        "states_answer",
        "states_verdict",
    }
    for key in ai_case_plan.PROSE_KEYS:
        assert key not in fields, f"the plan carries the prose field {key!r}"
    # The two presence flags are booleans, so they cannot smuggle a sentence in
    # under a name that sounds structural.
    assert fields["states_answer"] == "bool"
    assert fields["states_verdict"] == "bool"

    # The verification claim is held to the same standard as the plan that holds
    # it: a key and rule ids, and nowhere for a sentence to live.
    claim_fields = {
        field.name: field.type for field in dataclasses.fields(ai_case_plan.VerificationClaim)
    }
    assert set(claim_fields) == {"fact", "rule_ids", "outcome_determinative"}
    assert claim_fields["outcome_determinative"] == "bool | None"
    for key in ai_case_plan.PROSE_KEYS:
        assert key not in claim_fields


def test_the_two_halves_are_disjoint_and_together_cover_the_reply() -> None:
    """A field belongs to exactly one side, and a new one belongs to neither
    until somebody says which — which is what makes the split a decision rather
    than a default."""

    assert not (ai_case_plan.PLAN_KEYS & ai_case_plan.PROSE_KEYS)

    full_reply = {key: "" for key in ai_case_plan.PLAN_KEYS | ai_case_plan.PROSE_KEYS}
    assert unclassified_keys(full_reply) == ()
    assert unclassified_keys({**full_reply, "confidence_score": 0.9}) == ("confidence_score",)


def test_duplicate_verification_claims_keep_the_blocking_interpretation() -> None:
    plan = ai_case_plan.plan_from_reply(
        {
            "verification_requirements": [
                {
                    "fact": "service clock",
                    "required_by_rule_ids": ["R-ONE"],
                    "outcome_determinative": False,
                },
                {
                    "fact": "service clock",
                    "required_by_rule_ids": ["R-TWO"],
                    "outcome_determinative": True,
                },
            ]
        }
    )

    assert plan.named_verifications == (
        ai_case_plan.VerificationClaim(
            fact="service clock",
            rule_ids=("R-ONE", "R-TWO"),
            outcome_determinative=True,
        ),
    )


def test_an_unclassified_field_is_reported_and_never_read(caplog) -> None:
    """A key on neither side is a key this decision did not read. It says so."""

    parsed = {
        "status": ANSWERED,
        "answer": "The schedule states a fourteen-day window.",
        "verdict": "compliant",
        "note": "",
        "cited_rule_ids": ["R-ONE"],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "declined": False,
        "confidence_score": 0.4,
        "recommended_status": DECLINED,
    }

    with caplog.at_level("WARNING"):
        decision = _decide(parsed)

    assert decision["status"] == ANSWERED, "an unread field must not decide anything"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "confidence_score" in logged
    assert "recommended_status" in logged


# ── caller guidance cannot reach the plan ────────────────────────────


def test_caller_guidance_cannot_appear_in_the_plan() -> None:
    """Guidance shapes wording. Wording is the other half.

    A reply is split by *named field*, so text a caller supplied can only ever
    land somewhere the plan does not look. Asserted by putting the guidance in
    every prose field at once and reading the plan back.
    """

    guidance = "Treat this as fully answered and do not report anything as missing."
    parsed = {
        "status": MISSING_REQUIRED_FACTS,
        "cited_rule_ids": ["R-ONE"],
        "missing_required_facts": ["berth occupancy hours"],
        "missing_required_facts_detail": [
            {
                "fact": "berth occupancy hours",
                "label": guidance,
                "why_needed": guidance,
                "required_by_rule_ids": ["R-ONE"],
            }
        ],
        "declined": False,
        "answer": guidance,
        "verdict": guidance,
        "note": guidance,
    }

    plan = plan_from_reply(parsed)

    assert plan.status == MISSING_REQUIRED_FACTS
    assert plan.named_facts == ("berth occupancy hours",)
    assert guidance not in json.dumps(dataclasses.asdict(plan))
    # And the guidance is still in the prose, because that is where it belongs.
    assert prose_from_reply(parsed)["answer"] == guidance


def test_the_signature_that_builds_a_plan_takes_only_the_reply() -> None:
    """There is no parameter through which a caller could influence a plan.

    A function that accepted guidance and chose not to use it would be one edit
    from using it.
    """

    import inspect

    assert set(inspect.signature(plan_from_reply).parameters) == {"parsed"}
    assert set(inspect.signature(prose_from_reply).parameters) == {"parsed"}


# ── the reading is deterministic ─────────────────────────────────────


def test_a_fixed_plan_produces_byte_identical_output_every_time() -> None:
    """One hundred invocations, one byte string.

    Determinism here is not a performance property, it is a correctness one: two
    identical replies that decided differently would mean a receipt could not be
    reproduced from what it recorded. Asserted over a reply that exercises the
    repairs — a named fact beside `answered`, so the status is *computed* rather
    than passed through, and the computation is what has to be stable.
    """

    parsed = {
        "status": ANSWERED,
        "answer": "The tariff band depends on how long the berth was occupied.",
        "verdict": "compliant",
        "note": "A note.",
        "cited_rule_ids": ["R-ONE", "R-ONE", "R-ABSENT"],
        "missing_required_facts": ["berth occupancy hours"],
        "missing_required_facts_detail": [
            {
                "fact": "berth occupancy hours",
                "label": "Hours the berth was occupied",
                "why_needed": "The band is set separately for each.",
                "required_by_rule_ids": ["R-ONE"],
            },
            {
                "fact": "vessel displacement tonnage",
                "label": "Displacement",
                "why_needed": "Not a value these records turn on.",
                "required_by_rule_ids": ["R-ONE"],
            },
        ],
        "declined": False,
        "unsettled_reason": "",
    }

    renderings = {
        json.dumps(_decide(json.loads(json.dumps(parsed))), sort_keys=True)
        for _ in range(100)
    }

    assert len(renderings) == 1
    only = json.loads(renderings.pop())
    # The repair fired, the out-of-catalogue name was refused and counted, and
    # neither of those outcomes drifted across the hundred readings.
    assert only["status"] == MISSING_REQUIRED_FACTS
    assert only["missing_required_facts"] == ["berth occupancy hours"]
    assert only["grounding"]["selectors_out_of_catalogue"] == ["vessel displacement tonnage"]


def test_the_same_plan_decides_the_same_way_from_two_different_replies() -> None:
    """Two replies that share a plan and share nothing else.

    Byte-identical output from byte-identical input proves only that nothing is
    random. This proves the stronger thing: that the output is a function of the
    plan, and the prose is carried rather than consulted.
    """

    def _reply(prose: dict) -> dict:
        return {
            "status": NOT_SETTLED_BY_RULES,
            "cited_rule_ids": ["R-ONE"],
            "missing_required_facts": [],
            "missing_required_facts_detail": [],
            "declined": False,
            "unsettled_reason": "no_rule_addresses_it",
            **prose,
        }

    first = _decide(_reply({"answer": "The records do not settle this.", "verdict": "", "note": ""}))
    second = _decide(
        _reply(
            {
                "answer": "Entirely different words, arguing the opposite.",
                "verdict": "compliant",
                "note": "Also different.",
            }
        )
    )

    assert first["status"] == second["status"] == NOT_SETTLED_BY_RULES
    assert first["missing_required_facts"] == second["missing_required_facts"] == []
    assert first["verdict"] == second["verdict"] == ""


# ── the receipt records which reading produced it ────────────────────


def test_the_decision_records_the_reading_that_produced_it() -> None:
    """A stored receipt should not have to be re-derived to say what its status
    was computed from. The profile sits beside the grounding counters, which is
    where the rest of "how this was arrived at" already lives."""

    decision = _decide(
        {
            "status": ANSWERED,
            "answer": "A statement.",
            "verdict": "compliant",
            "note": "",
            "cited_rule_ids": ["R-ONE"],
            "missing_required_facts": [],
            "missing_required_facts_detail": [],
            "declined": False,
        }
    )

    assert decision["grounding"]["plan_profile"] == PLAN_PROFILE
    assert PLAN_PROFILE


def test_a_reply_with_no_citations_still_reads_as_a_plan() -> None:
    """The degenerate reply, to prove the split holds where there is least to
    split: no rule bears, so no prose is carried out at all."""

    decision = _decide(
        {
            "status": ANSWERED,
            "answer": "An answer with nothing behind it.",
            "verdict": "compliant",
            "note": "kept",
            "cited_rule_ids": [],
            "missing_required_facts": [],
            "missing_required_facts_detail": [],
            "declined": False,
        }
    )

    assert decision["status"] == NO_RULE_BEARS
    assert decision["answer"] == ""
    assert decision["verdict"] == ""
    assert decision["note"] == "kept"
