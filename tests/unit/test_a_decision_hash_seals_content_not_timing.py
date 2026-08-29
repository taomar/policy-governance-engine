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

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5433/test")

from policy_platform.application.policy_case_decision import (  # noqa: E402
    Caller,
    build_envelope,
)
from policy_platform.contracts.case_decision import (  # noqa: E402
    DECISION_HASH_INCLUDES,
    HASH_BASIS,
    CaseDecisionEnvelope,
    PolicySetRef,
    additional_instructions_hash,
    compute_decision_hash,
    decision_hash_preimage,
    request_hash,
    scenario_hash,
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


def _response(*, verdict: str = "not compliant", status: str = "answered") -> dict:
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
        "evaluation": {
            "intent": "decision",
            "classification_reasoning": "supplies facts and asks for a ruling",
            "informational": None,
            "decision": {
                "status": status,
                "verdict": verdict,
                "answer": "Approval was required first.",
                "missing_required_facts": [],
                "citations": [
                    {
                        "rule_id": "AI-alpha-1",
                        "source": {"state": "quoted", "text": "Approval is required.", "page": 3},
                        "policy": {"provision_id": None, "provision_key": "alpha", "heading_path": ["1. Alpha"]},
                    }
                ],
                "note": "",
                "grounding": {"prompt_version": "ai-case-intent-v4", "rules_cited": 1},
            },
            "reasoning_effort": "medium",
        },
        "size": {"combined_chars": 1200, "budget_chars": 200000, "oversize": False},
    }


def _envelope(**overrides) -> CaseDecisionEnvelope:
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

    Without this, `DECISION_HASH_INCLUDES` becomes a comment that used to be
    true — and the one thing a documented preimage must not be is out of date,
    because a caller verifying a receipt independently reads that list.
    """

    preimage = decision_hash_preimage(_envelope())
    assert tuple(sorted(preimage)) == tuple(sorted(DECISION_HASH_INCLUDES))


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
    assert compute_decision_hash(envelope) == envelope.decision_hash
    assert envelope.hash_basis == HASH_BASIS


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

    assert declined.decision_status == "declined"
    assert declined.decision.verdict == ""
    assert declined.decision_hash != baseline.decision_hash


def test_a_different_question_is_a_different_seal() -> None:
    """The scenario reaches the hash through its digest, not its prose — so the
    seal covers the question without the preimage carrying the text."""

    baseline = _envelope()
    other = _envelope(scenario="An entirely different question.")

    assert other.decision_hash != baseline.decision_hash
    assert decision_hash_preimage(other)["scenario_hash"] == scenario_hash(
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
    assert decision_hash_preimage(guided)["additional_instructions_hash"] == (
        additional_instructions_hash("Lead with the strictest rule.")
    )
    # The preimage carries the digest, never the caller's prose.
    assert "Lead with the strictest rule." not in str(decision_hash_preimage(guided))


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
