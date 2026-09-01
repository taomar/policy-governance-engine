"""P0: the telemetry blind spots this service used to have, and the ones it may
never close.

Three separate properties are checked here, and they are not the same property.

1. **A blind spot that was closed.** The index-existence probe is a live round
   trip to the search service that nothing was timing, sitting in the gap
   between `scope_load` and `projection_readiness`. It now has a key.

2. **A blind spot that must stay open, honestly.** Building the envelope,
   sealing it and writing it all finish *after* the object that would have to
   report them, and the stored row is that object's own dump. Those durations
   are emitted beside the receipt and must never appear inside it — a receipt
   that carried them would be one the database does not have.

3. **A route that was measuring and discarding.** Policy JSON already computed
   a stage map and threw it away at the application boundary. It now reports it,
   additively, under the same schema version.

The refusal cases matter more than the happy ones. A timing that vanishes when
the thing it measures fails is worse than no timing, because the absence reads
as "this did not happen" rather than "this failed after N ms".
"""
from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from policy_platform.application import policy_case_decision
from policy_platform.contracts.case_decision import (
    TraceRef,
    decision_hash_preimage_v2,
)
from policy_platform.contracts.policy_retrieval import PolicyRetrievalEnvelope
from policy_platform.infrastructure.ai.usage_metering import (
    collect_token_usage,
    record_call_usage,
)
from policy_platform.infrastructure.assistants import ai_case_project
from tests.fixtures.language_boundary import install_language_boundary

# Reused rather than rebuilt: the seal is only meaningfully tested against the
# same envelope the suite that owns the seal already builds. A second, private
# fixture here could drift from it and quietly stop testing the real shape.
from tests.unit.test_a_decision_hash_seals_content_not_timing import (  # noqa: E402
    _CONTEXT,
    _envelope,
)

pytestmark = pytest.mark.anyio


class _PolicySet:
    id = "11111111-1111-4111-8111-111111111111"
    key = "published-policy"
    name = "Published policy"


def _retrieval_response(**overrides: Any) -> dict:
    response = {
        "scope": "project",
        "policy_set_key": _PolicySet.key,
        "retrieval": {
            "status": "narrowed",
            "method": ai_case_project.LIGHT_RETRIEVAL_METHOD,
            "policies_considered": 2,
            "policies_retained": 1,
            "policies_discarded": 1,
            "projection_profile": "policy-english-projection-v1",
            "projection_ready": True,
        },
        "considered": [],
        "excluded": [],
        "evaluation": None,
        "size": {
            "combined_chars": 321,
            "budget_chars": ai_case_project.PAYLOAD_BUDGET_CHARS,
            "oversize": False,
        },
        "policies": [],
    }
    response.update(overrides)
    return response


def _install_retrieval(monkeypatch, *, timings: dict[str, int] | None) -> None:
    """Stand in for the scope helper, returning the context it really returns."""

    async def _retrieve(session, *, policy_set, scenario, with_context):
        context: dict[str, Any] = {
            "policy_version_id": "33333333-3333-4333-8333-333333333333",
            "version_number": 4,
        }
        if timings is not None:
            context["timings_ms"] = dict(timings)
        return ai_case_project.ProjectPolicyRetrieval(
            response=_retrieval_response(), context=context
        )

    monkeypatch.setattr(ai_case_project, "retrieve_project_policies", _retrieve)
    monkeypatch.setattr(
        policy_case_decision,
        "get_settings",
        lambda: SimpleNamespace(ai_enabled=True),
    )


# ── 1. the probe that nothing was timing ─────────────────────────────


async def test_the_index_existence_probe_is_measured_like_the_call_it_is() -> None:
    """`index_exists` is a network call, and was being counted as free.

    It opens its own connection and asks the search service a question over
    HTTPS, exactly as the readiness gate below it does — and the readiness gate
    was measured while this one was not. The gap it sat in was the largest
    unattributed span in the request.
    """

    timings: dict[str, int] = {}
    context = {"timings_ms": timings}

    probed: list[str] = []

    class _Client:
        def __init__(self, settings: Any) -> None:
            self._settings = settings

        async def index_exists(self, name: str) -> bool:
            probed.append(name)
            await asyncio.sleep(0.03)
            return False

    await _run_scope_until_index_probe(context, _Client)

    assert probed, "the probe under test never ran"
    assert "index_probe" in timings, "the index-existence round trip is unmeasured"
    assert timings["index_probe"] >= 25, timings
    assert isinstance(timings["index_probe"], int)


async def test_a_probe_that_fails_still_reports_the_time_it_spent_failing() -> None:
    """The refusal path, which is the one the key exists for.

    A search service that hangs and then errors has cost the caller the whole
    wait. If the key were only written on success, that request would be
    reported as having spent no time in the probe at all — which is the exact
    reading the instrumentation was added to prevent.
    """

    timings: dict[str, int] = {}
    context = {"timings_ms": timings}

    class _Client:
        def __init__(self, settings: Any) -> None:
            self._settings = settings

        async def index_exists(self, name: str) -> bool:
            await asyncio.sleep(0.03)
            raise RuntimeError("the search service refused the probe")

    response = await _run_scope_until_index_probe(context, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    assert "index_probe" in timings, "a failed probe reported no duration at all"
    assert timings["index_probe"] >= 25, timings


async def test_the_probe_is_silent_when_no_one_asked_for_timings() -> None:
    """The `None`-guard around the recording, and only that.

    Timings are opt-in through the context. A caller that passed no context has
    no map to write into, so the recording must check before it writes —
    without the guard this path raises a `TypeError`, which the retrieval
    handler would then report as a failed search rather than as the honest
    "this index has not been built yet".
    """

    class _Client:
        def __init__(self, settings: Any) -> None:
            self._settings = settings

        async def index_exists(self, name: str) -> bool:
            return False

    # No context at all: the helper must not fail, and nothing is recorded.
    response = await _run_scope_until_index_probe(None, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_NOT_BUILT


async def test_the_probe_key_is_absent_when_there_was_no_probe_to_make() -> None:
    """Absent means it did not happen, and that has to stay true here too.

    The client is constructed before the clock starts, so a client that cannot
    be constructed produces no `index_probe` key at all — not a zero, and not a
    duration that is really the constructor's. That is the honest reading of an
    absent key, and it is the reason the construction sits outside the span.
    """

    timings: dict[str, int] = {}
    context = {"timings_ms": timings}

    class _Client:
        def __init__(self, settings: Any) -> None:
            raise RuntimeError("the search client could not be constructed")

    response = await _run_scope_until_index_probe(context, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    assert "index_probe" not in timings


async def _run_scope_until_index_probe(context: dict | None, client_cls) -> dict:
    """Drive `_answer_project_scope` far enough to reach the probe.

    The scope load is replaced so the test needs no database; everything from
    the probe onwards is the real code path.
    """

    import policy_platform.infrastructure.assistants.ai_case_project as module

    original_scope = module.load_project_scope
    original_client = module.AzureSearchClient
    original_settings = module.get_settings
    try:

        async def _scope(session, policy_set_id):
            return {
                "candidates": [
                    {
                        "provision_key": "leave",
                        "provision_id": "22222222-2222-4222-8222-222222222222",
                        "heading_path": ["Leave"],
                        "rules": [],
                        "search_document_id": "doc-leave",
                        "payload": {"rules": []},
                    }
                ],
                "excluded": [],
                "active_version_id": "33333333-3333-4333-8333-333333333333",
                "active_version_number": 4,
                "has_published_version": True,
            }

        module.load_project_scope = _scope
        module.AzureSearchClient = client_cls
        module.get_settings = lambda: SimpleNamespace(
            search_enabled=True,
            ai_enabled=True,
            azure_openai_deployment="test-deployment",
        )
        return await module._answer_project_scope(
            object(),
            policy_set=_PolicySet(),
            scenario="a question",
            reasoning_effort="medium",
            context=context,
        )
    finally:
        module.load_project_scope = original_scope
        module.AzureSearchClient = original_client
        module.get_settings = original_settings


# ── 2. the durations the receipt cannot carry ────────────────────────


def test_finalisation_timings_are_disjoint_from_receipt_timings() -> None:
    """The invariant that keeps returned and stored receipts the same object.

    Every key in the finalisation map names a duration that ends after the
    envelope has been built and sealed. If one of them ever became a
    `stage_latency_ms` key, the only way to populate it would be to write the
    row and then change the envelope — and the caller would be holding a receipt
    the database does not have.

    The receipt vocabulary below is a written-down list, so it will not notice a
    *new* stage key being added upstream. It is not the primary guard for that:
    `test_the_receipt_carries_no_duration_that_ends_after_it_was_stored` in the
    receipt suite asserts the same disjointness against a real receipt from a
    real request. This one catches the cheaper mistake — a finalisation key
    being named after a stage that already exists.
    """

    receipt_keys = {
        "scope_load",
        "index_probe",
        "index_state_probe",
        "projection_readiness",
        "embedding",
        "policy_search",
        "rule_discovery",
        "retrieval_discovery_wall",
        "policy_selection",
        "retained_rule_ranking",
        "rule_slice_and_fit",
        "classifier",
        "information_gather",
        "verdict_gather",
        "gather_wall",
        "gather_total",
        "reservation",
        "language_in",
        "language_out",
        "decider_wall",
        "policy_link_lookup",
        "to_envelope",
    }

    assert set(policy_case_decision.FINALISATION_TELEMETRY_KEYS).isdisjoint(receipt_keys)


def test_the_finalisation_line_is_emitted_for_a_receipt_that_was_stored(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=policy_case_decision.__name__):
        policy_case_decision._log_finalisation(
            decision_id="decision-1",
            correlation_id="corr-1",
            stage_latency_ms={"to_envelope": 32330},
            finalisation_ms={"envelope_build": 3, "receipt_finalize": 41, "request_total": 32374},
            stored=True,
        )

    payload = _only_finalisation_payload(caplog)
    assert payload["stored"] is True
    assert payload["decision_id"] == "decision-1"
    assert payload["correlation_id"] == "corr-1"
    assert payload["stage_latency_ms"] == {"to_envelope": 32330}
    assert payload["finalisation_ms"] == {
        "envelope_build": 3,
        "receipt_finalize": 41,
        "request_total": 32374,
    }


def test_the_finalisation_line_is_emitted_for_a_receipt_that_could_not_be_stored(
    caplog,
) -> None:
    """The refusal path.

    A write that failed still spent the time it took to fail, and that run is
    the one an operator most needs the number for. A line that appeared only on
    success would leave the worst case invisible.
    """

    with caplog.at_level(logging.INFO, logger=policy_case_decision.__name__):
        policy_case_decision._log_finalisation(
            decision_id="decision-2",
            correlation_id="corr-2",
            stage_latency_ms=None,
            finalisation_ms={"envelope_build": 2, "receipt_finalize": 9001, "request_total": 9100},
            stored=False,
        )

    payload = _only_finalisation_payload(caplog)
    assert payload["stored"] is False
    assert payload["stage_latency_ms"] == {}
    assert payload["finalisation_ms"]["receipt_finalize"] == 9001


def test_the_finalisation_line_reports_only_durations_it_knows(caplog) -> None:
    """The control on the other side: an unexpected key is not passed through.

    The map is a fixed vocabulary of durations. Letting an arbitrary key ride
    along would make the line a second, undocumented telemetry channel that no
    reader could rely on.
    """

    with caplog.at_level(logging.INFO, logger=policy_case_decision.__name__):
        policy_case_decision._log_finalisation(
            decision_id="decision-3",
            correlation_id="corr-3",
            stage_latency_ms={},
            finalisation_ms={"receipt_finalize": 7, "something_invented": 999},
            stored=True,
        )

    payload = _only_finalisation_payload(caplog)
    assert payload["finalisation_ms"] == {"receipt_finalize": 7}


def test_the_finalisation_line_refuses_a_value_that_is_not_a_duration(caplog) -> None:
    """Everything in a timing record is milliseconds, or it is not reported.

    A size, a count or a flag sitting in a map a reader is told to treat as
    durations is worse than a missing key: it is a number that will be plotted
    on a time axis. `True` is the sharp case, because `bool` is an `int` in
    Python and would otherwise serialise happily as a duration of 1 ms.
    """

    with caplog.at_level(logging.INFO, logger=policy_case_decision.__name__):
        policy_case_decision._log_finalisation(
            decision_id="decision-4",
            correlation_id="corr-4",
            stage_latency_ms={
                "verdict_gather": 17340,
                "policies_retained": True,
                "retrieval_score": 0.91,
                "index_name": "policy-index",
            },
            finalisation_ms={"receipt_finalize": 7},
            stored=True,
        )

    payload = _only_finalisation_payload(caplog)
    assert payload["stage_latency_ms"] == {"verdict_gather": 17340}


def test_telemetry_that_cannot_be_emitted_does_not_become_the_caller_s_problem(
    caplog, monkeypatch
) -> None:
    """The containment, proved by making the emit fail.

    The decision this line describes has already been made, sealed and written.
    If measuring it could raise, that fault would land in the `except` guarding
    the write, and a stored receipt would be rolled back, re-marked failed and
    answered 500. Observing a request must never change its outcome.
    """

    class _Json:
        @staticmethod
        def dumps(*args, **kwargs):
            raise TypeError("nothing here is serialisable")

    monkeypatch.setattr(policy_case_decision, "json", _Json)

    with caplog.at_level(logging.INFO, logger=policy_case_decision.__name__):
        policy_case_decision._log_finalisation(
            decision_id="decision-5",
            correlation_id="corr-5",
            stage_latency_ms={"verdict_gather": 1},
            finalisation_ms={"receipt_finalize": 1},
            stored=True,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert not any(m.startswith(policy_case_decision.FINALISATION_LOG_EVENT) for m in messages)
    assert any("finalisation telemetry could not be emitted" in m for m in messages)


def _only_finalisation_payload(caplog) -> dict:
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith(policy_case_decision.FINALISATION_LOG_EVENT)
    ]
    assert len(lines) == 1, lines
    return json.loads(lines[0][len(policy_case_decision.FINALISATION_LOG_EVENT) + 1 :])


# ── 3. the route that was measuring and discarding ───────────────────


async def test_policy_json_reports_the_stages_it_actually_ran(monkeypatch) -> None:
    """`/policies` had a total and no breakdown, while the breakdown existed.

    The scope helper was already writing a stage map into the context this
    boundary asked for, and the boundary dropped it. The inbound language
    crossing — which the plan's arithmetic put at roughly *half* this route's
    budget — was never measured at all, because it happens before the context
    exists.
    """

    install_language_boundary(monkeypatch)
    _install_retrieval(
        monkeypatch,
        timings={
            "scope_load": 500,
            "index_probe": 940,
            "projection_readiness": 1025,
            "policy_search": 1690,
            "policy_selection": 6,
            "rule_slice_and_fit": 2,
        },
    )

    envelope = await policy_case_decision.retrieve_project_policies(
        object(),
        policy_set=_PolicySet(),
        scenario="which policy governs unpaid leave?",
        correlation_id="correlation-stage-map",
    )
    stages = envelope.stage_latency_ms

    assert stages is not None
    assert stages["policy_search"] == 1690
    assert stages["index_probe"] == 940
    # Measured here for the first time: it is not in the context the helper
    # returns, because it happens before that context exists.
    assert "language_in" in stages
    assert "language_out" in stages
    assert all(isinstance(value, int) and value >= 0 for value in stages.values())


async def test_policy_json_omits_the_stages_this_route_never_runs(monkeypatch) -> None:
    """Absent, not zero.

    This route makes no embedding call, runs no rule query, no classifier and no
    gather. Reporting those as `0` would say they ran instantly; reporting them
    not at all says they did not run — which is the difference the whole
    convention rests on.
    """

    install_language_boundary(monkeypatch)
    _install_retrieval(monkeypatch, timings={"scope_load": 500, "policy_search": 1690})

    envelope = await policy_case_decision.retrieve_project_policies(
        object(),
        policy_set=_PolicySet(),
        scenario="which policy governs unpaid leave?",
        correlation_id="correlation-absent",
    )

    assert envelope.stage_latency_ms is not None
    assert set(envelope.stage_latency_ms).isdisjoint(
        {
            "embedding",
            "rule_discovery",
            "retrieval_discovery_wall",
            "classifier",
            "information_gather",
            "verdict_gather",
            "gather_wall",
            "gather_total",
            "decider_wall",
            "to_envelope",
            "reservation",
        }
    )


async def test_policy_json_stage_telemetry_did_not_make_it_look_like_a_decision(
    monkeypatch,
) -> None:
    """The guard the existing suite states negatively, restated for the new field.

    The one shape promise this contract makes is that it can never be mistaken
    for a determination. A timing map is not decision-shaped, and the schema
    version is unchanged because nothing that already existed moved.
    """

    install_language_boundary(monkeypatch)
    _install_retrieval(monkeypatch, timings={"scope_load": 500})

    envelope = await policy_case_decision.retrieve_project_policies(
        object(),
        policy_set=_PolicySet(),
        scenario="which policy governs unpaid leave?",
        correlation_id="correlation-shape",
    )
    wire = envelope.model_dump(mode="json")

    assert wire["schema_version"] == "policy_retrieval_v1"
    assert set(wire).isdisjoint(
        {"decision_id", "receipt_url", "asked", "outcome", "information", "verdict", "citations"}
    )
    assert "stage_latency_ms" in wire


def test_policy_json_stage_telemetry_is_additive_and_absent_by_default() -> None:
    """A client that has never read the field is unaffected.

    The field defaults to absent rather than to an empty map, so an envelope
    built without telemetry is byte-identical to one built before the field
    existed for every consumer that does not ask for it.
    """

    assert PolicyRetrievalEnvelope.model_fields["stage_latency_ms"].default is None
    assert not PolicyRetrievalEnvelope.model_fields["stage_latency_ms"].is_required()


async def test_policy_json_still_answers_when_the_scope_helper_reports_no_timings(
    monkeypatch,
) -> None:
    """The control for the merge.

    The context is not contractually obliged to carry a stage map — the helper
    only writes one when a caller asked for context. Reading it must degrade to
    "the stages I measured myself", never to an exception on a route that was
    otherwise about to succeed.
    """

    install_language_boundary(monkeypatch)
    _install_retrieval(monkeypatch, timings=None)

    envelope = await policy_case_decision.retrieve_project_policies(
        object(),
        policy_set=_PolicySet(),
        scenario="which policy governs unpaid leave?",
        correlation_id="correlation-no-timings",
    )

    assert envelope.stage_latency_ms is not None
    assert set(envelope.stage_latency_ms) == {"language_in", "language_out"}


async def test_a_refusing_language_boundary_is_still_mapped_to_its_own_error(
    monkeypatch,
) -> None:
    """The timing wrapper did not change how a refusal is reported.

    Measuring the crossing meant putting a `try/finally` around a call that
    already sat inside the handler which maps boundary faults to 503. This
    asserts the mapping survived — it does **not** assert the duration, because
    on this path no envelope is ever built and the recorded value has nowhere
    to be observed. That is a real limit of what can be checked here, not an
    omission.
    """

    from policy_platform.infrastructure.assistants import ai_case_language

    install_language_boundary(
        monkeypatch,
        scenario_error=ai_case_language.LanguageBoundaryError(
            ai_case_language.SCENARIO_TRANSLATION_UNAVAILABLE, "boundary down"
        ),
    )
    _install_retrieval(monkeypatch, timings={"scope_load": 1})

    with pytest.raises(policy_case_decision.CaseDecisionError) as caught:
        await policy_case_decision.retrieve_project_policies(
            object(),
            policy_set=_PolicySet(),
            scenario="which policy governs unpaid leave?",
            correlation_id="correlation-boundary-down",
        )

    assert caught.value.status_code == 503


# ── 4. telemetry is metered per request, not per process ─────────────


async def test_concurrent_requests_do_not_mix_their_own_usage() -> None:
    """A standing property this milestone must not have disturbed.

    This is not a guard on new code — it passes with the whole change reverted,
    and it is meant to. Usage is metered through a `ContextVar`, and the
    milestone added per-request timing state next to it, so the question "did
    adding request-local measurement break request-local metering?" is worth
    answering rather than assuming. If the scope were ever made process-global
    the totals would still look plausible, which is exactly why it is asserted.
    """

    async def one(prompt_tokens: int) -> dict:
        with collect_token_usage() as scope:
            await asyncio.sleep(0)
            record_call_usage(
                {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": 1,
                    "total_tokens": prompt_tokens + 1,
                }
            )
            await asyncio.sleep(0)
            return policy_case_decision._token_usage_ref(scope).model_dump(mode="json")

    first, second, third = await asyncio.gather(one(10), one(200), one(3000))

    assert first["prompt_tokens"] == 10
    assert second["prompt_tokens"] == 200
    assert third["prompt_tokens"] == 3000
    assert first["calls"] == second["calls"] == third["calls"] == 1


# ── 5. none of this reached the seal ─────────────────────────────────


def test_a_new_stage_key_does_not_move_the_seal() -> None:
    """Computed, not asserted by construction.

    The earlier version of this test only checked that `TraceRef` accepts an
    open map — which would have passed unchanged even if the map had been folded
    into the preimage. So this one builds two receipts and compares the hashes
    they actually produce.

    The two differ in the new stage keys and also in the call identifiers, which
    `_envelope` mints fresh each time. That does not weaken the comparison: the
    identifiers are already proved outside the preimage by
    `test_the_seal_is_indifferent_to_record_identity_and_the_url` in the suite
    that owns the seal, so the stage map is the only difference that could move
    the hash.
    """

    baseline = _envelope()
    instrumented = _envelope(
        context={
            **_CONTEXT,
            "timings_ms": {"index_probe": 940, "index_state_probe": 12},
        }
    )

    assert instrumented.trace.stage_latency_ms == {
        "index_probe": 940,
        "index_state_probe": 12,
    }
    assert baseline.trace.stage_latency_ms != instrumented.trace.stage_latency_ms
    assert instrumented.decision_hash == baseline.decision_hash
    assert "index_probe" not in str(decision_hash_preimage_v2(instrumented))


def test_the_stage_map_a_receipt_carries_is_a_copy_of_the_one_it_was_built_from() -> None:
    """The property that makes the out-of-band rule enforceable.

    Post-envelope durations are kept out of the receipt by never writing them
    into the context. That discipline is only checkable because the envelope
    holds a *copy*: if it aliased the caller's dict, a later write to the
    context would silently reach a receipt that had already been sealed and
    stored, and no test of the writing code could catch it.
    """

    source = {"index_probe": 1}
    built = TraceRef(stage_latency_ms=source)
    source["index_probe"] = 2
    source["receipt_finalize"] = 41

    assert built.stage_latency_ms == {"index_probe": 1}

