"""One policy, traced across the versions it has been published in.

WHY A KEY AND NOT A ROW

`document_provisions.id` identifies a provision within a single document
version, so it cannot follow a policy from one published version to the next.
`provision_key` can: publishing copies it onto every approved rule, and the same
key recurs across versions when the same policy is published again. So a policy
is not a row that gets updated. It is a key, seen at a version, and its history
is the sequence of those sightings.

WHAT THIS REFUSES TO SAY

The earliest sighting is reported as *first seen*, never as *added*. Rules
published before the provision link existed carry no key, so an absence in an
older version can mean either that the policy was not there or that nothing
recorded it as being there. "Added in version 2" asserts the first; "first seen
in version 2" asserts only what was observed, which is all this can know.

A comparison is drawn only between consecutive sightings of the *same* key, not
between adjacent versions of the policy set. A policy can be absent from a
version in between, and a diff that ignored that would attribute a change to
whichever version happened to be next in the list.

Change is decided on what a reader would call the rule as stated — its wording,
its condition, its effect, its scope, the facts it names. Not on ids, revisions
or timestamps, which move for reasons that are not changes to the policy.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _canonical(value: Any) -> str:
    """A stable string for a JSON value, so equal content hashes equally."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def rule_fingerprint(row: Any) -> str:
    """What this rule says, reduced to a value that can be compared.

    Deliberately excludes `revision`, ids and timestamps. A rule republished
    unchanged into a new version is the same rule to a reader, and a history
    that called that a change would report movement where the document had
    none.
    """
    parts = [
        row.title or "",
        row.description or "",
        _canonical(row.condition_json),
        _canonical(row.effect_json),
        _canonical(row.scope_json),
        _canonical(row.required_facts_json),
        row.rule_type or "",
    ]
    return hashlib.sha256("\u0000".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class PolicyRuleSighting:
    rule_id: str
    title: str
    fingerprint: str


@dataclass
class PolicySighting:
    """The policy as one published version held it."""

    version_id: str
    version_number: int
    is_active: bool
    approved_by: str | None
    approved_at: Any
    heading_path: list[str]
    rules: list[PolicyRuleSighting] = field(default_factory=list)
    #: "first_seen" | "unchanged" | "changed" — against the previous sighting
    #: of this same key, which may be several versions back.
    change: str = "first_seen"
    rules_added: list[str] = field(default_factory=list)
    rules_removed: list[str] = field(default_factory=list)
    rules_reworded: list[str] = field(default_factory=list)


_SIGHTINGS_SQL = text(
    """
    SELECT
        apv.id                AS version_id,
        apv.version_number    AS version_number,
        apv.is_active         AS is_active,
        apv.approved_by       AS approved_by,
        apv.approved_at       AS approved_at,
        ar.rule_id            AS rule_id,
        ar.title              AS title,
        ar.description        AS description,
        ar.rule_type          AS rule_type,
        ar.condition_json     AS condition_json,
        ar.effect_json        AS effect_json,
        ar.scope_json         AS scope_json,
        ar.required_facts_json AS required_facts_json,
        ar.provision_heading_json AS provision_heading_json
    FROM approved_rules ar
    JOIN approved_policy_versions apv ON apv.id = ar.policy_version_id
    WHERE apv.policy_set_id = :policy_set_id
      AND ar.provision_key = :provision_key
    ORDER BY apv.version_number ASC, ar.rule_id ASC
    """
)


def _heading_path(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(entry) for entry in value]
    if isinstance(value, dict):
        path = value.get("heading_path") or value.get("path")
        if isinstance(path, list):
            return [str(entry) for entry in path]
    return []


async def policy_history(
    session: AsyncSession, policy_set_id: Any, provision_key: str
) -> list[PolicySighting]:
    """Every published version this policy appears in, oldest first.

    Returns an empty list when the key has never been published, which is a
    complete answer and not an error: a candidate policy has no publication
    history yet, and inventing one version so the tab has something in it would
    put a record on screen that no version holds.
    """
    result = await session.execute(
        _SIGHTINGS_SQL, {"policy_set_id": policy_set_id, "provision_key": provision_key}
    )

    by_version: dict[Any, PolicySighting] = {}
    for row in result:
        sighting = by_version.get(row.version_id)
        if sighting is None:
            sighting = PolicySighting(
                version_id=str(row.version_id),
                version_number=row.version_number,
                is_active=bool(row.is_active),
                approved_by=row.approved_by,
                approved_at=row.approved_at,
                heading_path=_heading_path(row.provision_heading_json),
            )
            by_version[row.version_id] = sighting
        sighting.rules.append(
            PolicyRuleSighting(
                rule_id=row.rule_id,
                title=row.title or "",
                fingerprint=rule_fingerprint(row),
            )
        )

    sightings = sorted(by_version.values(), key=lambda s: s.version_number)

    previous: PolicySighting | None = None
    for sighting in sightings:
        if previous is None:
            sighting.change = "first_seen"
            previous = sighting
            continue

        before = {rule.rule_id: rule.fingerprint for rule in previous.rules}
        after = {rule.rule_id: rule.fingerprint for rule in sighting.rules}

        sighting.rules_added = sorted(set(after) - set(before))
        sighting.rules_removed = sorted(set(before) - set(after))
        sighting.rules_reworded = sorted(
            rule_id
            for rule_id in set(before) & set(after)
            if before[rule_id] != after[rule_id]
        )
        moved = sighting.rules_added or sighting.rules_removed or sighting.rules_reworded
        sighting.change = "changed" if moved else "unchanged"
        previous = sighting

    return sightings
