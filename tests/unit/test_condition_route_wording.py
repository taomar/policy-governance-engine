"""Every code the server can put on a record has words in the interface.

The server emits `condition_provenance.code` and the interface turns it into a
sentence. That split is deliberate and right — wording sent inside a record is
frozen into every copy of it — but it leaves two artefacts in two languages in
two trees that have to agree, and nothing made them.

They have already disagreed twice, in both directions:

* `ConditionProvenanceNotice.tsx` shipped with wording for four of the five
  codes. The fifth, `derived_from_stated_bound`, fell through to the default
  branch and was described with the sentence written for
  `conditions_not_projected` — so a record whose comparison was compiled
  straight out of its own sentence was told a mapping was missing for it.
* That component was then deleted, and its stylesheet, its two helper
  functions and a comment in `ruleDisplay.ts` promising "the inspector renders
  as its own panel" were all left behind pointing at nothing. The reason was
  stripped from the rule description on the strength of that promise, so the
  net effect of the deletion was that no surface showed it at all.

Neither is caught by a type checker: `code` is a string on both sides, and a
lookup that misses returns undefined rather than failing. So it is caught here.

The direction matters. This enumerates what the *server* can emit and demands
the interface cover it, because that is the direction the risk runs: a new code
reaches records the day it is written, and the interface finds out when a
reviewer meets a record it has nothing to say about.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from policy_platform.contracts.policy import CONDITION_PROVENANCE_CODES

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"

#: The interface's side of the contract: one entry per code.
WORDING = ROOT / "apps" / "web" / "src" / "conditionRoute.ts"

#: The mapping object, from its declaration to the line that closes it.
_MAPPING = re.compile(r"export const CONDITION_ROUTE\b[^{]*\{\n(.*?)\n\};", re.DOTALL)

#: One key per line, opening its brace on the same line. The formatting is
#: stated in the file it reads, next to the object, so nobody reformats it
#: without meeting the reason.
_KEY = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_]*): \{$", re.MULTILINE)

#: Text a reader sees. Comment lines are skipped the way the wording guard
#: beside this one skips them: a comment naming a code is documentation.
_QUOTED = re.compile(r'"([^"\n]*)"')


def _wording_source() -> str:
    assert WORDING.exists(), (
        f"{WORDING.relative_to(ROOT)} does not exist. Nothing in the interface turns a "
        "provenance code into words, so every record is shown to a reviewer with no "
        "account of how it was routed."
    )
    return WORDING.read_text(encoding="utf-8")


def _mapping_body() -> str:
    match = _MAPPING.search(_wording_source())
    assert match, (
        f"{WORDING.relative_to(ROOT)} has no CONDITION_ROUTE object this test can read. "
        "It was renamed or reformatted; point this at the new shape rather than "
        "leaving a guard that reads nothing."
    )
    return match.group(1)


def _mapped_codes() -> set[str]:
    return set(_KEY.findall(_mapping_body()))


def _emitted_codes() -> list[tuple[str, str]]:
    """Every literal code passed to `ConditionProvenance(...)`, with its site."""

    found: list[tuple[str, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name != "ConditionProvenance":
                continue
            for keyword in node.keywords:
                if keyword.arg == "code" and isinstance(keyword.value, ast.Constant):
                    value = keyword.value.value
                    if isinstance(value, str):
                        found.append((value, f"{path.relative_to(ROOT)}:{node.lineno}"))
    return found


def test_every_code_the_server_emits_is_declared():
    """The declared list is only useful while it is the whole list.

    A code emitted but not declared would leave the interface guard below
    checking a set that no longer describes reality — passing, while a record
    carries something nothing has words for.
    """

    emitted = _emitted_codes()
    assert emitted, (
        "no ConditionProvenance(code=...) call found anywhere in the source; "
        "this scan has stopped reading the emitter"
    )

    undeclared = [
        f"{code} at {site}" for code, site in emitted if code not in CONDITION_PROVENANCE_CODES
    ]
    assert not undeclared, (
        "codes emitted but not declared in CONDITION_PROVENANCE_CODES:\n  "
        + "\n  ".join(undeclared)
    )


def test_every_declared_code_has_wording_in_the_interface():
    """A code with no entry renders a fallback, which is not the same as words.

    The fallback exists so an unknown code degrades gracefully in front of a
    reviewer. It is not a substitute for saying what a code we ship actually
    means, and without this test the difference is invisible until someone
    reads a record on screen.
    """

    mapped = _mapped_codes()
    assert mapped, (
        f"no codes read out of {WORDING.relative_to(ROOT)}; the extractor sees nothing, "
        "so it would pass whatever the interface says"
    )
    assert CONDITION_PROVENANCE_CODES, "no codes declared; there is nothing to check"

    missing = sorted(set(CONDITION_PROVENANCE_CODES) - mapped)
    assert not missing, (
        "codes the server can emit with no wording in "
        f"{WORDING.relative_to(ROOT)}: {missing}. A reviewer meeting one of these "
        "sees the fallback and learns nothing about why the record was routed."
    )


def test_the_interface_never_shows_a_reviewer_a_raw_code():
    """The words have to be words.

    Pasting the identifier into the sentence would satisfy the test above and
    put `no_scope_derived` in front of someone with no way to look it up.
    """

    offenders: list[str] = []
    for lineno, line in enumerate(_wording_source().splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for text in _QUOTED.findall(line):
            for code in CONDITION_PROVENANCE_CODES:
                if code in text:
                    offenders.append(f"{WORDING.name}:{lineno}: {code!r} in {text[:60]!r}")

    assert not offenders, "raw provenance codes in display text:\n  " + "\n  ".join(offenders)


def test_an_unrecognised_code_still_has_somewhere_to_land():
    """Records outlive the build that reads them.

    A stored record can carry a code from a writer newer or older than this
    interface. Falling through to nothing would put a reviewer back where this
    work started — approving a record with no account of how it was routed, and
    no way to tell there was one to be had.
    """

    assert "UNKNOWN_CONDITION_ROUTE" in _wording_source(), (
        f"{WORDING.relative_to(ROOT)} has no fallback for a code it does not know"
    )
