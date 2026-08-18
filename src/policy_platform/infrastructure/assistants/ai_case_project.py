"""Putting a case to a *project's* published policies: retrieve the ones that
bear on the question, discard the rest, and evaluate only the survivors.

WHY THIS EXISTS

The per-policy path (`ai_case_intent.answer_policy_case`, the `/policy-case/answer`
endpoint) answers one policy a reviewer has already chosen. A reviewer can also put
a case to the whole project without naming a policy — and there the instruction is
explicit and load-bearing:

    "u never run against all published, u must use AI search and any technique
     possible to retrieve highest policies match before evaluation, non matching
     policies are discarded"

So this module never evaluates against every policy. It *retrieves first*: it
embeds the question and searches the project's own policy index, whose unit is a
published policy at the latest approved version. Retrieved policy documents are
mapped back to the lean published payload by ``policy_version_id`` plus
``provision_key`` — identity that survives clause re-parsing. The rest are
discarded, and which were considered, retained, and discarded — and on what basis —
is reported, because a reviewer must always be able to see that narrowing happened
and how much (constraint 10).

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

  - ``narrowed``              — retrieval kept a subset; those are evaluated.
  - ``no_match``              — retrieval ran on the current published policy
                                index, but no policy matched this question.
  - ``no_published_version``  — the project has no active approved version, so
                                there is no published project scope to test.
  - ``index_not_built``       — the project's policy index does not exist yet.
  - ``index_stale``           — the index exists, but not for the active
                                published version.
  - ``unavailable``           — search is not configured on this server at all.
  - ``failed``                — the search call itself raised.
  - ``empty``                 — the active version has no published policy rules.

The one thing forbidden — falling back to evaluating every policy — is never done
in any of these states. When retrieval cannot be relied on, the reviewer is told,
and the escape hatch is the single-policy scope: naming a ``provision_id`` bypasses
retrieval entirely, because a reviewer who has chosen one policy has already done
the narrowing.

Nothing in this module names a domain. It works from the project's own published
version and policy identity, so it holds for any governance corpus (constraint 1).
The counts it reports are policies first, then rules (constraint 2).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import DocumentProvision
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.assistants.ai_case_intent import (
    _MAX_RECORD_CHARS,
    answer_case_over_policies,
)
from policy_platform.infrastructure.projection.policy_case_payload import to_compact
from policy_platform.infrastructure.projection.published_case_payload import (
    active_version_for_policy_set,
    published_case_payload_for_policy,
    published_case_payloads_for_policy_set,
)
from policy_platform.infrastructure.search.policy_index import policy_document_id, policy_index_name
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)


#: How far down the ranked policy hits a policy may be found and still be retained.
#: A policy ranking in the top of the search is what keeps it in, and everything
#: below it is discarded. Making this the retention threshold rather than a score
#: threshold is deliberate: RRF-hybrid scores are close together, so rank is the
#: discriminator. Over-keeping is the safe error here: the gather re-checks each
#: rule's bearing and cites only those that speak to the question, so a policy
#: retained but not bearing costs a little context, never a false citation;
#: under-keeping would drop a policy that bears, which is the one outcome the user
#: forbade. Named as a budget, not a measurement of any corpus.
RETRIEVAL_POLICY_BUDGET = 5

#: How many ranked policies are examined at all, a cost bound on the search. Wider
#: than the retention budget so a policy that surfaced but ranked out is reported
#: *with its score* — a reviewer sees it was seen and set aside, not that it never
#: appeared — while policies beyond it are honestly "did not surface".
RETRIEVAL_POLICY_SCAN = 40

#: The characters of the retained policies' combined record the gather may read in
#: one pass — the same ceiling `ai_case_intent` applies to a single policy's
#: record, shared so the size budget has one source of truth rather than two.
PAYLOAD_BUDGET_CHARS = _MAX_RECORD_CHARS

#: The retrieval method named in the response, so the reviewer knows which path
#: produced the narrowing.
RETRIEVAL_METHOD = "hybrid_vector_topk"

#: The two scopes a case can be put in. Named, because a reviewer who chose one
#: policy and a reviewer who put a question to the project are doing two different
#: things, and only the second one retrieves.
SCOPE_SINGLE = "single"
SCOPE_PROJECT = "project"

#: The honest states a retrieval can be in, plus ``bypassed`` for the
#: single-policy scope where retrieval does not run at all. Kept apart on purpose
#: (constraint 5); collapsing any pair reports one situation as another, and none
#: of them is ever "evaluate against all" (constraint 10).
RETRIEVAL_NARROWED = "narrowed"
RETRIEVAL_NO_MATCH = "no_match"
RETRIEVAL_INDEX_EMPTY = "index_empty"
RETRIEVAL_NO_PUBLISHED_VERSION = "no_published_version"
RETRIEVAL_INDEX_NOT_BUILT = "index_not_built"
RETRIEVAL_INDEX_STALE = "index_stale"
RETRIEVAL_UNAVAILABLE = "unavailable"
RETRIEVAL_FAILED = "failed"
RETRIEVAL_EMPTY_SET = "empty"
RETRIEVAL_BYPASSED = "bypassed"
RETRIEVAL_POLICY_NOT_PUBLISHED = "policy_not_published"

#: Why a candidate policy was discarded, told apart so "seen and set aside" never
#: reads the same as "never surfaced".
DISCARD_OUTSIDE_BUDGET = "outside_budget"  # surfaced in the scan but ranked below the budget
DISCARD_NO_MATCH = "no_retrieval_match"  # it did not surface in the scan at all
DISCARD_STALE_VERSION = "stale_index_version"  # surfaced, but not for the active version


class ProvisionNotInProject(LookupError):
    """Raised when a named provision exists but belongs to a different project.

    A distinct fact from an unknown id: the reviewer named a real policy, only not
    one of this project's, so the endpoint answers 404 without pretending the id
    was malformed.
    """


def published_policy_search_id(payload: dict) -> str | None:
    """The stable search key for a published policy document."""

    envelope = payload.get("envelope") or {}
    policy_version_id = envelope.get("policy_version_id")
    provision_key = envelope.get("provision_key")
    if not policy_version_id or not provision_key:
        return None
    return policy_document_id(policy_version_id=str(policy_version_id), provision_key=str(provision_key))


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
    discarded, by mapping the ranked policy hits back to the published payloads.

    ``candidates`` each carry their ``search_document_id`` (from
    :func:`published_policy_search_id`); ``hits`` are the ranked search results,
    each an ``id`` (a policy search key) and its ``@search.score``. A policy is
    retained when it ranks inside ``budget``; otherwise it is discarded, and a
    policy that surfaced lower in the scan is told apart from one that never
    surfaced at all.

    Returns ``{"retained", "discarded", "considered", "policies_retrieved"}``.
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
        key = candidate.get("search_document_id")
        keys = {str(key)} if key else set()
        matches = [(rank, hid, score) for (rank, hid, score) in ranked if hid in keys]
        in_budget = [m for m in matches if m[0] < budget]
        identity = _identity(candidate)

        if in_budget:
            entry = {
                **identity,
                "retained": True,
                "best_rank": min(m[0] for m in in_budget),
                "best_score": _max_score([m[2] for m in matches]),
                "matched_policies": len({m[1] for m in in_budget}),
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
                "matched_policies": 0,
                "discard_reason": reason,
            }
            discarded.append(entry)
        considered.append(entry)

    retained.sort(key=lambda e: e["best_rank"] if e["best_rank"] is not None else 1_000_000)
    return {
        "retained": retained,
        "discarded": discarded,
        "considered": considered,
        "policies_retrieved": len(ranked),
    }


async def load_project_scope(session: AsyncSession, policy_set_id) -> dict:
    """Read the project's active published policies.

    Project-wide cases intentionally use published policies at the active approved
    version only. A project with draft/live candidate rules but no active approved
    version is therefore not an empty search result; it has no published project
    scope to test yet.
    """

    psid = policy_set_id if isinstance(policy_set_id, uuid.UUID) else uuid.UUID(str(policy_set_id))
    active_version = await active_version_for_policy_set(session, psid)
    if active_version is None:
        return {
            "has_published_version": False,
            "active_version_id": None,
            "active_version_number": None,
            "candidates": [],
            "excluded": [],
        }

    payloads = await published_case_payloads_for_policy_set(session, psid)

    candidates: list[dict] = []
    excluded: list[dict] = []
    for payload in payloads:
        envelope = payload.get("envelope") or {}
        rule_count = len(payload.get("rules") or [])
        provision_key = str(envelope.get("provision_key") or "")
        if rule_count <= 0:
            excluded.append(
                {
                    "provision_id": None,
                    "provision_key": provision_key,
                    "heading_path": envelope.get("heading_path") or [],
                    "reason": "no_published_rules",
                }
            )
            continue
        search_document_id = published_policy_search_id(payload)
        if search_document_id is None:  # pragma: no cover - active published payloads carry this envelope
            continue
        candidates.append(
            {
                "provision_id": envelope.get("provision_id"),
                "provision_key": provision_key,
                "heading_path": envelope.get("heading_path") or [],
                "rules": rule_count,
                "policy_version_id": str(envelope.get("policy_version_id")),
                "version_number": envelope.get("version_number"),
                "search_document_id": search_document_id,
                "payload": payload,
            }
        )

    return {
        "has_published_version": True,
        "active_version_id": str(active_version.id),
        "active_version_number": active_version.version_number,
        "candidates": candidates,
        "excluded": excluded,
    }


def _odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _policy_index_filter(policy_set_key: str, policy_version_id: str | None = None) -> str:
    clauses = [f"policy_set_key eq {_odata_string(policy_set_key)}"]
    if policy_version_id:
        clauses.append(f"policy_version_id eq {_odata_string(policy_version_id)}")
    return " and ".join(clauses)


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
    policies_retrieved: int,
    reason: str | None = None,
) -> dict:
    block = {
        "status": status,
        "method": RETRIEVAL_METHOD,
        "policy_budget": RETRIEVAL_POLICY_BUDGET,
        "policy_scan": RETRIEVAL_POLICY_SCAN,
        "policies_retrieved": policies_retrieved,
        # Kept temporarily for API compatibility with callers already reading the
        # old field name; the value now counts policy documents, not clauses.
        "clauses_retrieved": policies_retrieved,
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
    policies_retrieved: int,
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
            policies_retrieved=policies_retrieved,
            reason=reason,
        ),
        "considered": considered,
        "excluded": excluded,
        "evaluation": evaluation,
        "size": size,
    }


async def _provision_in_project(session: AsyncSession, *, policy_set, provision_id):
    """The named provision, or `ProvisionNotInProject` if it is not this project's.

    Kept apart from "this policy is not published": an id that names nothing, or
    names a policy in a different project, is a caller error the endpoint answers
    404 to. A policy that exists here but is absent from the published version is
    a legitimate question with an honest answer, and must not be reported as if
    the reviewer had asked for something that does not exist.
    """

    pid = provision_id if isinstance(provision_id, uuid.UUID) else uuid.UUID(str(provision_id))
    provision = await session.get(DocumentProvision, pid)
    if provision is None:
        raise ProvisionNotInProject(f"No provision with id {provision_id!r}")
    if str(provision.policy_set_id) != str(policy_set.id):
        raise ProvisionNotInProject(
            f"Provision {provision_id!r} does not belong to project {policy_set.key!r}"
        )
    return provision


async def _answer_single_scope(
    session: AsyncSession, *, policy_set, provision_id, scenario: str, reasoning_effort: str
) -> dict:
    """The reviewer chose one policy: bypass retrieval and answer that policy.

    Retrieval does not run — the narrowing a reviewer would ask retrieval for has
    already been done by choosing the policy. The policy is projected from the
    project's *active approved version*, the same source the project scope reads,
    so naming a policy cannot silently switch the answer to the draft set. It is
    evaluated through the same multi-policy gather (a set of one), so a single-scope
    answer carries the same per-policy citations and fabrication guarantees as a
    project one.

    A provision can exist and still not be answerable here, in two different ways
    that a reviewer acts on differently: the project may have nothing published at
    all, or this particular policy may not be in the version that is published.
    Both are reported, and neither is answered from drafts.
    """

    provision = await _provision_in_project(session, policy_set=policy_set, provision_id=provision_id)

    def unanswerable(status: str, reason: str) -> dict:
        return {
            "scope": SCOPE_SINGLE,
            "policy_set_key": policy_set.key,
            "provision": {
                "provision_id": str(provision.id),
                "provision_key": provision.provision_key,
                "heading_path": provision.heading_path_json,
                "rules": 0,
            },
            "retrieval": {"status": status, "reason": reason},
            "evaluation": None,
            "size": _size_report([]),
        }

    version = await active_version_for_policy_set(session, policy_set.id)
    if version is None:
        return unanswerable(
            RETRIEVAL_NO_PUBLISHED_VERSION,
            "this project has no published version yet, so there is nothing approved to test against",
        )

    payload = await published_case_payload_for_policy(session, policy_set.id, provision.provision_key)
    if payload is None:
        return unanswerable(
            RETRIEVAL_POLICY_NOT_PUBLISHED,
            "this policy is not in the published version; only published policies are tested here",
        )

    envelope = payload.get("envelope") or {}
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
    active_version_id = scope.get("active_version_id")

    def respond(status: str, *, considered, retained, discarded, policies_retrieved, evaluation, size, reason=None):
        return _project_response(
            policy_set_key=policy_set.key,
            status=status,
            considered=considered,
            retained=retained,
            discarded=discarded,
            excluded=excluded,
            policies_retrieved=policies_retrieved,
            evaluation=evaluation,
            size=size,
            reason=reason,
        )

    empty_size = _size_report([])

    if not candidates:
        if not scope.get("has_published_version", True):
            return respond(
                RETRIEVAL_NO_PUBLISHED_VERSION,
                considered=[],
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason="the project has no published version yet; publish a version before testing the whole project",
            )
        return respond(
            RETRIEVAL_EMPTY_SET,
            considered=[],
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason="the active published version has no policy rules to test",
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
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=(
                "search is not configured on this server, so the policies bearing on the question "
                "cannot be retrieved; no evaluation was made. Choose a single policy to test it directly."
            ),
        )

    index_name = policy_index_name(policy_set.key)
    try:
        search_client = AzureSearchClient(settings)
        if not await search_client.index_exists(index_name):
            return respond(
                RETRIEVAL_INDEX_NOT_BUILT,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason=(
                    "this project's published-policy search index has not been built yet, so retrieval cannot be "
                    "relied on for it; no evaluation was made. Republish or rebuild the policy index."
                ),
            )
        ai_client = AzureOpenAIClient(settings)
        [vector] = await ai_client.embed([scenario])
        hits = await search_client.vector_search(
            index_name,
            query_text=scenario,
            vector=vector,
            top=RETRIEVAL_POLICY_SCAN,
        )
    except Exception as exc:  # noqa: BLE001 - a failed search is its own reported state
        logger.warning("project-case retrieval failed for set %s: %s", policy_set.key, exc)
        return respond(
            RETRIEVAL_FAILED,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=f"the search call failed: {exc}",
        )

    if not hits:
        # Nothing came back. Tell apart a project whose active published version
        # is absent from the index from one where the current index genuinely did
        # not match the question.
        try:
            current_indexed = await search_client.find_ids_by_filter(
                index_name, filter_expr=_policy_index_filter(policy_set.key, active_version_id), page_size=1
            )
            any_indexed = await search_client.find_ids_by_filter(
                index_name, filter_expr=_policy_index_filter(policy_set.key), page_size=1
            )
        except Exception as exc:  # noqa: BLE001 - fall back to the honest weaker claim
            logger.warning("project-case index probe failed for set %s: %s", policy_set.key, exc)
            current_indexed = []
            any_indexed = []
        if current_indexed:
            return respond(
                RETRIEVAL_NO_MATCH,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason="no published policy matched this question",
            )
        if any_indexed:
            return respond(
                RETRIEVAL_INDEX_STALE,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason=(
                    "this project's published-policy index has no documents for the active approved version, so "
                    "retrieval cannot be relied on for it; no evaluation was made. Republish or rebuild the policy index."
                ),
            )
        return respond(
            RETRIEVAL_INDEX_EMPTY,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=(
                "this project's published-policy index is empty, so retrieval cannot be relied on for it; "
                "no evaluation was made. Republish or rebuild the policy index."
            ),
        )

    stale_hits = [hit for hit in hits if str(hit.get("document_version")) != str(active_version_id)]
    current_hits = [hit for hit in hits if str(hit.get("document_version")) == str(active_version_id)]
    if hits and not current_hits:
        stale_considered = []
        for candidate in candidates:
            entry = {
                **_identity(candidate),
                "retained": False,
                "best_rank": None,
                "best_score": None,
                "matched_policies": 0,
                "discard_reason": DISCARD_STALE_VERSION,
            }
            stale_considered.append(entry)
        return respond(
            RETRIEVAL_INDEX_STALE,
            considered=stale_considered,
            retained=[],
            discarded=stale_considered,
            policies_retrieved=len(stale_hits),
            evaluation=None,
            size=empty_size,
            reason=(
                "the policy index returned only documents from a superseded published version, so retrieval cannot "
                "be relied on for the active version; no evaluation was made. Republish or rebuild the policy index."
            ),
        )

    selection = select_retained(candidates, current_hits, budget=RETRIEVAL_POLICY_BUDGET)
    retained = selection["retained"]
    discarded = selection["discarded"]
    considered = selection["considered"]
    policies_retrieved = selection["policies_retrieved"]

    if not retained:
        matched_candidate_ids = {entry["provision_key"] for entry in considered if entry.get("best_rank") is not None}
        if current_hits and not matched_candidate_ids:
            return respond(
                RETRIEVAL_INDEX_STALE,
                considered=considered,
                retained=retained,
                discarded=discarded,
                policies_retrieved=policies_retrieved,
                evaluation=None,
                size=empty_size,
                reason=(
                    "the policy index returned current-version documents that are not present in the active "
                    "published payload, so retrieval cannot be relied on; no evaluation was made. Republish or "
                    "rebuild the policy index."
                ),
            )
        # The search surfaced current-version policies, but none inside the
        # budget belongs to a testable policy. A real "no policy matched",
        # distinct from the index being absent/stale and from search unavailable.
        return respond(
            RETRIEVAL_NO_MATCH,
            considered=considered,
            retained=retained,
            discarded=discarded,
            policies_retrieved=policies_retrieved,
            evaluation=None,
            size=empty_size,
            reason="no published policy matched this question",
        )

    by_search_id = {c["search_document_id"]: c for c in candidates}
    records = [
        {
            "policy": {
                "provision_id": entry["provision_id"],
                "provision_key": entry["provision_key"],
                "heading_path": entry["heading_path"],
            },
            "payload": by_search_id[
                policy_document_id(
                    policy_version_id=str(active_version_id),
                    provision_key=str(entry["provision_key"]),
                )
            ]["payload"],
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
        policies_retrieved=policies_retrieved,
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
