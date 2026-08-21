"""Every role and action the server can refuse on has words in the interface.

The server sends `actor_role_insufficient` with a role identifier and an action
identifier. Neither is a sentence, so something has to turn them into one, and
that something is `apps/web/src/actorRole.ts`. A role or action added to the
Python tuples without a matching entry there reaches a reader as a raw
identifier, or as the deliberately vague fallback -- true, but less than the
server knew.

This runs from the Python side because that is where the vocabulary is
declared. The interface cannot check it: reading a Python tuple from a browser
test means parsing a language this project has a parser for one directory over.

WHY THE FLOORS ARE HERE. The check is "every declared name appears in that
file". Both halves can go quiet. A renamed or moved TypeScript file makes the
parse return nothing and every `in` test below passes against an empty set --
the failure this repository has now shipped five times. An emptied Python tuple
makes every loop run zero times and pass. So the parse is asserted to have
found entries, and the tuples are asserted to be non-empty, before anything is
concluded from them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from policy_platform.api.actor_role import (
    ACTOR_ROLE_REFUSAL,
    ACTOR_ROLES,
    GUARDED_ACTIONS,
)
from policy_platform.api.roles import ALL_ROLES as RBAC_ROLES
from policy_platform.api.roles import RBAC_REFUSAL as RBAC_REFUSAL_CODE

WORDING = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "actorRole.ts"

#: Keys of a `Record<string, string>` literal: `  some_key: "Some words",`
_ENTRY = re.compile(r'^\s{2}([a-z][a-z0-9_]*):\s*"', re.MULTILINE)


def _block(name: str) -> str:
    """The body of one exported record, from its declaration to its closer."""

    text = WORDING.read_text(encoding="utf-8")
    start = text.find(f"export const {name}")
    assert start != -1, (
        f"{name} is not declared in {WORDING.name}. Either it was renamed, or "
        "the file moved -- and every assertion below would then be checking an "
        "empty string."
    )
    end = text.find("\n};", start)
    assert end != -1, f"{name} has no closing brace in {WORDING.name}"
    return text[start:end]


def _keys(name: str) -> set[str]:
    return set(_ENTRY.findall(_block(name)))


def test_the_wording_file_is_where_this_test_thinks_it_is():
    """The first thing to check, because everything else reads this path."""

    assert WORDING.exists(), (
        f"no wording file at {WORDING}. A missing file makes every check below "
        "pass on an empty parse."
    )


def test_the_parser_still_finds_entries():
    """Positive control on the regex, not on the contents.

    If the file's formatting changes so that keys no longer match, this fails
    loudly instead of every membership test below succeeding against nothing.
    """

    assert _keys("ACTOR_ROLE_LABEL"), "parsed no roles out of the wording file"
    assert _keys("GUARDED_ACTION_PHRASE"), "parsed no actions out of the wording file"


def test_the_declared_vocabularies_are_not_empty():
    """Positive control on the Python side.

    An emptied tuple makes the parametrised tests below collect zero cases,
    which pytest reports as success.
    """

    assert ACTOR_ROLES, "no roles declared, so the role check runs zero times"
    assert GUARDED_ACTIONS, "no actions declared, so the action check runs zero times"


@pytest.mark.parametrize("role", ACTOR_ROLES)
def test_every_role_the_server_can_name_has_a_label(role: str):
    assert role in _keys("ACTOR_ROLE_LABEL"), (
        f"the server can refuse asking for {role!r} and the interface has no "
        f"label for it, so a reader is told less than the server knew"
    )


@pytest.mark.parametrize("action", GUARDED_ACTIONS)
def test_every_action_the_server_can_name_has_a_phrase(action: str):
    assert action in _keys("GUARDED_ACTION_PHRASE"), (
        f"the server can refuse {action!r} and the interface has no phrase for "
        f"it, so the sentence loses the verb and says only 'do this'"
    )


def test_the_code_itself_is_agreed_on_both_sides():
    """The one string both sides must spell identically.

    Everything else is keyed by it. If the two drift, the interface stops
    recognising the refusal and falls through to a generic error, which is the
    silence this work exists to remove.
    """

    text = WORDING.read_text(encoding="utf-8")
    assert f'"{ACTOR_ROLE_REFUSAL}"' in text, (
        f"the server sends {ACTOR_ROLE_REFUSAL!r} and the interface does not "
        "mention it"
    )


def test_the_capability_layers_refusal_code_is_agreed_too():
    """The second code, for the same reason as the first.

    `api/authz.py` refuses with its own code because it governs every operation
    rather than the named few in `actor_role.py`. It reached the interface
    unrecognised at first: `isActorRoleRefusal` matched one literal, so a
    capability refusal fell through to the generic path and would have rendered
    as a raw object -- exactly the silence the first code was introduced to
    remove, reappearing the moment a second code existed.

    Asserted against the constant rather than a copy of the string, so the two
    cannot be reworded apart.
    """

    text = WORDING.read_text(encoding="utf-8")
    assert f'"{RBAC_REFUSAL_CODE}"' in text, (
        f"the capability layer refuses with {RBAC_REFUSAL_CODE!r} and the "
        "interface does not mention it, so that refusal reaches a reader as a "
        "raw object"
    )


@pytest.mark.parametrize("role", RBAC_ROLES)
def test_every_capability_role_has_a_label(role: str):
    """The roles the capability layer can name need words as much as the others.

    Same rule as `test_every_role_the_server_can_name_has_a_label`, over the
    other vocabulary. Two vocabularies can refuse a reader and both render
    through one function, so both have to be covered or the newer one degrades
    to "you do not have the role this action needs" while the server knew which
    role it wanted.
    """

    assert role in _keys("ACTOR_ROLE_LABEL"), (
        f"the capability layer can refuse asking for {role!r} and the interface "
        "has no label for it, so a reader is told less than the server knew"
    )


def test_the_capability_vocabulary_is_not_empty():
    """Positive control, for the same reason as the one above it."""

    assert RBAC_ROLES, "no capability roles declared, so the check runs zero times"


def test_no_router_composes_the_sentence_this_replaced():
    """The wording left the server, and must not come back.

    Named by its distinguishing clause rather than in full, so that a reworded
    copy is still caught. `actor_role.py` itself is exempt: it quotes the old
    sentence in its module docstring to record what was removed and why.
    """

    src = Path(__file__).resolve().parents[2] / "src" / "policy_platform"
    offenders = []
    scanned = 0
    for path in sorted(src.rglob("*.py")):
        if path.name == "actor_role.py":
            continue
        scanned += 1
        if "acting role in the header" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(src).as_posix())

    # The floor. A scan pointed at a directory that does not exist reads no
    # files and reports no offenders, which is indistinguishable from success.
    assert scanned > 100, f"only scanned {scanned} Python files; expected the tree"

    assert offenders == [
        "api/routers/candidate_rules.py"
    ], (
        "expected exactly one remaining producer of this sentence. "
        f"Found {offenders}. candidate_rules.py is held by another workstream "
        "and is left for it to adopt `require_role`; anything else here is a "
        "new copy of wording that was deliberately moved to the interface."
    )
