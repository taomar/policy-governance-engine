"""Putting a case to a *project's* policies: retrieve the ones that bear on the
question, discard the rest, and evaluate only the survivors.

WHY THIS EXISTS

The per-policy path (`ai_case_intent.answer_policy_case`, the `/policy-case/answer`
endpoint) answers one policy a reviewer has already chosen. A reviewer can also put
a case to the whole project without naming a policy — and there the instruction is
explicit and load-bearing:

    "u never run against all published, u must use AI search and any technique
     possible to retrieve highest policies match before evaluation, non matching
     policies are discarded"

So this module never evaluates against every policy. It *retrieves first*: it
embeds the question and runs the same hybrid clause search the Ask-AI chat uses
(`ai_chat.ask`), scoped to the project's own documents, then maps the retrieved
clauses back to the policies that own them and keeps only those. The rest are
discarded, and which were considered, retained, and discarded — and on what basis —
is reported, because a reviewer must always be able to see that narrowing happened
and how much (constraint 10). Reusing the chat's retrieval rather than standing up
a second search path is deliberate: a second copy always drifts (a recorded failure
pattern), so the one search machinery is shared.

HOW A RETRIEVED CLAUSE IS MAPPED BACK TO A POLICY

The search index keys every clause as ``{document_version_id}_{clause_id}``
(`clause_search_document_id`), and the lean projection carries that same key on
every span it holds (`policy_case_payload`). So a retrieved clause is mapped to the
policy that owns it by the join those two already share — no heading match, no
title guess, nothing tuned to a corpus. A policy is retained when one of its
clauses ranks inside the retrieval budget; it is discarded otherwise, and told
apart from a policy that never surfaced at all.

WHY NO FAN-OUT

The retained policies are evaluated together, in one gather over their combined
lean records, not one call per policy: "u dont loop in code one policy after other,
u have the json light already to evaluate against." The combined size is measured
and reported (constraint 11), and if it ever exceeds the one-gather budget the
answer is refused rather than trimmed — the refusal is `ai_case_intent`'s, kept in
one place.

THE STATES A RETRIEVAL CAN BE IN, KEPT APART

Six facts about a search are not one fact (constraint 5), and none of them may
degrade silently to "answer against all" (constraint 10):

  - ``narrowed``      — retrieval kept a subset; those are evaluated.
  - ``no_match``      — retrieval ran and the project is indexed, but nothing it
                        surfaced belongs to a testable policy. "No policy matched
                        this question" — a real answer, not an absence.
  - ``index_empty``   — the project has testable policies but none are indexed, so
                        retrieval cannot be relied on for it. (Uploads can report
                        ``clauses_indexed: 0`` while search is enabled; a document
                        can be in Postgres and absent from the grounding index.)
  - ``unavailable``   — search is not configured on this server at all.
  - ``failed``        — the search call itself raised.
  - ``empty``         — the project has no policy with live rules to test.

The one thing forbidden — falling back to evaluating every policy — is never done
in any of these states. When retrieval cannot be relied on, the reviewer is told,
and the escape hatch is the single-policy scope: naming a ``provision_id`` bypasses
retrieval entirely, because a reviewer who has chosen one policy has already done
the narrowing.

Nothing in this module names a domain. It works from the project's own provisions,
its own document ids, and the document's own clause keys, so it holds for any
governance corpus (constraint 1). The counts it reports are policies first, then
rules (constraint 2).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, DocumentProvision, SourceDocument
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.assistants.ai_case_intent import (
    _MAX_RECORD_CHARS,
    answer_case_over_policies,
)
from policy_platform.infrastructure.projection.policy_case_payload import (
    case_payload_for_provision,
    to_compact,
)
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)


#: How far down the ranked clause hits a policy may be found and still be retained.
#: A budget, the same lever the Ask-AI chat spends on retrieval (`ai_chat.ask`
#: takes the top 6), set a little wider because a project case can bear on more
#: policies than a single-topic chat turn: a clause ranking in the top of the
#: search is what keeps its policy in, and everything below it is discarded. Making
#: this the retention threshold rather than a count of policies is what lets the
#: narrowing *adapt* — a question whose bearing clauses cluster in one policy keeps
#: one, a question that spreads keeps several — instead of always keeping a fixed
#: number whether they bear or not. Over-keeping is the safe error here: the gather
#: re-checks each rule's bearing and cites only those that speak to the question,
#: so a policy retained but not bearing costs a little context, never a false
#: citation; under-keeping would drop a policy that bears, which is the one outcome
#: the user forbade. Named as a budget, not a measurement of any corpus.
RETRIEVAL_CLAUSE_BUDGET = 8

#: How many ranked clauses are examined at all, a cost bound on the search. Wider
#: than the retention budget so a policy that surfaced but ranked out is reported
#: *with its score* — a reviewer sees it was seen and set aside, not that it never
#: appeared — while policies beyond it are honestly "did not surface". A scan, not
#: a corpus count.
RETRIEVAL_CLAUSE_SCAN = 40

#: The characters of the retained policies' combined record the gather may read in
#: one pass — the same ceiling `ai_case_intent` applies to a single policy's
#: record, shared so the size budget has one source of truth rather than two.
PAYLOAD_BUDGET_CHARS = _MAX_RECORD_CHARS

#: The retrieval method named in the response, so the reviewer knows which path
#: produced the narrowing. Reuses the chat's hybrid keyword+vector clause search.
RETRIEVAL_METHOD = "hybrid_vector_topk"

#: The two scopes a case can be put in. Named, because a reviewer who chose one
#: policy and a reviewer who put a question to the project are doing two different
#: things, and only the second one retrieves.
SCOPE_SINGLE = "single"
SCOPE_PROJECT = "project"

#: The six honest states a retrieval can be in, plus the seventh — ``bypassed`` —
#: for the single-policy scope where retrieval does not run at all. Kept apart on
#: purpose (constraint 5); collapsing any pair reports one situation as another,
#: and none of them is ever "evaluate against all" (constraint 10).
RETRIEVAL_NARROWED = "narrowed"
RETRIEVAL_NO_MATCH = "no_match"
RETRIEVAL_INDEX_EMPTY = "index_empty"
RETRIEVAL_UNAVAILABLE = "unavailable"
RETRIEVAL_FAILED = "failed"
RETRIEVAL_EMPTY_SET = "empty"
RETRIEVAL_BYPASSED = "bypassed"

#: Why a candidate policy was discarded, told apart so "seen and set aside" never
#: reads the same as "never surfaced".
DISCARD_OUTSIDE_BUDGET = "outside_budget"  # surfaced in the scan but ranked below the budget
DISCARD_NO_MATCH = "no_retrieval_match"  # no clause of it surfaced in the scan at all


class ProvisionNotInProject(LookupError):
    """Raised when a named provision exists but belongs to a different project.

    A distinct fact from an unknown id: the reviewer named a real policy, only not
    one of this project's, so the endpoint answers 404 without pretending the id
    was malformed.
    """


def provision_search_ids(payload: dict) -> set[str]:
    """The search keys a policy's clauses are indexed under, read from its payload.

    Every span in the lean record carries the ``search_document_id`` the index
    keyed that clause under (`policy_case_payload._span_ref`), which is exactly the
    id a clause hit comes back as. Collecting them is what lets a retrieved clause
    be mapped back to the policy that owns it, over the join the projection and the
    index already share rather than any second key this module invents.
    """

    keys: set[str] = set()
    for span in (payload.get("spans") or {}).values():
        if not isinstance(span, dict):
            continue
        key = span.get("search_document_id")
        if key:
            keys.add(str(key))
    return keys


def _max_score(scores: list) -> float | None:
    present = [s for s in scores if isinstance(s, (int, float))]
    return max(present) if present else None


def _identity(candidate: dict) -> dict:
    return {
        "provision_id": candidate["provision_id"],
        "provision_key": candidate["provision_key"],
        "heading_path": candidate["heading_path"],
        "rules": candidate["rules"],
    }


def select_retained(candidates: list[dict], hits: list[dict], *, budget: int) -> dict:
    """Split the candidate policies into the ones retrieval kept and the ones it
    discarded, by mapping the ranked clause hits back to the policies that own them.

    ``candidates`` each carry their ``search_document_ids`` (from
    :func:`provision_search_ids`); ``hits`` are the ranked search results, each an
    ``id`` (a clause's search key) and its ``@search.score``. A policy is retained
    when one of its clauses ranks inside ``budget``; otherwise it is discarded, and
    a policy that surfaced lower in the scan is told apart from one that never
    surfaced at all.

    Returns ``{"retained", "discarded", "considered", "clauses_retrieved"}``.
    ``considered`` lists every candidate in document order with a ``retained`` flag,
    so the narrowing is fully visible (constraint 10); ``retained`` is ordered by
    how high the policy ranked. No payload rides in any of these entries — they are
    the report, not the records.
    """

    ranked: list[tuple[int, str, object]] = []
    for rank, hit in enumerate(hits):
        hid = hit.get("id")
        if hid is None:
            continue
        ranked.append((rank, str(hid), hit.get("@search.score")))

    retained: list[dict] = []
    discarded: list[dict] = []
    considered: list[dict] = []

    for candidate in candidates:
        keys = candidate.get("search_document_ids") or set()
        matches = [(rank, hid, score) for (rank, hid, score) in ranked if hid in keys]
        in_budget = [m for m in matches if m[0] < budget]
        identity = _identity(candidate)

        if in_budget:
            entry = {
                **identity,
                "retained": True,
                "best_rank": min(m[0] for m in in_budget),
                "best_score": _max_score([m[2] for m in matches]),
                "matched_clauses": len({m[1] for m in in_budget}),
            }
            retained.append(entry)
        else:
            if matches:
                best_rank: int | None = min(m[0] for m in matches)
                best_score = _max_score([m[2] for m in matches])
                reason = DISCARD_OUTSIDE_BUDGET
            else:
                best_rank = None
                best_score = None
                reason = DISCARD_NO_MATCH
            entry = {
                **identity,
                "retained": False,
                "best_rank": best_rank,
                "best_score": best_score,
                "matched_clauses": 0,
                "discard_reason": reason,
            }
            discarded.append(entry)
        considered.append(entry)

    retained.sort(key=lambda e: e["best_rank"] if e["best_rank"] is not None else 1_000_000)
    return {
        "retained": retained,
        "discarded": discarded,
        "considered": considered,
        "clauses_retrieved": len(ranked),
    }


async def load_project_scope(session: AsyncSession, policy_set_id) -> dict:
    """Read a project's testable policies, its untestable ones, and its document ids.

    A *testable* policy is a provision with at least one live rule
    (``superseded_at IS NULL``) — the same "current set, drafts included" the
    per-policy path answers over, so a project that has never published still has
    policies whose rules state things. A provision with no live rule cannot be
    retrieved (it owns no grounded clause) and cannot be answered from, so it is
    reported as *untestable* rather than silently dropped: an empty policy and a
    discarded one are different facts (constraint 5).

    The document ids scope the search to this project's own documents, exactly as
    `ai_chat.ask` scopes its retrieval, so a project case is never grounded in
    another project's clauses.
    """

    psid = policy_set_id if isinstance(policy_set_id, uuid.UUID) else uuid.UUID(str(policy_set_id))

    provisions = list(
        (
            await session.execute(
                select(DocumentProvision)
                .where(DocumentProvision.policy_set_id == psid)
                .order_by(DocumentProvision.first_sequence)
            )
        )
        .scalars()
        .all()
    )

    live_counts: dict = {}
    if provisions:
        rows = await session.execute(
            select(CandidateRule.provision_id, func.count())
            .where(CandidateRule.provision_id.in_([p.id for p in provisions]))
            .where(CandidateRule.superseded_at.is_(None))
            .group_by(CandidateRule.provision_id)
        )
        live_counts = {row[0]: row[1] for row in rows.all()}

    document_ids = [
        str(row[0])
        for row in (
            await session.execute(select(SourceDocument.id).where(SourceDocument.policy_set_id == psid))
        ).all()
    ]

    candidates: list[dict] = []
    excluded: list[dict] = []
    for provision in provisions:
        rule_count = live_counts.get(provision.id, 0)
        if rule_count <= 0:
            excluded.append(
                {
                    "provision_id": str(provision.id),
                    "provision_key": provision.provision_key,
                    "heading_path": provision.heading_path_json,
                    "reason": "no_live_rules",
                }
            )
            continue
        payload = await case_payload_for_provision(session, provision.id)
        if payload is None:  # pragma: no cover - a live-count without a payload cannot occur
            continue
        candidates.append(
            {
                "provision_id": str(provision.id),
                "provision_key": provision.provision_key,
                "heading_path": provision.heading_path_json,
                "rules": rule_count,
                "search_document_ids": provision_search_ids(payload),
                "payload": payload,
            }
        )

    return {"candidates": candidates, "excluded": excluded, "document_ids": document_ids}


def _index_filter(document_ids: list[str]) -> str:
    if len(document_ids) == 1:
        return f"policy_id eq '{document_ids[0]}'"
    return f"search.in(policy_id, '{','.join(document_ids)}', ',')"


def _size_report(records: list[dict]) -> dict:
    """How large the retained policies' combined record is, against the one-gather
    budget — measured and reported so a payload that must be capped is a visible
    decision, never a silent trim (constraint 11)."""

    transport = to_compact(
        {"policies": [{"policy": r["policy"], "record": r["payload"]} for r in records]}
    )
    size = len(transport)
    return {
        "combined_chars": size,
        "budget_chars": PAYLOAD_BUDGET_CHARS,
        "oversize": size > PAYLOAD_BUDGET_CHARS,
    }


def _bare_considered(candidates: list[dict]) -> list[dict]:
    """The candidate policies listed without a retrieval verdict — for the states
    where retrieval could not produce one (unavailable, failed, index-empty). They
    are still shown, so a reviewer sees the testable policies the project holds and
    the top-level status says why none was retained."""

    return [{**_identity(c), "retained": False} for c in candidates]


def _retrieval_block(
    status: str,
    *,
    considered: list[dict],
    retained: list[dict],
    discarded: list[dict],
    excluded: list[dict],
    clauses_retrieved: int,
    reason: str | None = None,
) -> dict:
    block = {
        "status": status,
        "method": RETRIEVAL_METHOD,
        "clause_budget": RETRIEVAL_CLAUSE_BUDGET,
        "clause_scan": RETRIEVAL_CLAUSE_SCAN,
        "clauses_retrieved": clauses_retrieved,
        "policies_considered": len(considered),
        "policies_retained": len(retained),
        "policies_discarded": len(discarded),
        "policies_untestable": len(excluded),
    }
    if reason is not None:
        block["reason"] = reason
    return block


def _project_response(
    *,
    policy_set_key: str,
    status: str,
    considered: list[dict],
    retained: list[dict],
    discarded: list[dict],
    excluded: list[dict],
    clauses_retrieved: int,
    evaluation: dict | None,
    size: dict,
    reason: str | None = None,
) -> dict:
    return {
        "scope": SCOPE_PROJECT,
        "policy_set_key": policy_set_key,
        "retrieval": _retrieval_block(
            status,
            considered=considered,
            retained=retained,
            discarded=discarded,
            excluded=excluded,
            clauses_retrieved=clauses_retrieved,
            reason=reason,
        ),
        "considered": considered,
        "excluded": excluded,
        "evaluation": evaluation,
        "size": size,
    }


async def _answer_single_scope(
    session: AsyncSession, *, policy_set, provision_id, scenario: str, reasoning_effort: str
) -> dict:
    """The reviewer chose one policy: bypass retrieval and answer that policy.

    Retrieval does not run — the narrowing a reviewer would ask retrieval for has
    already been done by choosing the policy. The one policy is projected exactly
    as `/policy-case/answer` projects it, and evaluated through the same multi-policy
    gather (a set of one), so a single-scope answer carries the same per-policy
    citations and fabrication guarantees as a project one.
    """

    payload = await case_payload_for_provision(session, provision_id)
    if payload is None:
        raise ProvisionNotInProject(f"No provision with id {provision_id!r}")

    envelope = payload.get("envelope") or {}
    if str(envelope.get("policy_set_id")) != str(policy_set.id):
        raise ProvisionNotInProject(
            f"Provision {provision_id!r} does not belong to project {policy_set.key!r}"
        )

    identity = {
        "provision_id": envelope.get("provision_id"),
        "provision_key": envelope.get("provision_key"),
        "heading_path": envelope.get("heading_path"),
        "rules": len(payload.get("rules") or []),
    }
    record = {"policy": identity, "payload": payload}
    evaluation = await answer_case_over_policies(
        [record], scenario=scenario, reasoning_effort=reasoning_effort
    )

    return {
        "scope": SCOPE_SINGLE,
        "policy_set_key": policy_set.key,
        "provision": identity,
        "retrieval": {
            "status": RETRIEVAL_BYPASSED,
            "reason": "the reviewer chose one policy; retrieval does not run",
        },
        "evaluation": evaluation,
        "size": _size_report([record]),
    }


async def _answer_project_scope(
    session: AsyncSession, *, policy_set, scenario: str, reasoning_effort: str
) -> dict:
    """No policy was named: retrieve the ones that bear on the question, discard
    the rest, and evaluate only the survivors — never the whole set."""

    scope = await load_project_scope(session, policy_set.id)
    candidates = scope["candidates"]
    excluded = scope["excluded"]
    document_ids = scope["document_ids"]

    def respond(status: str, *, considered, retained, discarded, clauses_retrieved, evaluation, size, reason=None):
        return _project_response(
            policy_set_key=policy_set.key,
            status=status,
            considered=considered,
            retained=retained,
            discarded=discarded,
            excluded=excluded,
            clauses_retrieved=clauses_retrieved,
            evaluation=evaluation,
            size=size,
            reason=reason,
        )

    empty_size = _size_report([])

    if not candidates:
        return respond(
            RETRIEVAL_EMPTY_SET,
            considered=[],
            retained=[],
            discarded=[],
            clauses_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason="the project has no policy with live rules to test",
        )

    settings = get_settings()
    if not settings.search_enabled:
        # The one thing forbidden is falling back to "all policies". Retrieval
        # cannot run, so no evaluation is made and the reviewer is told why; the
        # single-policy scope is the escape hatch.
        return respond(
            RETRIEVAL_UNAVAILABLE,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            clauses_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=(
                "search is not configured on this server, so the policies bearing on the question "
                "cannot be retrieved; no evaluation was made. Choose a single policy to test it directly."
            ),
        )

    index_name = settings.azure_search_authoring_index
    try:
        ai_client = AzureOpenAIClient(settings)
        [vector] = await ai_client.embed([scenario])
        search_client = AzureSearchClient(settings)
        hits = await search_client.vector_search(
            index_name,
            query_text=scenario,
            vector=vector,
            policy_ids=document_ids or None,
            top=RETRIEVAL_CLAUSE_SCAN,
        )
    except Exception as exc:  # noqa: BLE001 - a failed search is its own reported state
        logger.warning("project-case retrieval failed for set %s: %s", policy_set.key, exc)
        return respond(
            RETRIEVAL_FAILED,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            clauses_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=f"the search call failed: {exc}",
        )

    if not hits:
        # Nothing came back. Tell apart a project whose clauses are not in the
        # index at all (retrieval cannot be relied on for it) from one that is
        # indexed but where the query genuinely matched nothing.
        try:
            indexed = await search_client.find_ids_by_filter(
                index_name, filter_expr=_index_filter(document_ids), page_size=1
            )
        except Exception as exc:  # noqa: BLE001 - fall back to the honest weaker claim
            logger.warning("project-case index probe failed for set %s: %s", policy_set.key, exc)
            indexed = []
        if indexed:
            return respond(
                RETRIEVAL_NO_MATCH,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                clauses_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason="no published policy matched this question",
            )
        return respond(
            RETRIEVAL_INDEX_EMPTY,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            clauses_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=(
                "this project's policies are not in the grounding index, so retrieval cannot be "
                "relied on for it; no evaluation was made. Choose a single policy to test it directly."
            ),
        )

    selection = select_retained(candidates, hits, budget=RETRIEVAL_CLAUSE_BUDGET)
    retained = selection["retained"]
    discarded = selection["discarded"]
    considered = selection["considered"]
    clauses_retrieved = selection["clauses_retrieved"]

    if not retained:
        # The search surfaced clauses, but none inside the budget belongs to a
        # testable policy. A real "no policy matched", distinct from the index
        # being empty and from search being unavailable.
        return respond(
            RETRIEVAL_NO_MATCH,
            considered=considered,
            retained=retained,
            discarded=discarded,
            clauses_retrieved=clauses_retrieved,
            evaluation=None,
            size=empty_size,
            reason="no published policy matched this question",
        )

    by_id = {c["provision_id"]: c for c in candidates}
    records = [
        {
            "policy": {
                "provision_id": entry["provision_id"],
                "provision_key": entry["provision_key"],
                "heading_path": entry["heading_path"],
            },
            "payload": by_id[entry["provision_id"]]["payload"],
        }
        for entry in retained
    ]

    evaluation = await answer_case_over_policies(
        records, scenario=scenario, reasoning_effort=reasoning_effort
    )

    return respond(
        RETRIEVAL_NARROWED,
        considered=considered,
        retained=retained,
        discarded=discarded,
        clauses_retrieved=clauses_retrieved,
        evaluation=evaluation,
        size=_size_report(records),
    )


async def answer_project_case(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    provision_id: str | None = None,
    reasoning_effort: str = "medium",
) -> dict:
    """Answer a case put to a project, at the scope the reviewer chose.

    When ``provision_id`` is given the reviewer has chosen one policy: retrieval is
    bypassed and that policy is answered. Otherwise the case is put to the project,
    and the policies bearing on the question are retrieved and the rest discarded
    before anything is evaluated — never the whole set.

    ``policy_set`` is the resolved project (the caller has already turned a key into
    a row and answered 404 if it did not exist). Raises :class:`ProvisionNotInProject`
    when a named provision is unknown or belongs to another project, ``ValueError``
    when an id is malformed (from the projection), and ``RuntimeError`` when the
    model is not configured — the endpoint maps these to 404, 422, and 503.
    """

    if provision_id is not None and str(provision_id).strip():
        return await _answer_single_scope(
            session,
            policy_set=policy_set,
            provision_id=provision_id,
            scenario=scenario,
            reasoning_effort=reasoning_effort,
        )
    return await _answer_project_scope(
        session, policy_set=policy_set, scenario=scenario, reasoning_effort=reasoning_effort
    )
