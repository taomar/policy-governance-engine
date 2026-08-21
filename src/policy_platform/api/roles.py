"""Role and capability vocabulary for the RBAC layer.

Three roles, ordered by ascending privilege. The middle tier is called
``policy_author`` rather than "policy reviewer" because *review* already
means *approve or reject an extracted candidate rule* throughout this
codebase — the Review workspace tab, the ``ReviewQueue`` component, and
the ``/review`` endpoints all use that word in that narrower sense. Using
it again for a role would make "reviewer" mean two unrelated things in
the same conversation, and the disambiguation cost falls on every future
reader of every mention.

Capability bands describe *what kind of change* an operation makes, not
*which HTTP verb* it uses. The classification is deliberately decoupled
from verbs because 19 of the 48 write operations are ``POST /api/ai/…``
and about half of those mutate nothing — they are POST only because they
carry a request body.
"""
from __future__ import annotations

from typing import Final

# ── roles, lowest → highest privilege ────────────────────────────────
VIEWER: Final[str] = "viewer"
POLICY_AUTHOR: Final[str] = "policy_author"
ADMIN: Final[str] = "admin"

#: Explicit privilege ordering. Index position determines rank: a higher
#: index satisfies every requirement at a lower index.
_ROLE_RANK: Final[dict[str, int]] = {
    VIEWER: 0,
    POLICY_AUTHOR: 1,
    ADMIN: 2,
}

#: Every role a refusal can name, declared explicitly so it can be enumerated.
#:
#: Same reasoning as ``ACTOR_ROLES`` in ``actor_role.py``: a vocabulary that
#: cannot be enumerated cannot be checked, and an unchecked vocabulary is how a
#: role identifier reaches a reader as a raw string. A cross-language guard
#: walks this tuple and fails when a member has no wording in
#: ``apps/web/src/actorRole.ts``, so adding a role here without adding words for
#: it is caught rather than shipped.
ALL_ROLES: Final[tuple[str, ...]] = (VIEWER, POLICY_AUTHOR, ADMIN)

#: The refusal code the capability layer raises.
#:
#: Named here rather than written inline where it is raised, because a literal
#: repeated between the server and the interface is precisely the drift the
#: refusal codes were introduced to remove — and it had already begun: this
#: value existed only as a string inside ``authz.py``, so nothing could assert
#: the interface recognised it, and the interface did not.
RBAC_REFUSAL: Final[str] = "rbac_insufficient"

# ── capability bands ────────────────────────────────────────────────
#: Returns data or computes; changes nothing.
READ: Final[str] = "READ"
#: Appends a record that something was *run*; no governed content altered.
USE: Final[str] = "USE"
#: Changes governed content — documents, candidates, versions, publication.
AUTHOR: Final[str] = "AUTHOR"
#: Changes configuration, assigns roles, or destroys.
ADMINISTER: Final[str] = "ADMINISTER"

#: Minimum role required for each band.
BAND_MINIMUM_ROLE: Final[dict[str, str]] = {
    READ: VIEWER,
    USE: VIEWER,
    AUTHOR: POLICY_AUTHOR,
    ADMINISTER: ADMIN,
}


def role_satisfies(actual: str, *, minimum: str) -> bool:
    """True when *actual* meets or exceeds *minimum* in the privilege ordering.

    Unknown roles satisfy nothing — default closed. An unrecognised value
    must not silently receive any access, because the alternative is that
    a typo or a renamed claim grants permissions the operator never
    intended.
    """
    actual_rank = _ROLE_RANK.get(actual)
    minimum_rank = _ROLE_RANK.get(minimum)
    if actual_rank is None or minimum_rank is None:
        return False
    return actual_rank >= minimum_rank
