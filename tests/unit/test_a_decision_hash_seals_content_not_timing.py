"""`decision_hash` seals what was decided, not when or how fast.

WHAT THE HASH IS AND IS NOT

It is **not** a determinism claim. The same case put twice to the same version
may legitimately produce different prose, because a language model is in the
path; a hash that changed between two such calls would be reporting nothing
useful, and one that stayed the same would be lying about what it covers.

It is an **integrity seal**: given a receipt, the hash proves that its
decision-defining content is the content that was written. That makes the
preimage the entire specification, so these tests hold it directly rather than
asserting a literal digest — a frozen digest would break on any refactor and
tell nobody what actually changed.

TWO TRACKS, ONE SEAL

`case_decision_v2` answers a case as two independent halves — what the policies
state, and what the case comes to — so both are sealed, along with the two
booleans saying which was asked for. What is *not* sealed is the classifier's
prose reasoning: it explains a routing choice rather than being part of what was
decided, and a hash that moved when a prompt was reworded would obscure the
changes an auditor actually cares about.

THE TWO HALVES

A seal is worth exactly the pair of properties below, and either alone is
worthless:

  * things that are not the decision must not disturb it — timestamps, latency,
    the receipt URL, the decision and correlation ids, the caller. A hash that
    moves when the clock moves cannot be compared across two reads of the same
    receipt.
  * the decision must disturb it — a different verdict, status, explanation or
    citation is a different decision. A hash that survives a changed verdict
    seals nothing at all.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5433/test")

from policy_platform.application.policy_case_decision import (  # noqa: E402
    Caller,
    build_envelope,
)
from policy_platform.contracts.case_decision import (  # noqa: E402
    DECISION_HASH_V2_INCLUDES,
    HASH_BASIS_V2,
    HASH_BASIS_V2_WITH_VERIFICATION,
    CaseDecisionEnvelope,
    CaseDecisionEnvelopeV2,
    InformationSection,
    PolicySetRef,
    VerdictSection,
    additional_instructions_hash,
    compute_decision_hash_v2,
    decision_hash_preimage_v2,
    request_hash,
    scenario_hash,
    validate_receipt,
)

_PROJECT = PolicySetRef(id=str(uuid.uuid4()), key="sealed-project", name="Sealed Project")
_VERSION_ID = str(uuid.uuid4())
_RECEIVED = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
_DECIDED = datetime(2026, 3, 1, 9, 0, 13, tzinfo=timezone.utc)

_CALLER = Caller(
    identity="caller@example.com",
    role="viewer",
    authentication_source="local-token",
    calling_system_identity="a-bot",
)

_CONTEXT = {
    "version_source": "project_scope",
    "policy_version_id": _VERSION_ID,
    "version_number": 4,
    "effective_from": None,
    "effective_to": None,
    "index_name": "policy-cases-sealed",
    "index_version_id": _VERSION_ID,
    "retrieval_method": "hybrid_vector_topk",
}


def _response(
    *,
    verdict: str = "not compliant",
    status: str = "answered",
    information: dict | None = None,
    verdict_requested: bool = True,
) -> dict:
    evaluation: dict = {
        "intent": "decision" if verdict_requested else "informational",
        "information_requested": information is not None,
        "verdict_requested": verdict_requested,
        "classification_reasoning": "supplies facts and asks for a ruling",
        "classifier_version": "ai-case-needs-v1",
        "informational": information,
        "decision": (
            {
                "status": status,
                "verdict": verdict,
                "answer": "Approval was required first.",
                "missing_required_facts": [],
                "missing_information": [],
                "citations": [
                    {
                        "rule_id": "AI-alpha-1",
                        "source": {"state": "quoted", "text": "Approval is required.", "page": 3},
                        "policy": {"provision_id": None, "provision_key": "alpha", "heading_path": ["1. Alpha"]},
                    }
                ],
                "note": "",
                "grounding": {"prompt_version": "ai-case-intent-v4", "rules_cited": 1},
            }
            if verdict_requested
            else None
        ),
        "reasoning_effort": "medium",
    }
    return {
        "scope": "project",
        "policy_set_key": _PROJECT.key,
        "retrieval": {
            "status": "narrowed",
            "method": "hybrid_vector_topk",
            "policy_budget": 5,
            "policy_scan": 40,
            "policies_retrieved": 2,
            "policies_considered": 2,
            "policies_retained": 1,
            "policies_discarded": 1,
            "policies_untestable": 0,
        },
        "considered": [
            {
                "provision_id": None,
                "provision_key": "alpha",
                "heading_path": ["1. Alpha"],
                "rules": 2,
                "retained": True,
                "best_rank": 0,
                "best_score": 0.9,
            },
            {
                "provision_id": None,
                "provision_key": "beta",
                "heading_path": ["2. Beta"],
                "rules": 1,
                "retained": False,
                "best_rank": None,
                "best_score": None,
                "discard_reason": "no_retrieval_match",
            },
        ],
        "excluded": [],
        "evaluation": evaluation,
        "size": {"combined_chars": 1200, "budget_chars": 200000, "oversize": False},
    }


def _informational_branch(*, answer: str = "The policy sets a written-approval step.") -> dict:
    """A populated information track, for the mixed and information-only cases."""

    return {
        "status": "answered",
        "answer": answer,
        "citations": [
            {
                "rule_id": "AI-alpha-1",
                "source": {"state": "quoted", "text": "Approval is required.", "page": 3},
                "policy": {"provision_id": None, "provision_key": "alpha", "heading_path": ["1. Alpha"]},
            }
        ],
        "note": "",
        "grounding": {"prompt_version": "ai-case-intent-v4", "rules_cited": 1},
    }


def _envelope(**overrides) -> CaseDecisionEnvelopeV2:
    kwargs = {
        "decision_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "idempotency_key": None,
        "project": _PROJECT,
        "caller": _CALLER,
        "scenario": "I paid before asking. Was that allowed?",
        "reasoning_effort": "medium",
        "requested_provision_id": None,
        "received_at": _RECEIVED,
        "decided_at": _DECIDED,
        "latency_ms": 13_000,
        "response": _response(),
        "context": dict(_CONTEXT),
        "additional_instructions": "",
        "provision_ids": {"alpha": str(uuid.uuid4()), "beta": str(uuid.uuid4())},
    }
    kwargs.update(overrides)
    return build_envelope(**kwargs)


# ── what the seal covers ─────────────────────────────────────────────


def test_the_preimage_is_exactly_the_documented_field_set() -> None:
    """The rule is stated in the contract; this is it, checked.

    Without this, `DECISION_HASH_V2_INCLUDES` becomes a comment that used to be
    true — and the one thing a documented preimage must not be is out of date,
    because a caller verifying a receipt independently reads that list.
    """

    preimage = decision_hash_preimage_v2(_envelope())
    assert tuple(sorted(preimage)) == tuple(sorted(DECISION_HASH_V2_INCLUDES))


def test_the_seal_is_indifferent_to_when_and_how_long(_=None) -> None:
    """Timestamps and latency are facts about the call, not about the decision.

    A hash that moved with them could not be compared between the POST's copy
    and the receipt read a month later, which is the only comparison anyone
    actually performs.
    """

    baseline = _envelope()
    later = _envelope(
        received_at=_RECEIVED + timedelta(days=30),
        decided_at=_DECIDED + timedelta(days=30),
        latency_ms=42,
    )

    assert later.decision_hash == baseline.decision_hash
    assert later.decided_at != baseline.decided_at


def test_stage_latency_is_visible_but_not_part_of_the_seal() -> None:
    baseline = _envelope()
    observed = _envelope(
        context={
            **_CONTEXT,
            "timings_ms": {
                "embedding": 1414,
                "policy_search": 1604,
                "gather_wall": 18_500,
            },
        }
    )

    assert observed.trace.stage_latency_ms == {
        "embedding": 1414,
        "policy_search": 1604,
        "gather_wall": 18_500,
    }
    assert observed.decision_hash == baseline.decision_hash


def test_the_seal_is_indifferent_to_record_identity_and_the_url() -> None:
    """Two receipts of the same decided content seal identically.

    The decision id, the correlation id, the idempotency key and the receipt URL
    name the *call*. Folding them in would make every hash unique by
    construction, which is a fingerprint of the row rather than a seal on the
    decision.
    """

    baseline = _envelope()
    other_call = _envelope(
        decision_id=str(uuid.uuid4()),
        correlation_id="a-different-correlation",
        idempotency_key="a-key",
    )

    assert other_call.decision_hash == baseline.decision_hash
    assert other_call.decision_id != baseline.decision_id
    assert other_call.receipt_url != baseline.receipt_url


def test_the_seal_is_indifferent_to_who_asked() -> None:
    """The caller is recorded, and does not change what the policies decided."""

    baseline = _envelope()
    other_caller = _envelope(
        caller=Caller(
            identity="someone-else@example.com",
            role="admin",
            authentication_source="token",
            calling_system_identity="another-bot",
        )
    )

    assert other_caller.decision_hash == baseline.decision_hash


def test_the_hash_excludes_itself_and_is_reproducible_from_the_envelope() -> None:
    """A receipt can be re-verified from its own returned body.

    Recomputing over the completed envelope — hash field and all — must give the
    same value, which is only true if the hash is outside its own preimage.
    """

    envelope = _envelope()
    assert compute_decision_hash_v2(envelope) == envelope.decision_hash
    assert envelope.hash_basis == HASH_BASIS_V2_WITH_VERIFICATION


# ── what the seal must notice ────────────────────────────────────────


def test_a_different_verdict_is_a_different_seal() -> None:
    """The property the whole mechanism exists for.

    A seal that survives a changed verdict is not evidence of anything.
    """

    baseline = _envelope()
    flipped = _envelope(response=_response(verdict="compliant"))

    assert flipped.decision_hash != baseline.decision_hash


def test_a_different_status_is_a_different_seal() -> None:
    """`declined` and `answered` are different decisions even when the prose is
    identical — and the receipt strips the verdict for the first, so the content
    genuinely differs."""

    baseline = _envelope()
    declined = _envelope(response=_response(status="declined"))

    assert declined.outcome.verdict == "declined"
    assert declined.verdict.reached is False
    assert declined.verdict.decision == ""
    assert declined.decision_hash != baseline.decision_hash


def test_the_two_asked_booleans_are_sealed() -> None:
    """A receipt that could be re-labelled after the fact seals nothing useful.

    "You only asked for information" is exactly the sentence a missing verdict
    would be explained away with, so what the classifier read the question as
    asking for is part of what was decided — even though the reasoning behind it
    is not.
    """

    verdict_only = _envelope()
    mixed = _envelope(response=_response(information=_informational_branch()))

    assert verdict_only.asked.information_requested is False
    assert mixed.asked.information_requested is True
    assert mixed.decision_hash != verdict_only.decision_hash

    preimage = decision_hash_preimage_v2(mixed)
    assert preimage["asked"] == {"information_requested": True, "verdict_requested": True}


def test_the_classification_reasoning_is_not_sealed() -> None:
    """Prose explaining a routing choice is not part of what was decided.

    Sealing it would move the hash whenever a classifier reworded itself — a
    change no auditor could act on, and one that would drown out the changes
    they could.
    """

    baseline = _envelope()
    response = _response()
    response["evaluation"]["classification_reasoning"] = "an entirely different explanation"
    reworded = _envelope(response=response)

    assert reworded.asked.classification_reasoning != baseline.asked.classification_reasoning
    assert reworded.decision_hash == baseline.decision_hash
    assert "an entirely different explanation" not in str(decision_hash_preimage_v2(reworded))


def test_a_different_information_answer_is_a_different_seal() -> None:
    """Both tracks are decision-defining, not just the one that carries a verdict.

    A receipt whose *statement* of what the policies hold could be altered
    without breaking the seal would be no evidence at all for the half of the
    question that asked for it.
    """

    baseline = _envelope(response=_response(information=_informational_branch()))
    changed = _envelope(
        response=_response(information=_informational_branch(answer="Something else entirely."))
    )

    assert changed.decision_hash != baseline.decision_hash


def test_a_citation_serving_both_tracks_is_sealed_as_serving_both() -> None:
    """Which track rested on a rule is part of the account of what rested on what.

    The merged list carries one entry per rule; a rule cited by both tracks says
    so, and a seal that ignored the tags would treat "the verdict rested on this"
    and "both halves rested on this" as the same receipt.
    """

    verdict_only = _envelope()
    mixed = _envelope(response=_response(information=_informational_branch()))

    (shared,) = mixed.citations
    assert sorted(shared.serves) == ["information", "verdict"]
    assert [c.serves for c in verdict_only.citations] == [["verdict"]]

    preimage = decision_hash_preimage_v2(mixed)
    assert preimage["citations"][0]["serves"] == ["information", "verdict"]
    assert mixed.decision_hash != verdict_only.decision_hash


def test_a_different_question_is_a_different_seal() -> None:
    """The scenario reaches the hash through its digest, not its prose — so the
    seal covers the question without the preimage carrying the text."""

    baseline = _envelope()
    other = _envelope(scenario="An entirely different question.")

    assert other.decision_hash != baseline.decision_hash
    assert decision_hash_preimage_v2(other)["scenario_hash"] == scenario_hash(
        "An entirely different question."
    )


def test_different_caller_guidance_is_a_different_seal() -> None:
    """Guidance cannot change what was decided, and is still part of the request.

    A receipt whose record of what the caller asked for could be edited without
    breaking the seal would be weaker evidence than one whose could not — so the
    guidance is covered, by digest, exactly as the scenario is.
    """

    baseline = _envelope()
    guided = _envelope(additional_instructions="Lead with the strictest rule.")

    assert guided.decision_hash != baseline.decision_hash
    assert decision_hash_preimage_v2(guided)["additional_instructions_hash"] == (
        additional_instructions_hash("Lead with the strictest rule.")
    )
    # The preimage carries the digest, never the caller's prose.
    assert "Lead with the strictest rule." not in str(decision_hash_preimage_v2(guided))


def test_a_different_citation_is_a_different_seal() -> None:
    """Which rules a decision rested on is part of the decision.

    Two identical verdicts resting on different rules are not the same decision,
    and an auditor comparing them needs the hash to say so.
    """

    response = _response()
    response["evaluation"]["decision"]["citations"][0]["rule_id"] = "AI-alpha-9"
    changed = _envelope(response=response)

    assert changed.decision_hash != _envelope().decision_hash


def test_a_different_version_is_a_different_seal() -> None:
    """The same answer under a different published version is a different fact."""

    baseline = _envelope()
    other_version = _envelope(context={**_CONTEXT, "version_number": 5})

    assert other_version.decision_hash != baseline.decision_hash


def test_a_different_retained_set_is_a_different_seal() -> None:
    """Narrowing is part of the decision: which policies were carried in, and
    which were set aside, is exactly what a reviewer challenges first."""

    response = _response()
    response["considered"][1]["retained"] = True
    changed = _envelope(response=response)

    assert changed.decision_hash != _envelope().decision_hash


# ── the request hash, which is a different hash for a different job ──


# ── the invariant the envelope enforces rather than documents ────────


def test_a_verdict_section_refuses_a_decision_it_did_not_reach() -> None:
    """The one confusion this vocabulary exists to prevent, made unrepresentable.

    "Not compliant" is a *reached* verdict and belongs in `decision`. A case that
    could not be decided carries no decision at all. If both could be expressed
    the same way, a client rendering `decision` would eventually present "we
    could not decide" as a refusal, or the reverse — and there is no worse
    failure available to a governance product.
    """

    reached = VerdictSection(status="answered", reached=True, decision="not compliant")
    assert reached.decision == "not compliant"

    blocked = VerdictSection(status="missing_required_facts", reached=False, decision="")
    assert blocked.decision == ""

    with pytest.raises(ValidationError):
        VerdictSection(status="answered", reached=True, decision="")

    with pytest.raises(ValidationError):
        VerdictSection(status="missing_required_facts", reached=False, decision="not compliant")

    with pytest.raises(ValidationError):
        VerdictSection(status="answered", reached=False, decision="")


def test_an_information_section_refuses_an_answer_it_did_not_give() -> None:
    """The same guard on the other track.

    `answered` and a non-empty `answer` are two views of one fact, and a section
    carrying one without the other would let a client show an empty string as a
    statement of what the policies hold.
    """

    answered = InformationSection(status="answered", answered=True, answer="the cap is 30 hours")
    assert answered.answered is True

    with pytest.raises(ValidationError):
        InformationSection(status="answered", answered=True, answer="")

    with pytest.raises(ValidationError):
        InformationSection(status="no_rule_bears", answered=False, answer="something")


def test_an_outcome_may_not_disagree_with_the_section_beside_it() -> None:
    """Two views of one fact, checked against each other.

    Without this the envelope could report `outcome.verdict: "answered"` and
    carry no verdict, which is precisely the class of contradiction the two-track
    shape was introduced to make impossible.
    """

    envelope = _envelope()
    payload = envelope.model_dump(mode="json")

    # Claiming an outcome for a section that is not there.
    contradictory = {**payload, "verdict": None}
    with pytest.raises(ValidationError):
        CaseDecisionEnvelopeV2.model_validate(contradictory)

    # Carrying a section for a track reported as never asked for.
    mislabelled = {**payload, "outcome": {"information": "not_requested", "verdict": "not_requested"}}
    with pytest.raises(ValidationError):
        CaseDecisionEnvelopeV2.model_validate(mislabelled)

    # An outcome that names a different status than the section it summarises.
    disagreeing = {**payload, "outcome": {**payload["outcome"], "verdict": "declined"}}
    with pytest.raises(ValidationError):
        CaseDecisionEnvelopeV2.model_validate(disagreeing)


def test_a_stored_receipt_is_read_back_as_the_version_that_wrote_it() -> None:
    """The stored `schema_version` decides, which is why it is stored.

    A v1 receipt re-read as v2 would have to acquire two booleans nobody
    classified for it. A discriminated union makes that a validation error rather
    than a silent coercion into the wrong shape.
    """

    v2 = _envelope()
    replayed = validate_receipt(v2.model_dump(mode="json"))
    assert isinstance(replayed, CaseDecisionEnvelopeV2)
    assert replayed.decision_hash == v2.decision_hash

    legacy = {
        "schema_version": "case_decision_v1",
        "decision_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "policy_set": _PROJECT.model_dump(mode="json"),
        "caller": {
            "principal_identity": "caller@example.com",
            "principal_role": "viewer",
            "authentication_source": "local-token",
            "channel": "api",
        },
        "request": {
            "scenario": "a question asked before the redesign",
            "scenario_hash": scenario_hash("a question asked before the redesign"),
            "scope": "project",
            "reasoning_effort_requested": "medium",
            "received_at": _RECEIVED.isoformat(),
        },
        "decision_status": "answered",
        "retrieval": {"status": "narrowed"},
        "decision": {"status": "answered", "verdict": "not compliant"},
        "trace": {},
        "decision_hash": "a-hash-written-under-v1",
        "hash_basis": "case_decision_v1",
        "receipt_url": "/api/policy-decisions/whatever",
        "decided_at": _DECIDED.isoformat(),
        "latency_ms": 9000,
    }
    older = validate_receipt(legacy)
    assert isinstance(older, CaseDecisionEnvelope)
    assert older.decision_status == "answered"
    assert older.decision.verdict == "not compliant"

    # A tag neither envelope claims is refused rather than coerced into one.
    with pytest.raises(ValidationError):
        validate_receipt({**legacy, "schema_version": "case_decision_v9"})


# ── the request hash, which is a different hash for a different job ──


def test_the_request_hash_ignores_correlation_but_not_the_question() -> None:
    """Idempotency binds a key to a *request*, and a correlation id is not one.

    A caller retrying under a new correlation id is retrying the same request
    and must be replayed the original receipt — telling them their body changed
    would be both wrong and impossible to act on.
    """

    base = request_hash(
        policy_set_key="p", scenario="the question", provision_id=None, reasoning_effort="medium"
    )

    assert base == request_hash(
        policy_set_key="p", scenario="the question", provision_id=None, reasoning_effort="medium"
    )
    assert base != request_hash(
        policy_set_key="p", scenario="another question", provision_id=None, reasoning_effort="medium"
    )
    assert base != request_hash(
        policy_set_key="p", scenario="the question", provision_id="abc", reasoning_effort="medium"
    )
    assert base != request_hash(
        policy_set_key="p", scenario="the question", provision_id=None, reasoning_effort="high"
    )
    assert base != request_hash(
        policy_set_key="other", scenario="the question", provision_id=None, reasoning_effort="medium"
    )
    assert base != request_hash(
        policy_set_key="p",
        scenario="the question",
        provision_id=None,
        reasoning_effort="medium",
        additional_instructions="be brief",
    )
