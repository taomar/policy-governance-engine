"""A determination can be complete and still not be a licence to act.

WHAT THIS FILE HOLDS

The acceptance for ``verification_requirements``: the additive list of conditions
a caller must confirm before acting on a verdict that *was* reached.

THE DEFECT IT CLOSES

Governance records routinely settle two different questions in the same
paragraph. One is whether something is *conferred* — a status, an allowance, an
entitlement, a class of permission. The other is what must hold before it is
*exercised* — a quantity currently standing, an approval, a sequence, a window.

Before this field existed, the second kind had exactly one place to go, and it
was ``missing_information``. Naming any of them therefore converted an answered
case into a blocked one. A caller who asked "is this conferred?" and whose
records answered it plainly received, instead of the answer, an audit of their
own position — as though the rules had not settled anything.

That is wrong in both directions. It withholds an answer the records give, and
it teaches a reader that a blocked status means "the policy is silent" when it
sometimes meant "the policy answered, and something else has to be checked".

THE FOUR CLAIMS

  * **An entitlement that the retained rules establish is answered**, and the
    conditions on acting ride alongside it without unmaking it.
  * **A question about the act itself still blocks** when something genuinely
    outcome-determinative is unstated. The new field is not an escape hatch from
    the missing-fact discipline; it is a different thing from it.
  * **The same safeguards apply.** A check keyed on a name the records never
    declared is refused and reported, and a rule id naming no retained rule is
    removed — because a caller acts on these too.
  * **A refusal here does not invalidate a verdict grounded separately.** That
    is the one place the two lists deliberately differ: a refused missing fact
    is fatal because the judgement still hangs on it, and nothing hangs on
    these.

NOTHING HERE NAMES A DOMAIN

The records are a berthing tariff and a kennel licence. What is asserted is the
relationship between what a record confers and what it conditions, which holds
for any governance corpus.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.application import policy_case_decision  # noqa: E402
from policy_platform.application.policy_case_decision import (  # noqa: E402
    Caller,
    build_envelope,
)
from policy_platform.contracts.case_decision import (  # noqa: E402
    PolicySetRef,
    VerdictSection,
    compute_decision_hash_v2,
    decision_hash_preimage_v2,
    validate_receipt,
)
from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402
from policy_platform.infrastructure.assistants.ai_case_plan import (  # noqa: E402
    CasePlan,
    VerificationClaim,
)
from policy_platform.infrastructure.assistants.ai_case_intent import (  # noqa: E402
    ANSWERED,
    MISSING_REQUIRED_FACTS,
    NOT_SETTLED_BY_RULES,
)

_SPANS = {"S1": {"text": "A sentence the document wrote."}}


def _rule(rule_id: str = "R-ONE", *, required: list[dict] | None = None) -> dict:
    rule: dict = {"rule_id": rule_id, "evidence_refs": ["S1"]}
    if required is not None:
        rule["required_facts"] = required
    return rule


def _reply(
    *,
    status: str = ANSWERED,
    verdict: str = "The entitlement is conferred.",
    missing: list[str] | None = None,
    verifications: list[dict] | None = None,
    cited: list[str] | None = None,
) -> dict:
    """One parsed gather reply, in the shape the prompts ask for."""

    named = list(missing or [])
    return {
        "status": status,
        "answer": "The retained records set out the position.",
        "verdict": verdict,
        "cited_rule_ids": list(cited if cited is not None else ["R-ONE"]),
        "missing_required_facts": named,
        "missing_required_facts_detail": [
            {
                "fact": name,
                "label": f"Label for {name}",
                "why_needed": "The outcome is set separately for each.",
                "required_by_rule_ids": ["R-ONE"],
            }
            for name in named
        ],
        "verification_requirements": list(verifications or []),
        "declined": False,
        "note": "",
    }


def _decide(parsed: dict, rules: list[dict]) -> dict:
    return ai_case_intent._decision_from_parsed(parsed, rules=rules, spans=_SPANS)


def _verification(
    fact: str,
    *,
    rule_ids: list[str] | None = None,
    why: str = "",
    outcome_determinative: bool = False,
) -> dict:
    return {
        "fact": fact,
        "label": f"Confirm {fact}",
        "why_needed": why or "Confirm this against the record before acting.",
        "outcome_determinative": outcome_determinative,
        "required_by_rule_ids": list(rule_ids if rule_ids is not None else ["R-ONE"]),
    }


# ── the answer survives the conditions on acting ─────────────────────


def test_a_rate_based_entitlement_returns_a_scoped_verdict_with_checks() -> None:
    """The prompt must not turn a computable entitlement into policy silence."""

    for prompt in (
        ai_case_intent._DECISION_SYSTEM_PROMPT,
        ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
    ):
        assert "rate, formula, schedule or table" in prompt
        assert "calculate it" in prompt
        assert "under the named rule or formula" in prompt
        assert "recorded balance, approval" in prompt
        assert "do not apply that rule" in prompt
        assert "never turn a conditional calculation into an unqualified entitlement" in prompt
        assert "elapsed time" in prompt
        assert "does not by itself say that its term was completed" in prompt
        assert "Do not substitute one clock for another" in prompt
        assert "assignment, possession, employment" in prompt
        assert "entry into service, contract commencement" in prompt
        assert "the missing start event is a" in prompt
        assert '"outcome_determinative"' in prompt
        assert "`not_settled_by_rules` is unavailable" in prompt


class TestAConferredEntitlementIsAnswered:
    """The behaviour this file exists for."""

    def test_a_reached_verdict_carries_its_checks_and_stays_reached(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(verifications=[_verification("berth occupancy hours")]),
            rules,
        )

        assert decision["status"] == ANSWERED
        assert decision["verdict"] == "The entitlement is conferred."
        # The whole point: the conditions did not empty the determination, and
        # they are not sitting in the field that means there isn't one.
        assert decision["missing_required_facts"] == []
        assert decision["missing_information"] == []
        assert [item["fact"] for item in decision["verification_requirements"]] == [
            "berth occupancy hours"
        ]

    def test_an_outcome_determinative_check_is_promoted_to_missing(self) -> None:
        rules = [_rule(required=[{"phrase": "service start date"}])]
        decision = _decide(
            _reply(
                verifications=[
                    _verification(
                        "service start date",
                        outcome_determinative=True,
                    )
                ]
            ),
            rules,
        )

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["verdict"] == ""
        assert decision["missing_required_facts"] == ["service start date"]
        assert decision["missing_information"][0]["label"] == "Confirm service start date"
        assert decision["verification_requirements"] == []
        assert decision["grounding"]["verifications_promoted_to_missing"] == 1

    def test_a_check_with_no_determinative_flag_fails_safe_as_missing(self) -> None:
        rules = [_rule(required=[{"phrase": "service start date"}])]
        check = _verification("service start date")
        check.pop("outcome_determinative")

        decision = _decide(_reply(verifications=[check]), rules)

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["verdict"] == ""
        assert decision["missing_required_facts"] == ["service start date"]
        assert decision["verification_requirements"] == []

    def test_an_outcome_determinative_alias_overrides_an_optional_alias(self) -> None:
        plan = CasePlan(
            status=ANSWERED,
            named_verifications=(
                VerificationClaim(
                    fact="service start date",
                    outcome_determinative=False,
                ),
                VerificationClaim(
                    fact="service entry date",
                    outcome_determinative=True,
                ),
            ),
        )
        parsed = {
            "verification_requirements": [
                _verification("service start date"),
                _verification(
                    "service entry date",
                    outcome_determinative=True,
                ),
            ]
        }
        membership = {
            "declared": True,
            "alias_index": {
                "service-start-date": "service-clock",
                "service-entry-date": "service-clock",
            },
        }

        optional, promoted, optional_refused, promoted_refused = (
            ai_case_intent._reconciled_verification_requirements(
                plan,
                parsed,
                available_ids=set(),
                fact_names={},
                missing_keys=set(),
                membership=membership,
            )
        )

        assert optional == []
        assert [item["fact"] for item in promoted] == ["service-clock"]
        assert optional_refused == []
        assert promoted_refused == []

    def test_each_check_carries_a_key_a_label_a_reason_and_its_rules(self) -> None:
        """The same shape a missing fact carries, so a caller builds one reader."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(
                verifications=[
                    _verification(
                        "berth occupancy hours",
                        why="The quantity standing is held on the account record.",
                    )
                ]
            ),
            rules,
        )

        (item,) = decision["verification_requirements"]
        assert item == {
            "fact": "berth occupancy hours",
            "label": "Confirm berth occupancy hours",
            "why_needed": "The quantity standing is held on the account record.",
            "required_by_rule_ids": ["R-ONE"],
        }

    def test_a_status_with_no_determination_carries_no_checks(self) -> None:
        """A condition on acting on a determination is meaningless where there is
        none. Emitting one beside a blocked case would restore exactly the blur
        the two lists exist to prevent."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        for status in (MISSING_REQUIRED_FACTS, NOT_SETTLED_BY_RULES):
            decision = _decide(
                _reply(
                    status=status,
                    verdict="",
                    missing=["berth occupancy hours"] if status == MISSING_REQUIRED_FACTS else [],
                    verifications=[_verification("berth occupancy hours")],
                ),
                rules,
            )
            assert decision["status"] == status
            assert decision["verification_requirements"] == [], status

    def test_the_key_is_always_present_so_one_reader_serves_every_state(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(_reply(), rules)

        assert decision["verification_requirements"] == []


@pytest.mark.asyncio
async def test_the_gather_and_validator_use_the_same_complete_record_catalogue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Top-level fact declarations advertised to the model remain valid on return."""

    payload = {
        "envelope": {"provision_key": "a-policy"},
        "spans": _SPANS,
        "facts": {
            "canonical-balance": {
                "name": "canonical-balance",
                "source_phrase": "the current recorded balance",
            }
        },
        "rules": [_rule()],
    }
    reply = _reply(
        verifications=[_verification("canonical-balance")]
    )

    async def _reply_once(*_args, **_kwargs):
        return reply

    monkeypatch.setattr(ai_case_intent, "_chat_json", _reply_once)
    decision = await ai_case_intent.answer_decision(
        payload, scenario="Is the entitlement conferred?"
    )

    assert [item["fact"] for item in decision["verification_requirements"]] == [
        "canonical-balance"
    ]
    assert decision["grounding"]["verification_selectors_out_of_catalogue"] == []


@pytest.mark.asyncio
async def test_a_nonempty_complete_record_catalogue_still_refuses_an_invented_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "envelope": {"provision_key": "a-policy"},
        "spans": _SPANS,
        "facts": {"canonical-balance": {"name": "canonical-balance"}},
        "rules": [_rule()],
    }
    reply = _reply(
        verifications=[_verification("invented-selector")]
    )

    async def _reply_once(*_args, **_kwargs):
        return reply

    monkeypatch.setattr(ai_case_intent, "_chat_json", _reply_once)
    decision = await ai_case_intent.answer_decision(
        payload, scenario="Is the entitlement conferred?"
    )

    assert decision["status"] == ANSWERED
    assert decision["verification_requirements"] == []
    assert decision["grounding"]["verification_selectors_out_of_catalogue"] == [
        "invented-selector"
    ]


# ── the missing-fact discipline is not weakened ──────────────────────


class TestAnActionQuestionStillBlocks:
    """The counterweight. Without it, the new field is a way to answer anything."""

    def test_a_reply_that_blocks_still_blocks_and_names_its_facts(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(
                status=MISSING_REQUIRED_FACTS,
                verdict="",
                missing=["berth occupancy hours"],
            ),
            rules,
        )

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["verdict"] == ""
        assert decision["missing_required_facts"] == ["berth occupancy hours"]
        assert decision["verification_requirements"] == []

    def test_a_value_named_in_both_places_keeps_the_blocking_reading(self) -> None:
        """The one-directional preference. A reply that hedges by naming the same
        value as both a blocker and an optional check does not get to have the
        weaker reading — otherwise the hedge is a route around the discipline."""

        rules = [
            _rule(
                required=[
                    {"phrase": "berth occupancy hours"},
                    {"phrase": "vessel length"},
                ]
            )
        ]
        decision = _decide(
            _reply(
                status=MISSING_REQUIRED_FACTS,
                verdict="",
                missing=["berth occupancy hours"],
                verifications=[
                    _verification("berth occupancy hours"),
                    _verification("vessel length"),
                ],
            ),
            rules,
        )

        assert decision["status"] == MISSING_REQUIRED_FACTS
        assert decision["missing_required_facts"] == ["berth occupancy hours"]
        assert decision["verification_requirements"] == []


# ── the same safeguards, because a caller acts on both ───────────────


class TestTheClosedVocabularyIsEnforcedHereToo:
    def test_a_check_named_outside_the_catalogue_is_dropped_and_reported(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(verifications=[_verification("vessel displacement tonnage")]),
            rules,
        )

        assert decision["verification_requirements"] == []
        assert decision["grounding"]["verification_selectors_out_of_catalogue"] == [
            "vessel displacement tonnage"
        ]
        # Reported under its own key, so an auditor can tell an optional check
        # that was refused from a fact the judgement turned on.
        assert decision["grounding"]["selectors_out_of_catalogue"] == []

    def test_a_refused_check_does_not_unmake_a_separately_grounded_verdict(self) -> None:
        """The one place the two lists deliberately differ.

        A refused missing-fact name is fatal because the judgement still hangs on
        something this layer can no longer name. Nothing hangs on these, so the
        determination — grounded on its own citations — stands.
        """

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(verifications=[_verification("vessel displacement tonnage")]),
            rules,
        )

        assert decision["status"] == ANSWERED
        assert decision["verdict"] == "The entitlement is conferred."

    @pytest.mark.parametrize(
        "written",
        [
            "berth occupancy hours",
            "Berth Occupancy Hours",
            "berth_occupancy_hours",
            "BERTH-OCCUPANCY-HOURS",
        ],
    )
    def test_any_spelling_the_records_use_still_resolves(self, written: str) -> None:
        """The control. Without it every assertion above is satisfied by refusing
        everything, which would be a worse product and a passing test file."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(_reply(verifications=[_verification(written)]), rules)

        assert [item["fact"] for item in decision["verification_requirements"]] == [
            "berth occupancy hours"
        ]
        assert decision["grounding"]["verification_selectors_out_of_catalogue"] == []

    def test_two_spellings_of_one_check_are_carried_once(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(
                verifications=[
                    _verification("berth occupancy hours"),
                    _verification("Berth_Occupancy_Hours"),
                ]
            ),
            rules,
        )

        assert [item["fact"] for item in decision["verification_requirements"]] == [
            "berth occupancy hours"
        ]

    def test_records_that_declare_no_vocabulary_refuse_no_check(self) -> None:
        """With nothing declared there is no vocabulary to check against, and
        refusing every name would blame the model for a deficiency in the
        records — the same fallback the missing facts already have."""

        rules = [_rule(required=[])]
        decision = _decide(
            _reply(verifications=[_verification("kennel occupancy count")]),
            rules,
        )

        assert [item["fact"] for item in decision["verification_requirements"]] == [
            "kennel-occupancy-count"
        ]
        assert decision["grounding"]["verification_selectors_out_of_catalogue"] == []


class TestARuleIdIsFilteredToTheRetainedSet:
    def test_an_id_naming_no_retained_rule_is_removed(self) -> None:
        """A check attributed to a rule nobody read is a fabrication under a
        different field name, and it is refused as one."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(
                verifications=[
                    _verification("berth occupancy hours", rule_ids=["R-ONE", "R-INVENTED"])
                ]
            ),
            rules,
        )

        (item,) = decision["verification_requirements"]
        assert item["required_by_rule_ids"] == ["R-ONE"]

    def test_a_check_whose_every_id_is_invented_survives_without_them(self) -> None:
        """The check itself resolved against the catalogue, so it is real; only
        the attribution was not. Dropping the check would lose something a caller
        needs in order to remove an attribution they never had."""

        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        decision = _decide(
            _reply(verifications=[_verification("berth occupancy hours", rule_ids=["R-NOPE"])]),
            rules,
        )

        (item,) = decision["verification_requirements"]
        assert item["fact"] == "berth occupancy hours"
        assert item["required_by_rule_ids"] == []


# ── prose describes; it does not decide ──────────────────────────────


class TestProseCannotChangeTheOutcome:
    """The M3 boundary, asserted where the new field crosses it.

    The identities — which checks, in what order, attributed to which rules —
    come from the plan. The label and the reason come from the prose half, and
    rewording either must move nothing else.
    """

    def test_rewording_a_label_moves_neither_status_nor_verdict_nor_the_keys(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        first = _decide(_reply(verifications=[_verification("berth occupancy hours")]), rules)

        reworded = _reply(verifications=[_verification("berth occupancy hours")])
        reworded["verification_requirements"][0]["label"] = "An entirely different label"
        reworded["verification_requirements"][0]["why_needed"] = "An entirely different reason"
        second = _decide(reworded, rules)

        assert second["status"] == first["status"] == ANSWERED
        assert second["verdict"] == first["verdict"]
        assert [item["fact"] for item in second["verification_requirements"]] == [
            item["fact"] for item in first["verification_requirements"]
        ]
        assert second["verification_requirements"][0]["label"] == "An entirely different label"

    def test_a_description_of_a_check_the_plan_never_named_is_not_carried(self) -> None:
        """Prose can describe; it cannot introduce.

        Asserted against the reconciler directly, because that is the only place
        the two halves are separable: the plan supplies the identities and the
        parsed reply supplies only the words. A describing entry matching no
        named check describes nothing this decision carries, so it is dropped.
        """

        plan = CasePlan(
            status=ANSWERED,
            named_verifications=(
                VerificationClaim(
                    fact="berth occupancy hours",
                    rule_ids=(),
                    outcome_determinative=False,
                ),
            ),
        )
        parsed = {
            "verification_requirements": [
                _verification("berth occupancy hours", rule_ids=[]),
                _verification("vessel length", rule_ids=[]),
            ]
        }
        membership = ai_case_intent._selector_membership(
            [_rule(required=[{"phrase": "berth occupancy hours"}, {"phrase": "vessel length"}])]
        )

        items, promoted, refused, promoted_refused = (
            ai_case_intent._reconciled_verification_requirements(
                plan,
                parsed,
                available_ids=set(),
                fact_names={},
                missing_keys=set(),
                membership=membership,
            )
        )

        assert [item["fact"] for item in items] == ["berth-occupancy-hours"]
        # And it was not refused either: it resolved perfectly well against the
        # catalogue. It simply was not one of the checks the plan claimed.
        assert refused == []
        assert promoted == []
        assert promoted_refused == []

    def test_an_entry_that_is_not_an_object_is_ignored_rather_than_read(self) -> None:
        rules = [_rule(required=[{"phrase": "berth occupancy hours"}])]
        parsed = _reply(verifications=[_verification("berth occupancy hours")])
        parsed["verification_requirements"].append("berth occupancy hours")

        decision = _decide(parsed, rules)
        assert [item["fact"] for item in decision["verification_requirements"]] == [
            "berth occupancy hours"
        ]


# ── the public contract admits the combination ───────────────────────


class TestThePublicSectionAdmitsAQualifiedVerdict:
    def test_a_reached_verdict_may_carry_checks(self) -> None:
        section = VerdictSection(
            status="answered",
            reached=True,
            decision="The entitlement is conferred.",
            verification_requirements=[
                {"fact": "berth-occupancy-hours", "label": "Confirm the hours standing"}
            ],
        )

        assert section.status == "answered"
        assert section.reached is True
        assert section.decision == "The entitlement is conferred."
        assert [item.fact for item in section.verification_requirements] == [
            "berth-occupancy-hours"
        ]

    def test_a_verdict_that_was_not_reached_may_not_carry_checks(self) -> None:
        with pytest.raises(ValueError, match="verification requirements qualify"):
            VerdictSection(
                status="missing_required_facts",
                reached=False,
                decision="",
                missing_information=[{"fact": "berth-occupancy-hours", "label": "Hours"}],
                missing_required_facts=["Hours"],
                verification_requirements=[
                    {"fact": "vessel-length", "label": "Confirm the length"}
                ],
            )

    def test_one_value_may_not_be_both_a_blocker_and_a_check(self) -> None:
        """Not by a third rule, but by the shape of the two already there.

        Missing information belongs only to `missing_required_facts`, which is
        never `reached`; checks belong only to a verdict that is. So the two
        lists can never be populated on the same section, and a value cannot
        appear in both without the section itself being refused first. That is a
        stronger guarantee than a comparison, and this asserts it as the reason
        rather than trusting it as an accident.
        """

        with pytest.raises(ValueError, match="verification requirements qualify"):
            VerdictSection(
                status="missing_required_facts",
                reached=False,
                decision="",
                missing_information=[{"fact": "berth-occupancy-hours", "label": "Hours"}],
                missing_required_facts=["Hours"],
                verification_requirements=[
                    {"fact": "berth-occupancy-hours", "label": "Hours"}
                ],
            )

        # And from the other side: a reached verdict cannot carry the blockers.
        with pytest.raises(ValueError, match="missing information belongs only"):
            VerdictSection(
                status="answered",
                reached=True,
                decision="A determination.",
                missing_information=[{"fact": "berth-occupancy-hours", "label": "Hours"}],
                verification_requirements=[
                    {"fact": "berth-occupancy-hours", "label": "Hours"}
                ],
            )

    def test_the_field_defaults_to_empty_so_an_older_receipt_reads(self) -> None:
        section = VerdictSection(status="answered", reached=True, decision="A determination.")
        assert section.verification_requirements == []


# ── the seal ─────────────────────────────────────────────────────────


_PROJECT = PolicySetRef(id=str(uuid.uuid4()), key="sealed-berthing", name="Sealed Berthing")
_VERSION_ID = str(uuid.uuid4())
_RECEIVED = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
_DECIDED = datetime(2026, 5, 4, 8, 0, 11, tzinfo=timezone.utc)

_CALLER = Caller(
    identity="harbourmaster@example.com",
    role="viewer",
    authentication_source="local-token",
    calling_system_identity="a-bot",
)

_CONTEXT = {
    "version_source": "project_scope",
    "policy_version_id": _VERSION_ID,
    "version_number": 2,
    "effective_from": None,
    "effective_to": None,
    "index_name": "policy-cases-sealed",
    "index_version_id": _VERSION_ID,
    "retrieval_method": "hybrid_vector_topk",
}


def _sealed_envelope(verifications: list[dict] | None = None):
    """A receipt of a reached verdict, optionally carrying checks before acting."""

    decision: dict = {
        "status": "answered",
        "verdict": "entitled",
        "answer": "The vessel is entitled to a berth under the tariff.",
        "missing_required_facts": [],
        "missing_information": [],
        "citations": [
            {
                "rule_id": "AI-berth-1",
                "source": {"state": "quoted", "text": "A registered vessel may berth.", "page": 1},
                "policy": {
                    "provision_id": None,
                    "provision_key": "berth",
                    "heading_path": ["1. Berthing"],
                },
            }
        ],
        "note": "",
        "grounding": {"prompt_version": ai_case_intent.PROMPT_VERSION, "rules_cited": 1},
    }
    if verifications is not None:
        decision["verification_requirements"] = verifications

    return build_envelope(
        decision_id=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
        idempotency_key=None,
        project=_PROJECT,
        caller=_CALLER,
        scenario="Is this vessel entitled to a berth?",
        reasoning_effort="medium",
        requested_provision_id=None,
        received_at=_RECEIVED,
        decided_at=_DECIDED,
        latency_ms=11_000,
        response={
            "scope": "project",
            "policy_set_key": _PROJECT.key,
            "retrieval": {
                "status": "narrowed",
                "method": "hybrid_vector_topk",
                "policy_budget": 5,
                "policy_scan": 40,
                "policies_retrieved": 1,
                "policies_considered": 1,
                "policies_retained": 1,
                "policies_discarded": 0,
                "policies_untestable": 0,
            },
            "considered": [
                {
                    "provision_id": None,
                    "provision_key": "berth",
                    "heading_path": ["1. Berthing"],
                    "rules": 1,
                    "retained": True,
                    "best_rank": 0,
                    "best_score": 0.9,
                }
            ],
            "excluded": [],
            "evaluation": {
                "intent": "decision",
                "information_requested": False,
                "verdict_requested": True,
                "classification_reasoning": "asks whether an entitlement exists",
                "classifier_version": "ai-case-needs-v1",
                "informational": None,
                "decision": decision,
                "reasoning_effort": "medium",
            },
            "size": {"combined_chars": 900, "budget_chars": 200000, "oversize": False},
        },
        context=dict(_CONTEXT),
        additional_instructions="",
        provision_ids={"berth": str(uuid.uuid4())},
    )


_A_CHECK = {
    "fact": "mooring-fee-settled",
    "label": "Confirm the mooring fee is settled",
    "why_needed": "The tariff conditions taking the berth on a settled account.",
    "required_by_rule_ids": ["AI-berth-1"],
}


class TestTheReceiptSealsTheChecks:
    """A caller acts on these, so they are evidence, and evidence is sealed."""

    def test_a_public_receipt_carries_the_checks_it_was_decided_with(self) -> None:
        envelope = _sealed_envelope([_A_CHECK])

        assert envelope.verdict is not None
        assert [item.fact for item in envelope.verdict.verification_requirements] == [
            "mooring-fee-settled"
        ]
        assert envelope.verdict.verification_requirements[0].required_by_rule_ids == [
            "AI-berth-1"
        ]
        # And the verdict itself is untouched by their presence.
        assert envelope.verdict.status == "answered"
        assert envelope.verdict.reached is True
        assert envelope.verdict.decision == "entitled"

        # It survives the round trip a caller actually performs.
        served = validate_receipt(envelope.model_dump(mode="json"))
        assert served.verdict is not None
        assert [item.fact for item in served.verdict.verification_requirements] == [
            "mooring-fee-settled"
        ]

    def test_the_checks_are_inside_the_seal(self) -> None:
        """Named in the preimage, not merely carried beside it."""

        preimage = decision_hash_preimage_v2(_sealed_envelope([_A_CHECK]))
        assert preimage["verdict"]["verification_requirements"] == [_A_CHECK]

    def test_changing_a_check_changes_the_hash(self) -> None:
        """Otherwise a condition on acting could be added, reworded or dropped
        after the fact and the receipt would still look like the one that was
        issued — which is the one thing a seal exists to prevent."""

        baseline = _sealed_envelope([_A_CHECK]).decision_hash

        added = _sealed_envelope(
            [_A_CHECK, {"fact": "berth-occupancy-hours", "label": "Confirm the hours"}]
        )
        assert added.decision_hash != baseline

        reworded = _sealed_envelope([{**_A_CHECK, "label": "Check the account is clear"}])
        assert reworded.decision_hash != baseline

        rekeyed = _sealed_envelope([{**_A_CHECK, "fact": "berth-occupancy-hours"}])
        assert rekeyed.decision_hash != baseline

        dropped = _sealed_envelope([])
        assert dropped.decision_hash != baseline

    def test_a_receipt_written_before_the_field_existed_still_verifies(self) -> None:
        """The entry is written only when there is something to seal.

        So a stored receipt that predates the field — and one that simply
        carries no checks, which is the same decision — produces the preimage it
        was sealed under. Adding the field may not reach backwards and
        invalidate hashes already written.
        """

        older = _sealed_envelope(None)
        assert older.verdict is not None
        assert older.verdict.verification_requirements == []

        preimage = decision_hash_preimage_v2(older)
        assert "verification_requirements" not in preimage["verdict"]

        # An empty list is the same decision as no list, and seals identically.
        assert _sealed_envelope([]).decision_hash == older.decision_hash

        # And it still verifies as stored, read back through the public reader.
        stored = older.model_dump(mode="json")
        stored["verdict"].pop("verification_requirements", None)
        assert "verification_requirements" not in stored["verdict"]
        replayed = validate_receipt(stored)
        assert replayed.verdict is not None
        assert replayed.verdict.verification_requirements == []
        assert compute_decision_hash_v2(replayed) == older.decision_hash


class TestTheReaderIsOwedTheseInTheirLanguage:
    """The words cross the rendering boundary; the keys and rule ids do not."""

    def _evaluation(self) -> dict:
        return {
            "classification_reasoning": "asks whether an entitlement exists",
            "informational": None,
            "decision": {
                "status": "answered",
                "verdict": "entitled",
                "answer": "The vessel is entitled to a berth.",
                "note": "",
                "missing_information": [],
                "verification_requirements": [
                    {
                        "fact": "mooring-fee-settled",
                        "label": "Confirm the mooring fee is settled",
                        "why_needed": "The tariff conditions taking the berth on it.",
                        "required_by_rule_ids": ["AI-berth-1"],
                    }
                ],
            },
        }

    def test_the_label_and_the_reason_are_offered_for_rendering(self) -> None:
        fields = policy_case_decision.prose_for_rendering(self._evaluation())

        assert fields[policy_case_decision.PROSE_VERIFICATION_LABEL.format(index=0)] == (
            "Confirm the mooring fee is settled"
        )
        assert fields[policy_case_decision.PROSE_VERIFICATION_WHY_NEEDED.format(index=0)] == (
            "The tariff conditions taking the berth on it."
        )

    def test_the_key_and_its_rule_ids_are_never_shown_to_the_renderer(self) -> None:
        """A translated selector key is a key a follow-up form cannot use, and a
        translated rule id names no rule at all."""

        fields = policy_case_decision.prose_for_rendering(self._evaluation())

        for value in fields.values():
            assert "mooring-fee-settled" not in value
            assert "AI-berth-1" not in value

    def test_rendering_replaces_the_words_and_nothing_else(self) -> None:
        response = {"evaluation": self._evaluation(), "size": {"combined_chars": 1}}

        rendered = policy_case_decision._with_rendered_prose(
            response,
            {
                policy_case_decision.PROSE_VERIFICATION_LABEL.format(index=0): "Une autre phrase",
                policy_case_decision.PROSE_VERIFICATION_WHY_NEEDED.format(index=0): "Une raison",
            },
        )

        item = rendered["evaluation"]["decision"]["verification_requirements"][0]
        assert item["label"] == "Une autre phrase"
        assert item["why_needed"] == "Une raison"
        # The identity, the rules and the verdict are exactly what they were.
        assert item["fact"] == "mooring-fee-settled"
        assert item["required_by_rule_ids"] == ["AI-berth-1"]
        assert rendered["evaluation"]["decision"]["status"] == "answered"
        assert rendered["evaluation"]["decision"]["verdict"] == "entitled"
