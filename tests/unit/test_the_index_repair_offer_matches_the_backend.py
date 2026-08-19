"""The rebuild the backend names must be a rebuild the product offers.

Retrieval refuses a project-wide case when the policy index cannot be relied on,
and several of those refusals end by telling the reader to *republish or rebuild
the policy index*. That instruction is only true if the surface printing it also
gives them a way to do it. When it does not, the product names an action it does
not offer -- which is the defect the policy-index repair surface was built to
remove.

THE WITNESS

It was removed in two of the three places and left in the third. `index_empty`
carries the same instruction as `index_not_built` and `index_stale`, and the
client's repair offer listed only the latter two, so a project whose index
existed but held nothing showed the sentence with no control beside it. Nothing
failed: both sides were internally consistent, and neither knew about the other.

WHAT THIS PINS

Not the wording, which will change, and not the set of statuses, which will
grow. It pins the *relationship*: the statuses whose reason tells a reader to
rebuild are exactly the statuses the client treats as repairable. Either side
may move as long as the other moves with it.

WHY THE FLOORS COME FIRST

The verdict is a set comparison, and a comparison between two empty sets passes.
Both extractors read source text -- a Python module for the constants and their
reasons, a TypeScript module for the client's list -- so either can quietly
return nothing if the code it reads is renamed or restructured. The floors below
assert each side found something before the sets are compared, so this cannot
become a guard that passes by looking at nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE_PROJECT = ROOT / "src" / "policy_platform" / "infrastructure" / "assistants" / "ai_case_project.py"
INDEX_HEALTH = ROOT / "apps" / "web" / "src" / "policyIndexHealth.ts"

#: The sentence the backend uses to tell a reader the index needs rebuilding.
#: Matched case-insensitively on the distinctive verb pair rather than the whole
#: sentence, so rewording the surrounding text does not silently empty this set.
_REBUILD_INSTRUCTION = re.compile(r"republish or rebuild", re.IGNORECASE)

#: `RETRIEVAL_THING = "thing"` -- constant name to wire value.
_CONSTANT_RE = re.compile(r'^(?P<name>RETRIEVAL_[A-Z_]+)\s*=\s*"(?P<value>[a-z_]+)"', re.MULTILINE)

#: The client's declared list, read as the literal strings inside it.
_CLIENT_SET_RE = re.compile(
    r"INDEX_REPAIRABLE_RETRIEVAL_STATUSES\s*=\s*\[(?P<body>.*?)\]",
    re.DOTALL,
)


def _constant_values() -> dict[str, str]:
    return {m.group("name"): m.group("value") for m in _CONSTANT_RE.finditer(CASE_PROJECT.read_text(encoding="utf-8"))}


def _statuses_that_say_rebuild() -> set[str]:
    """Wire values of every retrieval status whose `respond(...)` reason says to rebuild.

    Read by scanning each `respond(` call: the first argument names the status
    constant, and the reason belongs to that call. Splitting on `respond(` keeps
    a reason with the status it was returned beside, which reading the file
    line-by-line would not.
    """

    source = CASE_PROJECT.read_text(encoding="utf-8")
    values = _constant_values()
    found: set[str] = set()
    for chunk in source.split("respond(")[1:]:
        head = chunk[:120]
        name = next((n for n in values if re.match(rf"\s*{n}\b", head)), None)
        if name is None:
            continue
        # The reason belongs to this call, so stop at the next one.
        if _REBUILD_INSTRUCTION.search(chunk.split("respond(")[0]):
            found.add(values[name])
    return found


def _client_repairable() -> set[str]:
    match = _CLIENT_SET_RE.search(INDEX_HEALTH.read_text(encoding="utf-8"))
    assert match, (
        "INDEX_REPAIRABLE_RETRIEVAL_STATUSES is no longer readable from "
        f"{INDEX_HEALTH.name}. The guard cannot compare a list it cannot find."
    )
    return set(re.findall(r'"([a-z_]+)"', match.group("body")))


def test_the_extractors_find_something_to_compare():
    """Both floors, asserted before the comparison that depends on them."""

    backend = _statuses_that_say_rebuild()
    client = _client_repairable()

    assert len(backend) >= 3, (
        f"only {len(backend)} retrieval statuses were found telling the reader to "
        "rebuild; the reason-matching has stopped working and the comparison "
        "below would be vacuous"
    )
    assert len(client) >= 3, (
        f"only {len(client)} statuses were read from the client's repairable "
        "list; the comparison below would be vacuous"
    )


def test_the_index_repair_offer_matches_the_backend():
    """Every status that names the repair offers it, and no status offers it falsely.

    Both directions matter. A status the backend tells you to rebuild and the
    client does not offer is a dead-end instruction. A status the client offers
    to rebuild and the backend never names is a control that does not fix what
    the reader is looking at -- `unavailable`, for instance, means Search is not
    configured, which no rebuild repairs.
    """

    backend = _statuses_that_say_rebuild()
    client = _client_repairable()

    missing = sorted(backend - client)
    extra = sorted(client - backend)

    assert not missing, (
        "These retrieval statuses tell the reader to republish or rebuild, and "
        "the product does not offer the repair for them:\n  " + "\n  ".join(missing)
        + "\n\nAdd them to INDEX_REPAIRABLE_RETRIEVAL_STATUSES, or stop telling "
        "the reader to rebuild in that state."
    )
    assert not extra, (
        "The product offers an index rebuild for these statuses, and the backend "
        "never tells the reader to rebuild in them:\n  " + "\n  ".join(extra)
        + "\n\nEither the offer is wrong, or the backend's reason should say so."
    )


def test_the_reason_pattern_can_actually_fail():
    """A pattern that matches anything makes every assertion above vacuous."""

    assert not _REBUILD_INSTRUCTION.search("no evaluation was made")
    assert _REBUILD_INSTRUCTION.search("Republish or rebuild the policy index.")
