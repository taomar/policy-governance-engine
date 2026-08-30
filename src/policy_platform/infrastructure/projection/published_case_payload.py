"""Published ``grounding_projection_v1`` payloads for the active policy version.

Candidate rules keep the whole canonical payload as JSON; approved rules do not.
The reconstruction therefore delegates to the existing approved-version mapper,
which is already the inverse of the publish/import path and restores the
canonical rule from the approved-rule columns plus evidence/exception rows.
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.domain.models import ApprovedPolicyVersion, ApprovedRule, PolicySet
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.projection.policy_case_payload import build_case_payload


def _uuid_or_none(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


async def _policy_set_id_for(session: AsyncSession, policy_set_id: object) -> uuid.UUID | None:
    parsed = _uuid_or_none(policy_set_id)
    if parsed is not None:
        return parsed

    result = await session.execute(select(PolicySet.id).where(PolicySet.key == str(policy_set_id)))
    return result.scalar_one_or_none()


async def active_version_for_policy_set(
    session: AsyncSession, policy_set_id: object
) -> ApprovedPolicyVersion | None:
    """Return the active approved version for a policy set id or key."""

    resolved = await _policy_set_id_for(session, policy_set_id)
    if resolved is None:
        return None

    stmt = (
        select(ApprovedPolicyVersion)
        .where(
            ApprovedPolicyVersion.policy_set_id == resolved,
            ApprovedPolicyVersion.is_active.is_(True),
        )
        .options(
            selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
            selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
            selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
        )
        .order_by(ApprovedPolicyVersion.version_number.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _published_rules(version: ApprovedPolicyVersion) -> list[tuple[ApprovedRule, CanonicalRule]]:
    package = approved_policy_version_to_package(version)
    canonical_by_rule_id = {rule.rule_id: rule for rule in package.rules}
    approved = sorted(
        version.rules,
        key=lambda rule: (rule.provision_key or "", rule.rule_id, rule.revision),
    )
    return [(rule, canonical_by_rule_id[rule.rule_id]) for rule in approved]


def _payload_for_group(
    *,
    version: ApprovedPolicyVersion,
    provision_key: str,
    heading_path: list[str],
    rules: list[CanonicalRule],
) -> dict:
    payload = build_case_payload(
        policy_set_id=str(version.policy_set_id),
        provision_id=None,
        provision_key=provision_key,
        heading_path=heading_path,
        rules=rules,
    )

    version_effective_from = str(version.effective_from)
    version_effective_to = None if version.effective_to is None else str(version.effective_to)
    envelope = payload["envelope"]
    envelope["policy_version_id"] = str(version.id)
    envelope["version_number"] = version.version_number
    envelope["effective_from"] = version_effective_from
    envelope["effective_to"] = version_effective_to

    for projected, rule in zip(payload["rules"], rules):
        if str(rule.effective_from) != version_effective_from:
            projected["effective_from"] = str(rule.effective_from)
        else:
            projected.pop("effective_from", None)

        rule_effective_to = None if rule.effective_to is None else str(rule.effective_to)
        if rule_effective_to != version_effective_to:
            projected["effective_to"] = rule_effective_to
        else:
            projected.pop("effective_to", None)

    return payload


def governing_extras_for_group(rules: list[CanonicalRule]) -> dict:
    """The governing fields the lean payload deliberately does not carry.

    `build_case_payload` drops `authority` and `priority`: the gather never reads
    them, so putting them in the model-facing record would only cost budget. But
    they *are* governing — a `PolicyAuthority` is a level, an owner and a
    precedence rank, and two otherwise identical statements issued under
    different authority are two policies, not one said twice.

    That matters to exactly one caller: the pass that decides whether two
    published policies are the same policy and may share one answer slot. It is
    returned beside the payload rather than inside it so the record the model
    reads is byte-for-byte what it always was, while the equivalence test still
    sees everything that governs.

    Per rule and in rule order, because "rule 1 is the board's and rule 2 is the
    unit's" is a different policy from the reverse.
    """

    return {
        "authority": [
            None
            if rule.authority is None
            else {
                "level": rule.authority.level,
                "owner": rule.authority.owner,
                "rank": rule.authority.rank,
            }
            for rule in rules
        ],
        "priority": [rule.priority for rule in rules],
    }


def _group_payloads(
    version: ApprovedPolicyVersion, rows: Iterable[tuple[ApprovedRule, CanonicalRule]]
) -> list[dict]:
    return [payload for payload, _ in _group_payloads_with_extras(version, rows)]


def _group_payloads_with_extras(
    version: ApprovedPolicyVersion, rows: Iterable[tuple[ApprovedRule, CanonicalRule]]
) -> list[tuple[dict, dict]]:
    grouped: OrderedDict[str, tuple[list[str], list[CanonicalRule]]] = OrderedDict()

    for approved, canonical in rows:
        if not approved.provision_key:
            raise ValueError(
                "active approved version "
                f"{version.id} contains approved rule {approved.rule_id!r} without provision_key; "
                "a published policy payload cannot safely group it"
            )

        heading_path = list(approved.provision_heading_json or [])
        existing = grouped.get(approved.provision_key)
        if existing is None:
            grouped[approved.provision_key] = (heading_path, [canonical])
            continue
        if existing[0] != heading_path:
            raise ValueError(
                "active approved version "
                f"{version.id} contains conflicting headings for provision_key "
                f"{approved.provision_key!r}"
            )
        existing[1].append(canonical)

    return [
        (
            _payload_for_group(
                version=version,
                provision_key=provision_key,
                heading_path=heading_path,
                rules=rules,
            ),
            governing_extras_for_group(rules),
        )
        for provision_key, (heading_path, rules) in grouped.items()
    ]


async def published_case_payloads_for_policy_set(
    session: AsyncSession, policy_set_id: object
) -> list[dict]:
    """One published grounding payload per policy in the active approved version."""

    return [payload for payload, _ in await published_case_payloads_with_extras(session, policy_set_id)]


async def published_case_payloads_with_extras(
    session: AsyncSession, policy_set_id: object
) -> list[tuple[dict, dict]]:
    """Each published policy's payload beside the governing fields it omits.

    One read, two products. The payload is exactly what
    :func:`published_case_payloads_for_policy_set` returns; the extras are
    :func:`governing_extras_for_group`, which only the duplicate-policy
    equivalence test consumes.
    """

    version = await active_version_for_policy_set(session, policy_set_id)
    if version is None:
        return []

    return _group_payloads_with_extras(version, _published_rules(version))


async def published_case_payload_with_extras_for_policy(
    session: AsyncSession, policy_set_id: object, provision_key: str
) -> tuple[dict, dict] | None:
    """One policy's payload beside the governing fields it omits.

    The single-policy scope needs the extras for the same reason the project
    scope does: rule-level equivalence compares authority, and the lean record
    does not carry it. Without them a reviewer who names one policy would get a
    weaker duplicate test than a reviewer who names none.
    """

    version = await active_version_for_policy_set(session, policy_set_id)
    if version is None:
        return None

    rows = (
        (approved, canonical)
        for approved, canonical in _published_rules(version)
        if approved.provision_key == provision_key
    )
    found = _group_payloads_with_extras(version, rows)
    return found[0] if found else None
