"""Policy-set and approved-version endpoints.

Version creation here is an explicit manual-import stand-in for the full
governance workflow (candidate extraction -> review -> approval), which is
deferred (see docs/known-limitations.md). It still enforces Rule 5.3
(insert-only, immutable approved versions) at the repository layer.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    AggregateEligibilityResponse,
    AggregateLimitResponse,
    ApprovedPolicyVersionResponse,
    CreateAggregateLimitRequest,
    CreatePolicySetRequest,
    ImportPolicyVersionRequest,
    MarkPolicySetReviewedRequest,
    PolicySetResponse,
    PreviewAggregateLimitRequest,
    PreviewAggregateLimitResponse,
    ProposeAggregateLimitsRequest,
    ProposeAggregateLimitsResponse,
    UpdateAggregateLimitRequest,
    UpdatePolicySetRequest,
    UpdateTrustedConfigRequest,
)
from policy_platform.contracts.policy import AggregateLimit, CanonicalRule
from policy_platform.infrastructure.aggregates.aggregate_eligibility import assess_rules
from policy_platform.infrastructure.aggregates.aggregate_preview import preview_aggregate_limit
from policy_platform.infrastructure.aggregates.ai_aggregate_proposal import propose_aggregate_limits
from policy_platform.infrastructure.assembly.approved_provision_lookup import (
    approved_provision_groupings,
)
from policy_platform.infrastructure.assembly.policy_assembly import assemble
from policy_platform.infrastructure.assembly.provision_history import policy_history
from policy_platform.infrastructure.assembly.topic_label_lookup import labels_for_policy_set
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.projection.export import (
    ExportFormat,
    content_disposition,
    extension_for,
    media_type_for,
    models_to_export,
)
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.persistence.policy_set_teardown import (
    RETAINED_TABLES,
    delete_policy_set,
)
from policy_platform.infrastructure.persistence.policy_version_import import import_approved_policy_version
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import get_settings
from policy_platform.infrastructure.extraction.policy_formulator import check_trusted_config
from policy_platform.infrastructure.persistence.repositories import (
    ApprovedPolicyVersionRepository,
    PolicyAggregateLimitRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/policy-sets", tags=["policy-sets"])


def _to_response(ps) -> PolicySetResponse:
    return PolicySetResponse(
        id=str(ps.id),
        key=ps.key,
        name=ps.name,
        owner=ps.owner,
        description=ps.description,
        category=ps.category,
        tags=list(ps.tags_json or []),
        review_due_date=ps.review_due_date,
        last_reviewed_at=ps.last_reviewed_at,
        is_review_overdue=ps.review_due_date is not None and ps.review_due_date < date.today(),
        accountable_owner=ps.accountable_owner,
        delegate_approver=ps.delegate_approver,
        escalation_contact=ps.escalation_contact,
        consulted_parties=list(ps.consulted_parties_json or []),
        informed_parties=list(ps.informed_parties_json or []),
    )


def _aggregate_limit_to_response(row) -> AggregateLimitResponse:
    return AggregateLimitResponse(
        id=str(row.id),
        policy_set_id=str(row.policy_set_id),
        aggregate_key=row.aggregate_key,
        description=row.description,
        contributing_rules=list(row.contributing_rules_json or []),
        aggregator=row.aggregator,
        max_value=row.max_value,
        period=row.period,
    )


@router.get("", response_model=list[PolicySetResponse])
async def list_policy_sets(session: AsyncSession = Depends(get_session)) -> list[PolicySetResponse]:
    repo = PolicySetRepository(session)
    policy_sets = await repo.list_all()
    return [_to_response(ps) for ps in policy_sets]


@router.post("", response_model=PolicySetResponse, status_code=201)
async def create_policy_set(
    body: CreatePolicySetRequest, session: AsyncSession = Depends(get_session)
) -> PolicySetResponse:
    repo = PolicySetRepository(session)
    if await repo.get_by_key(body.key) is not None:
        raise HTTPException(status_code=409, detail=f"policy set '{body.key}' already exists")
    policy_set = await repo.create(
        key=body.key,
        name=body.name,
        owner=body.owner,
        description=body.description,
        category=body.category,
        tags=body.tags,
        accountable_owner=body.accountable_owner,
        delegate_approver=body.delegate_approver,
        escalation_contact=body.escalation_contact,
        consulted_parties=body.consulted_parties,
        informed_parties=body.informed_parties,
    )
    await session.commit()
    return _to_response(policy_set)


@router.get("/portfolio/summary")
async def portfolio_summary(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Decision-useful operational state for every project in one round trip.

    The Projects register is a portfolio surface, so it should not download full
    document, candidate, version, test, and quality collections per project merely
    to discard every field except a count. Published-version and quality state are
    resolved here at their owning persistence boundary.
    """
    rows = (
        await session.execute(
            text(
                """
                WITH active_versions AS (
                  SELECT DISTINCT ON (policy_set_id)
                    id,
                    policy_set_id,
                    version_number,
                    approved_at
                  FROM approved_policy_versions
                  WHERE is_active
                  ORDER BY policy_set_id, version_number DESC
                ),
                latest_quality AS (
                  SELECT DISTINCT ON (policy_set_id)
                    qr.policy_set_id,
                    qr.scope,
                    qr.rule_count,
                    qr.high_count,
                    qr.medium_count,
                    qr.low_count,
                    qr.run_at
                  FROM quality_runs qr
                  LEFT JOIN active_versions av
                    ON av.policy_set_id = qr.policy_set_id
                  -- Published-scope results still have to belong to the version
                  -- that is actually live, or an evaluation of a superseded
                  -- package would be reported as the current one.
                  --
                  -- Every other scope is admitted. This filter used to read
                  -- `WHERE qr.scope = 'published'`, which discarded every quality
                  -- run that exists on a portfolio where nothing has been
                  -- published: the checks ran, found real problems, stored them,
                  -- and the register said "Not evaluated" over the top of them.
                  WHERE qr.scope <> 'published'
                     OR (av.id IS NOT NULL AND av.version_number = qr.version_number)
                  ORDER BY qr.policy_set_id, qr.run_at DESC
                )
                SELECT
                  ps.key,
                  -- What document this set governs, by its bytes.
                  --
                  -- The register grew a row per extraction because the product
                  -- has no run-within-a-project, so re-running meant making a
                  -- new set. Grouping needs an identity for "the same
                  -- document", and titles cannot supply one: they carry the
                  -- run's own annotation, so one file appears as "AIS Employee
                  -- Handbook", "AIS Handbook v3" and so on. The content hash is
                  -- the file itself and is the only identity here that does not
                  -- depend on what somebody typed.
                  (SELECT dv.content_hash FROM source_documents d
                     JOIN document_versions dv ON dv.document_id = d.id
                    WHERE d.policy_set_id = ps.id
                    ORDER BY dv.version_number DESC
                    LIMIT 1) AS document_content_hash,
                  (SELECT d.title FROM source_documents d
                    WHERE d.policy_set_id = ps.id
                    ORDER BY d.created_at ASC
                    LIMIT 1) AS document_title,
                  -- Runs reach a set through the document version they ran on;
                  -- extraction_runs carries no policy_set_id of its own.
                  (SELECT count(*) FROM extraction_runs er
                     JOIN document_versions dv2 ON dv2.id = er.document_version_id
                     JOIN source_documents d2 ON d2.id = dv2.document_id
                    WHERE d2.policy_set_id = ps.id) AS run_count,
                  (SELECT count(*) FROM source_documents d
                    WHERE d.policy_set_id = ps.id) AS document_count,
                  (SELECT count(*) FROM candidate_rules c
                    WHERE c.policy_set_id = ps.id
                      AND c.review_status = 'candidate'
                      AND c.superseded_at IS NULL) AS review_pending,
                  -- The current generation's size and how its records are routed.
                  --
                  -- active_rule_count below counts PUBLISHED rules, which is 0 for
                  -- every project that has not been published yet. Reporting that as
                  -- a project's content made a set holding hundreds of records under
                  -- review read as empty, on the same row as a badge counting them.
                  -- Both numbers were true; they measure different lifecycle stages,
                  -- and the register showed the one the work has not reached yet.
                  --
                  -- Superseded rows are excluded for the same reason the review queue
                  -- excludes them: a re-extracted document keeps its earlier
                  -- generations for delta comparison, and counting them would report
                  -- a project as several times its real size.
                  (SELECT count(*) FROM candidate_rules c
                    WHERE c.policy_set_id = ps.id
                      AND c.superseded_at IS NULL) AS live_candidate_count,
                  -- Counted per route rather than as a ratio of one to the other, and
                  -- neither is subtracted from the other. A record whose mode is
                  -- absent or is some mode added later belongs to neither count, so
                  -- the two never silently sum to the whole and the caller can see
                  -- when they do not.
                  (SELECT count(*) FROM candidate_rules c
                    WHERE c.policy_set_id = ps.id
                      AND c.superseded_at IS NULL
                      AND c.payload_json->>'evaluation_mode' = 'deterministic')
                    AS candidate_direct_count,
                  (SELECT count(*) FROM candidate_rules c
                    WHERE c.policy_set_id = ps.id
                      AND c.superseded_at IS NULL
                      AND c.payload_json->>'evaluation_mode' = 'ai_ready')
                    AS candidate_reading_count,
                  (SELECT count(*) FROM approved_policy_versions v
                    WHERE v.policy_set_id = ps.id) AS version_count,
                  av.version_number AS active_version_number,
                  av.approved_at AS last_published_at,
                  (SELECT count(*) FROM approved_rules ar
                    WHERE ar.policy_version_id = av.id) AS active_rule_count,
                  (SELECT count(*) FROM approved_rules ar
                    WHERE ar.policy_version_id = av.id
                      AND ar.machine_executable) AS machine_executable_count,
                  (SELECT count(*) FROM policy_tests t
                    WHERE t.policy_set_id = ps.id) AS test_count,
                  (SELECT count(*) FROM policy_tests t
                    WHERE t.policy_set_id = ps.id
                      AND t.is_active) AS regression_test_count,
                  lq.high_count AS latest_quality_high,
                  lq.medium_count AS latest_quality_medium,
                  lq.low_count AS latest_quality_low,
                  lq.run_at AS latest_quality_at,
                  -- What that evaluation was about. A code, not a sentence: the
                  -- surface decides how to say "this describes the candidate
                  -- generation" versus "this describes the published package",
                  -- and the two must not be conflated now that both can appear.
                  lq.scope AS latest_quality_scope,
                  lq.rule_count AS latest_quality_rule_count
                FROM policy_sets ps
                LEFT JOIN active_versions av ON av.policy_set_id = ps.id
                LEFT JOIN latest_quality lq ON lq.policy_set_id = ps.id
                ORDER BY lower(ps.name), ps.key
                """
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


@router.patch("/{key}", response_model=PolicySetResponse)
async def update_policy_set(
    key: str, body: UpdatePolicySetRequest, session: AsyncSession = Depends(get_session)
) -> PolicySetResponse:
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    policy_set = await repo.update_metadata(
        policy_set,
        name=body.name,
        description=body.description,
        category=body.category,
        tags=body.tags,
        review_due_date=body.review_due_date,
        clear_review_due_date=body.clear_review_due_date,
        accountable_owner=body.accountable_owner,
        delegate_approver=body.delegate_approver,
        escalation_contact=body.escalation_contact,
        consulted_parties=body.consulted_parties,
        informed_parties=body.informed_parties,
    )
    await session.commit()
    return _to_response(policy_set)


@router.post("/{key}/review", response_model=PolicySetResponse)
async def mark_policy_set_reviewed(
    key: str, body: MarkPolicySetReviewedRequest, session: AsyncSession = Depends(get_session)
) -> PolicySetResponse:
    """Attest that a human just reviewed this policy set (ISO 37301 §9.3).

    Stamps `last_reviewed_at` to now and, if `next_due_date` is supplied,
    advances `review_due_date` to the next cycle in the same call — so
    "reviewed today, next check in a year" is one request, not two.
    """
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    policy_set = await repo.mark_reviewed(policy_set, next_due_date=body.next_due_date)
    await session.commit()
    return _to_response(policy_set)


@router.get("/{key}", response_model=PolicySetResponse)
async def get_policy_set(key: str, session: AsyncSession = Depends(get_session)) -> PolicySetResponse:
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    return _to_response(policy_set)


@router.delete("/{key}")
async def delete_policy_set_endpoint(
    key: str,
    actor: str,
    confirm: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete a policy set and everything scoped to it.

    Projects are meant to be disposable -- created and dropped freely -- but
    there was no way to drop one from the product, so teardown meant running SQL
    against the database by hand.

    `confirm` must repeat the key. A delete that takes hundreds of extracted
    rules with it should not be reachable by a mistyped URL or a stray click,
    and echoing the name is the cheapest guard that cannot be satisfied by
    accident.

    Returns a body rather than 204. The operator needs to see what actually
    went -- in particular `search_index`, which reports `clean`, `skipped` or
    `orphaned` rather than a count that cannot distinguish "nothing to remove"
    from "we could not remove it".
    """

    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    if confirm != key:
        raise HTTPException(
            status_code=400,
            detail=(
                f"confirmation does not match: to delete policy set '{key}', "
                f"pass confirm={key}"
            ),
        )

    outcome, search_ids = await delete_policy_set(session, policy_set, actor=actor)
    await session.commit()

    # After the commit, and outside the transaction: this is a network call to
    # another service, and a slow or unavailable Search resource must not hold a
    # database transaction open. The rows are already gone, so a failure here is
    # reported as `orphaned` rather than pretended away.
    settings = get_settings()
    if not search_ids:
        outcome.search_documents_deleted = 0
    elif settings.ai_enabled and settings.search_enabled:
        try:
            await AzureSearchClient(settings).delete_documents(
                settings.azure_search_authoring_index, search_ids
            )
            outcome.search_documents_deleted = len(search_ids)
        except Exception as exc:  # noqa: BLE001 - reported, never raised past the delete
            outcome.search_index_error = str(exc)

    return {
        "key": outcome.policy_set_key,
        "name": outcome.policy_set_name,
        "rows_deleted": outcome.rows_deleted,
        "total_rows_deleted": outcome.total_rows,
        "search_index": outcome.search_index_state,
        "search_documents_identified": outcome.search_documents_identified,
        "search_documents_deleted": outcome.search_documents_deleted,
        "search_index_error": outcome.search_index_error,
        "retained": dict(RETAINED_TABLES),
    }


@router.get("/{key}/workspace-counts")
async def get_workspace_counts(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Badge counts for the project workspace's tab strip.

    One endpoint and one round trip for all of them, counted in the database.
    The alternative the UI reached for first is to call each feature's list
    endpoint and read `.length`, which is what `ProjectOverviewTab` does for its
    three figures. That does not survive being generalised to a whole tab strip:
    it is a request per tab on every project open, and each one transfers an
    entire collection — hundreds of fully-serialised candidate rules, with their
    payloads — so the browser can discard everything but the row count.

    Counts are deliberately "what a reviewer would consider outstanding" rather
    than raw table totals, because that is what a badge is read as:

      * `review_pending` excludes superseded candidates. A re-extraction
        supersedes the previous run's rows rather than deleting them, so a raw
        count would keep charging the reviewer for work that is no longer on
        their queue and would only ever grow.
      * `review_pending_policies` counts the same outstanding work in the unit
        it is decided in. A reviewer approves a policy, not a rule, so the rule
        count answers a question they are not asking and a badge carrying it
        overstates how many decisions are ahead. It is a second number rather
        than a replacement because both are true and they are not derivable
        from one another.

        A pending candidate that is attached to no provision is its own unit:
        nothing groups it, so it is one more thing to decide. Adding it to the
        distinct-provision count is therefore not double-counting — the two
        `count`s partition the pending rows on whether `provision_id` is null,
        and every pending row is in exactly one of them. Dropping the second
        would let a queue that plainly holds work badge nothing.
      * `policies` counts rules in the *active* version, not every approved rule
        ever published; approved versions are immutable and accumulate.
      * `exceptions_open` counts undecided requests only — a decided exception
        is history, not a task.
    """
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    row = (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM source_documents WHERE policy_set_id = :sid) AS documents,
                  (SELECT count(*) FROM candidate_rules
                     WHERE policy_set_id = :sid
                       AND review_status = 'candidate'
                       AND superseded_at IS NULL) AS review_pending,
                  (SELECT count(DISTINCT provision_id) FROM candidate_rules
                     WHERE policy_set_id = :sid
                       AND review_status = 'candidate'
                       AND superseded_at IS NULL
                       AND provision_id IS NOT NULL)
                  + (SELECT count(*) FROM candidate_rules
                       WHERE policy_set_id = :sid
                         AND review_status = 'candidate'
                         AND superseded_at IS NULL
                         AND provision_id IS NULL) AS review_pending_policies,
                  (SELECT count(*) FROM approved_rules ar
                     JOIN approved_policy_versions v ON ar.policy_version_id = v.id
                     WHERE v.policy_set_id = :sid AND v.is_active) AS policies,
                  (SELECT count(*) FROM approved_policy_versions WHERE policy_set_id = :sid) AS versions,
                  (SELECT count(*) FROM policy_aggregate_limits WHERE policy_set_id = :sid) AS limits,
                  (SELECT count(*) FROM policy_tests WHERE policy_set_id = :sid) AS tests,
                  (SELECT count(*) FROM policy_tests
                     WHERE policy_set_id = :sid AND is_active) AS regression_tests,
                  (SELECT count(*) FROM policy_exceptions
                     WHERE policy_set_id = :sid AND decision = 'pending') AS exceptions_open,
                  (SELECT count(*) FROM correlation_findings WHERE policy_set_id = :sid) AS correlation_findings,
                  (SELECT count(*) FROM evaluations WHERE policy_set_id = :sid) AS decisions
                """
            ),
            {"sid": policy_set.id},
        )
    ).mappings().one()

    return dict(row)


@router.get("/{key}/trusted-config")
async def get_trusted_config(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    """The policy set's Section 83 trusted configuration (its fact model).

    Returned alongside `warnings` so an author sees the same shape problems the
    extraction would hit, without having to run one to find out.
    """
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    config = policy_set.trusted_config_json or {}
    return {
        "policy_set_key": policy_set.key,
        "trusted_config": config,
        "warnings": check_trusted_config(config),
        "fact_count": len(config.get("fact_model") or {}),
        "output_count": len(config.get("output_model") or {}),
    }


@router.put("/{key}/trusted-config")
async def put_trusted_config(
    key: str, body: UpdateTrustedConfigRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Replace the policy set's trusted configuration.

    A full replace rather than a merge: a fact model is read as a whole by the
    agent, and a merge would make removing a wrong mapping impossible through
    this endpoint — the one operation an author most needs after discovering a
    term was mapped incorrectly.

    Shape problems are returned as `warnings`, not raised. Section 83 is the
    spec's key list rather than the model's, so an unrecognised key must not
    block saving; and a partially-correct fact model is still strictly better
    than none. The caller is told exactly what will be ignored.
    """
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    config = body.trusted_config or {}
    policy_set.trusted_config_json = config
    await session.commit()
    await session.refresh(policy_set)
    return {
        "policy_set_key": policy_set.key,
        "trusted_config": policy_set.trusted_config_json,
        "warnings": check_trusted_config(config),
        "fact_count": len(config.get("fact_model") or {}),
        "output_count": len(config.get("output_model") or {}),
    }


@router.get("/{key}/versions", response_model=list[ApprovedPolicyVersionResponse])
async def list_policy_versions(
    key: str, session: AsyncSession = Depends(get_session)
) -> list[ApprovedPolicyVersionResponse]:
    """All versions of a policy set (active and superseded), newest first.

    Powers the admin UI's version-history timeline — distinct from
    `/active-version`, which only ever returns the single current version.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    versions = await version_repo.list_all_versions(policy_set.id)
    return [
        ApprovedPolicyVersionResponse(
            id=str(v.id),
            policy_set_id=str(v.policy_set_id),
            version_number=v.version_number,
            effective_from=v.effective_from,
            effective_to=v.effective_to,
            is_active=v.is_active,
            approved_by=v.approved_by,
            approved_at=v.approved_at,
            rule_count=len(v.rules),
        )
        for v in versions
    ]


@router.get("/{key}/versions/{version_id}/rules", response_model=list[CanonicalRule])
async def get_policy_version_rules(
    key: str, version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[CanonicalRule]:
    """Full canonical rule detail for one version — used to render readable rule cards.

    (`/versions` intentionally omits rule bodies to stay lightweight; this
    endpoint is the drill-down.)
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    return package.rules


@router.get("/{key}/versions/{version_id}/policies")
async def get_policy_version_policies(
    key: str, version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """One published version as policies rather than as loose rules.

    The published counterpart of `/policy-sets/{key}/policies`, and deliberately
    the same payload: a reviewer who has read a policy in the queue and a reader
    who looks it up after publication are looking at the same thing, and the
    second surface should not have to reconstruct from a flat list what the
    first was handed. `/versions/{version_id}/rules` returns the records, which
    is what an evaluator consumes; this returns those same records arranged
    under the provision that states them, which is what a person reads. The rule
    ids here index into the ids there, so a client holding both needs no third
    fetch.

    Nothing is re-grouped. Publishing copies the provision key and its heading
    chain onto each rule, so the boundary a reviewer approved is the boundary
    shown here — this reads it back rather than deriving a second opinion on it.
    A rule published before that link existed falls through to the same heading
    fallback the queue uses, which keeps it grouped rather than dropped.
    """

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    groupings = await approved_provision_groupings(session, policy_set.id, version.rules)
    policies = assemble(package.rules, provisions=groupings)
    # One query for the whole page, read and never generated — the same
    # contract the queue holds. A published policy with no stored label carries
    # none rather than acquiring one on the way to the screen.
    topic_labels = await labels_for_policy_set(session, policy_set.id)

    def _rule(rule) -> dict:
        return {
            "rule_id": rule.rule_id,
            "title": rule.title,
            "evaluation_mode": rule.evaluation_mode.value,
        }

    return [
        {
            "key": policy.key,
            "heading": policy.heading,
            "heading_path": list(policy.heading_path),
            "topic_label": (
                topic_labels[policy.key].as_payload()
                if policy.key in topic_labels
                else None
            ),
            "persisted": policy.persisted,
            "provision_id": policy.provision_id,
            "document_version_id": policy.document_version_id,
            "source_elements": policy.source_elements,
            "page": policy.page,
            "rule_count": policy.rule_count,
            "passage_count": policy.passage_count,
            "route": policy.route,
            "passages": [
                {
                    "key": passage.key,
                    "source_elements": passage.source_elements,
                    "page": passage.page,
                    "rule_count": passage.rule_count,
                    "rules": [_rule(rule) for rule in passage.rules],
                }
                for passage in policy.passages
            ],
            "rules": [_rule(rule) for rule in policy.rules],
        }
        for policy in policies
    ]


@router.get("/{key}/provisions/{provision_key}/history")
async def get_provision_history(
    key: str, provision_key: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """One policy, traced across every published version it appears in.

    A policy is not a row that gets updated. `document_provisions.id` belongs to
    a single document version and cannot follow it; `provision_key` can, because
    publishing copies the key onto every rule and the same key recurs when the
    same policy is published again. So this reads the sightings of a key rather
    than the revisions of a record.

    The oldest sighting is reported as `first_seen`, never as `added`. Rules
    published before the provision link existed carry no key at all, so an
    absence from an earlier version can mean the policy was not there *or* that
    nothing recorded it as being there, and only the first of those would
    justify calling it an addition.

    Comparison runs between consecutive sightings of this key, which may be
    several versions apart, rather than between adjacent versions of the set: a
    policy absent from the version in between has not changed *in* that version,
    and saying so would attribute movement to a version that never held it.

    An empty list means the key has never been published. That is an answer, not
    a 404 — a candidate policy has no publication history yet.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    sightings = await policy_history(session, policy_set.id, provision_key)
    return [
        {
            "version_id": sighting.version_id,
            "version_number": sighting.version_number,
            "is_active": sighting.is_active,
            "approved_by": sighting.approved_by,
            "approved_at": sighting.approved_at,
            "heading_path": sighting.heading_path,
            "change": sighting.change,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "fingerprint": rule.fingerprint,
                }
                for rule in sighting.rules
            ],
            "rules_added": sighting.rules_added,
            "rules_removed": sighting.rules_removed,
            "rules_reworded": sighting.rules_reworded,
        }
        for sighting in sightings
    ]


@router.get("/{key}/versions/{version_id}/aggregate-limits", response_model=list[AggregateLimit])
async def get_policy_version_aggregate_limits(
    key: str, version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[AggregateLimit]:
    """Immutable aggregate limits snapshotted into this published version.

    Distinct from `/aggregate-limits` (this policy set's mutable *draft*
    definitions) — this is what was actually in effect as of this version,
    exactly like `/versions/{version_id}/rules` vs. the candidate-rule draft
    endpoints.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    return package.aggregate_limits


@router.get("/{key}/aggregate-limits", response_model=list[AggregateLimitResponse])
async def list_aggregate_limits(
    key: str, session: AsyncSession = Depends(get_session)
) -> list[AggregateLimitResponse]:
    """Mutable draft aggregate limits — the policy set's current desired state.

    Edited directly by a Policy Manager (no per-candidate review workflow),
    and snapshotted verbatim into `ApprovedAggregateLimit` at publish time.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    rows = await repo.list_by_policy_set(policy_set.id)
    return [_aggregate_limit_to_response(r) for r in rows]


async def _active_package_or_404(key: str, session: AsyncSession):
    """The active published package for `key`, or a 404 explaining which half
    is missing. Both the eligibility and preview endpoints need exactly this,
    and an unpublished policy set is a legitimate state rather than an error —
    so the message says which of the two things is absent."""

    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    version = await ApprovedPolicyVersionRepository(session).get_active_version(policy_set.id)
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"policy set '{key}' has no active published version; "
                "combined caps are evaluated against published rules"
            ),
        )
    return approved_policy_version_to_package(version), version


@router.get("/{key}/aggregate-limits/eligibility", response_model=AggregateEligibilityResponse)
async def get_aggregate_limit_eligibility(
    key: str, session: AsyncSession = Depends(get_session)
) -> AggregateEligibilityResponse:
    """Which published rules could actually contribute to a combined cap.

    Deterministic and AI-free by design. The evaluator drops a contribution
    silently when the rule cannot be SATISFIED or when the amount fact is not
    numeric, so a cap built over ineligible rules saves, publishes and then
    does nothing. Answering this up front is what stops that.
    """

    package, _ = await _active_package_or_404(key, session)
    return AggregateEligibilityResponse(**assess_rules(list(package.rules)).to_dict())


@router.post("/{key}/aggregate-limits/propose", response_model=ProposeAggregateLimitsResponse)
async def propose_aggregate_limits_for_set(
    key: str,
    body: ProposeAggregateLimitsRequest,
    session: AsyncSession = Depends(get_session),
) -> ProposeAggregateLimitsResponse:
    """Ask the model to find rule groups that share one finite pool.

    Proposals are returned, never saved. An aggregate limit changes the outcome
    of every future evaluation against this policy set, so it takes a human
    decision — the same stance `propose_policy_tests` takes for tests.
    """

    try:
        result = await propose_aggregate_limits(
            session,
            policy_set_key=key,
            reasoning_effort=body.reasoning_effort,
            guidance=body.guidance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ProposeAggregateLimitsResponse(**result)


@router.post("/{key}/aggregate-limits/preview", response_model=PreviewAggregateLimitResponse)
async def preview_aggregate_limit_for_set(
    key: str,
    body: PreviewAggregateLimitRequest,
    session: AsyncSession = Depends(get_session),
) -> PreviewAggregateLimitResponse:
    """Run a draft cap through the real evaluator without saving it.

    The draft is spliced into an in-memory copy of the published package and
    `evaluate_policy` decides the outcome, so the preview cannot disagree with
    what publishing would actually do.
    """

    package, _ = await _active_package_or_404(key, session)
    result = preview_aggregate_limit(
        package,
        contributing_rules=[c.model_dump(mode="json") for c in body.contributing_rules],
        max_value=body.max_value,
        facts=body.facts,
        description=body.description,
    )
    return PreviewAggregateLimitResponse(**result)


@router.post("/{key}/aggregate-limits", response_model=AggregateLimitResponse, status_code=201)
async def create_aggregate_limit(
    key: str, body: CreateAggregateLimitRequest, session: AsyncSession = Depends(get_session)
) -> AggregateLimitResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    if await repo.get_by_key(policy_set.id, body.aggregate_key) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"aggregate limit '{body.aggregate_key}' already exists for policy set '{key}'",
        )
    row = await repo.create(
        policy_set_id=policy_set.id,
        aggregate_key=body.aggregate_key,
        description=body.description,
        contributing_rules=[c.model_dump(mode="json") for c in body.contributing_rules],
        aggregator=body.aggregator,
        max_value=body.max_value,
        period=body.period,
    )
    await session.commit()
    return _aggregate_limit_to_response(row)


@router.put("/{key}/aggregate-limits/{aggregate_key}", response_model=AggregateLimitResponse)
async def update_aggregate_limit(
    key: str,
    aggregate_key: str,
    body: UpdateAggregateLimitRequest,
    session: AsyncSession = Depends(get_session),
) -> AggregateLimitResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    row = await repo.get_by_key(policy_set.id, aggregate_key)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"aggregate limit '{aggregate_key}' not found for policy set '{key}'"
        )
    row = await repo.update(
        row,
        description=body.description,
        contributing_rules=[c.model_dump(mode="json") for c in body.contributing_rules],
        aggregator=body.aggregator,
        max_value=body.max_value,
        period=body.period,
    )
    await session.commit()
    return _aggregate_limit_to_response(row)


@router.delete("/{key}/aggregate-limits/{aggregate_key}", status_code=204)
async def delete_aggregate_limit(
    key: str, aggregate_key: str, session: AsyncSession = Depends(get_session)
) -> Response:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    row = await repo.get_by_key(policy_set.id, aggregate_key)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"aggregate limit '{aggregate_key}' not found for policy set '{key}'"
        )
    await repo.delete(row)
    await session.commit()
    return Response(status_code=204)


@router.get("/{key}/versions/{version_id}/export")
async def export_policy_version_rules(
    key: str,
    version_id: uuid.UUID,
    format: ExportFormat = "json",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download every rule in one approved version as JSON, JSONL, or CSV.

    Verbatim structural export: no rule field is reworded or summarized,
    only re-serialized — safe for audit/archival use or hand-off to another
    system.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    content = models_to_export(package.rules, format)
    filename = f"{key}-v{version.version_number}-rules.{extension_for(format)}"
    return Response(
        content=content, media_type=media_type_for(format), headers=content_disposition(filename)
    )


@router.post(
    "/{key}/versions",
    response_model=ApprovedPolicyVersionResponse,
    status_code=201,
)
async def import_policy_version(
    key: str, body: ImportPolicyVersionRequest, session: AsyncSession = Depends(get_session)
) -> ApprovedPolicyVersionResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version = await import_approved_policy_version(
        session,
        policy_set_id=policy_set.id,
        version_number=body.version_number,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        approved_by=body.approved_by,
        is_active=body.is_active,
        rules=body.rules,
        aggregate_limits=body.aggregate_limits,
    )
    await session.commit()
    return ApprovedPolicyVersionResponse(
        id=str(version.id),
        policy_set_id=str(version.policy_set_id),
        version_number=version.version_number,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        is_active=version.is_active,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        rule_count=len(body.rules),
    )


@router.get("/{key}/active-version", response_model=ApprovedPolicyVersionResponse)
async def get_active_version(key: str, session: AsyncSession = Depends(get_session)) -> ApprovedPolicyVersionResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_active_version(policy_set.id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"no active approved version for policy set '{key}'")

    return ApprovedPolicyVersionResponse(
        id=str(version.id),
        policy_set_id=str(version.policy_set_id),
        version_number=version.version_number,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        is_active=version.is_active,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        rule_count=len(version.rules),
    )
