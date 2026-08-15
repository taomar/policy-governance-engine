"""Refusals that turn on who is acting, as codes rather than sentences.

Two routers each carried their own copy of one sentence:

    "Only a Policy Manager can perform this action. Switch your acting role in
     the header."

and the interface carried a third, which had already drifted from both -- it
says "launch a new campaign" where the servers say "perform this action". Three
producers of one message is three places to edit for a copy change, two of
which need a deployment, and the drift had already happened without anyone
choosing it.

WHAT A CODE HAS TO CARRY. The reason the servers wrote a sentence is that the
sentence knows something the bare refusal does not: which role was needed, and
what the actor was trying to do. A code saying only "forbidden" would leave the
interface to guess the verb, and it would guess wrong on the page that already
words it differently. So the refusal carries the role it wanted and the action
it refused, both as identifiers, and the words for each live in
`apps/web/src/actorRole.ts` beside everything else a reader sees.

The two tuples below are declared explicitly rather than derived, for the same
reason `CONDITION_PROVENANCE_CODES` is: a test enumerates them and fails when
one gains a member the interface has no wording for. A set that cannot be
enumerated cannot be checked, and an unchecked vocabulary is how a code reaches
a reader as a raw identifier.
"""
from __future__ import annotations

from typing import Final

from fastapi import HTTPException

#: The one refusal shape this module raises. Named so the interface can tell it
#: from a 403 that means something else, without matching on prose.
ACTOR_ROLE_REFUSAL: Final[str] = "actor_role_insufficient"

#: Every role a refusal can name.
ACTOR_ROLES: Final[tuple[str, ...]] = ("policy_manager",)

#: Every action a refusal can name. An action is here because a reader needs
#: the verb: "you cannot do this" and "you cannot launch a campaign" are
#: different sentences, and only the second is worth reading.
GUARDED_ACTIONS: Final[tuple[str, ...]] = ("launch_attestation_campaign",)


def require_role(actor_role: str, *, required: str, action: str) -> None:
    """Refuse, in codes, when the acting role is not the one required.

    Raises a 403 whose `detail` is an object rather than a string. Every
    consumer of this API reads `detail`, so the shape change is visible; that
    is deliberate. A refusal that silently kept a `detail` string would have
    left the old sentence in place for anything that had not been updated, and
    the drift this replaces began exactly that way.
    """

    assert required in ACTOR_ROLES, f"{required!r} is not a declared role"
    assert action in GUARDED_ACTIONS, f"{action!r} is not a declared action"

    if actor_role == required:
        return

    raise HTTPException(
        status_code=403,
        detail={
            "code": ACTOR_ROLE_REFUSAL,
            "required_role": required,
            "action": action,
        },
    )
