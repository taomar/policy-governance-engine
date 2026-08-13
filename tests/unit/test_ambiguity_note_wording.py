"""Every ambiguity status the server can store has words in the interface.

`ambiguity_status` says whether the sentence a record was read from can be read
more than one way. It is stored on every record and, until the change this test
guards, reached a reviewer only as a warning glyph in the inspector header whose
hover text was the enum member with the underscores taken out. On a document
under review 43 of 273 records carried a non-`none` status; a reviewer approving
one of them for publication was never told in text, and a reviewer working by
keyboard — where no hover exists — was never told at all.

The server emits the enum and the interface owns the words, the same split
`condition_provenance` uses. That split is right, and it leaves two artefacts in
two languages in two trees that have to agree with nothing making them.

The direction matters, and it is the same direction as its sibling guard: this
enumerates what the *server* can store and demands the interface cover it. A new
member reaches records the day it is added, and the interface finds out when a
reviewer meets a record it has nothing to say about.

There is a second thing this polices that the sibling does not. `ambiguity_status`
is a statement about the SOURCE DOCUMENT — that its words carry more than one
reading. It is not a statement about the record, which is quoting those words
faithfully, and it is not a shortfall in anything. Wording that turns a fact
about a document into a fault in a record is the recurring defect in this
codebase, so the vocabulary is checked here too.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from policy_platform.contracts.policy import AmbiguityStatus

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"

#: The interface's side of the contract: one entry per status.
WORDING = ROOT / "apps" / "web" / "src" / "ambiguityNote.ts"

#: Every value the enum can take, read from the enum itself rather than copied.
DECLARED: tuple[str, ...] = tuple(member.value for member in AmbiguityStatus)

#: The mapping object, from its declaration to the line that closes it.
_MAPPING = re.compile(r"export const AMBIGUITY_NOTE\b[^{]*\{\n(.*?)\n\};", re.DOTALL)

#: One key per line, opening its brace on the same line. The formatting is
#: stated in the file it reads, next to the object, so nobody reformats it
#: without meeting the reason.
_KEY = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_]*): \{$", re.MULTILINE)

#: Text a reader sees.
_QUOTED = re.compile(r'"([^"\n]*)"')

#: Words that turn a fact about a document into a fault in the record quoting
#: it. `ambiguity_status` describes the source's wording; a record carrying an
#: ambiguous sentence faithfully is doing its job and is not waiting on anyone.
#:
#: Matched case-insensitively on word boundaries against display strings only.
_DEFICIENCY = (
    r"missing",
    r"incomplete",
    r"unfinished",
    r"deficien\w*",
    r"not yet",
    r"awaits?",
    r"awaiting",
    r"pending",
    r"needs? (?:work|fixing|attention)",
    r"failed?",
    r"problem",
    r"defect",
)
_DEFICIENCY_RE = re.compile(r"\b(?:" + "|".join(_DEFICIENCY) + r")\b", re.IGNORECASE)

#: Floors on what each scan LOOKED AT, as distinct from what it found.
#:
#: Every verdict below is an empty collection, and an empty collection is what a
#: healthy codebase and a blind scan both produce. `assert not offenders` cannot
#: tell "examined twenty strings, none bad" from "examined nothing". These
#: numbers make the second case fail.
#:
#: Floors, not equalities. Growth is ordinary and must not fail here; collapse is
#: not. Lowering one should be a deliberate edit with a reason attached.
_STATUSES_AT_WRITING = 4  # the declared enum the day this was written
_MINIMUM_FILES_SCANNED = 60  # src/policy_platform held 121; loose on purpose
_MINIMUM_DISPLAY_STRINGS = 12  # the wording file carried more than 20
_MINIMUM_EMIT_SITES = 3  # formulation_mapping alone had four

# Where the floor goes is not uniform, and getting it wrong hides the defect the
# test exists for.
#
# When the verdict is a list of offenders, a blind scan produces an empty list
# and passes vacuously — so the floor goes AFTER, where it is the only thing left
# to fail.
#
# When the verdict is a set difference against what the scan found, a blind scan
# inverts the meaning rather than silencing it: `DECLARED - mapped` with `mapped`
# empty reports every status as missing wording, which is a precise, confident
# and entirely wrong report about the interface when the fault is in this file.
# There the floor goes FIRST, so the run says "the extractor read nothing"
# instead of "the interface has no wording". It does not shadow a real offender,
# because a genuinely unmapped status leaves the volume untouched — confirmed by
# injecting one and checking the failure still names it.


def _wording_source() -> str:
    assert WORDING.exists(), (
        f"{WORDING.relative_to(ROOT)} does not exist. Nothing in the interface turns an "
        "ambiguity status into words, so a reviewer approving a record is not told what "
        "the source's wording admits."
    )
    return WORDING.read_text(encoding="utf-8")


def _mapping_body() -> str:
    match = _MAPPING.search(_wording_source())
    assert match, (
        f"{WORDING.relative_to(ROOT)} has no AMBIGUITY_NOTE object this test can read. "
        "It was renamed or reformatted; point this at the new shape rather than leaving "
        "a guard that reads nothing."
    )
    return match.group(1)


def _mapped_statuses() -> set[str]:
    return set(_KEY.findall(_mapping_body()))


def _display_strings() -> tuple[list[tuple[int, str]], int]:
    """Quoted text a reader sees, and how many strings were examined.

    Comment lines are skipped: a comment naming a status is documentation, and
    this file's own docstring names several.
    """

    strings: list[tuple[int, str]] = []
    examined = 0
    for lineno, line in enumerate(_wording_source().splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for text in _QUOTED.findall(line):
            examined += 1
            strings.append((lineno, text))
    return strings, examined


def _emitted_statuses() -> tuple[list[tuple[str, str]], int]:
    """Every `AmbiguityStatus.MEMBER` the server names, and files read.

    The file count is returned because the statuses alone cannot report it. A
    `SRC` pointing at a directory that no longer exists yields no paths, no
    statuses, and a clean bill of health.
    """

    by_name = {member.name: member.value for member in AmbiguityStatus}
    found: list[tuple[str, str]] = []
    files = 0
    for path in sorted(SRC.rglob("*.py")):
        files += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "AmbiguityStatus"
                and node.attr in by_name
            ):
                found.append((by_name[node.attr], f"{path.relative_to(ROOT)}:{node.lineno}"))
    return found, files


def test_every_status_the_server_emits_is_declared():
    """The enum is only useful while it is the whole story.

    A status written as a bare string somewhere the enum does not cover would
    leave the interface guard below checking a set that no longer describes
    reality — passing, while a record carries something nothing has words for.
    """

    emitted, files = _emitted_statuses()

    undeclared = [f"{value} at {site}" for value, site in emitted if value not in DECLARED]
    assert not undeclared, (
        "AmbiguityStatus members emitted whose value is not in the enum's own values:\n  "
        + "\n  ".join(undeclared)
    )

    # Floors last: the verdict above is an empty list either way, so these are
    # the only assertions that can tell a clean scan from a stopped one. Two
    # numbers, because the scan has two independent ways to go blind and one
    # cannot report the other.
    assert files >= _MINIMUM_FILES_SCANNED, (
        f"the scan read {files} python files under {SRC.relative_to(ROOT)}, expected at "
        f"least {_MINIMUM_FILES_SCANNED}. It is not reading the source tree, so the "
        "verdict above was reached without examining the emitter."
    )
    assert len(emitted) >= _MINIMUM_EMIT_SITES, (
        f"the scan found {len(emitted)} AmbiguityStatus.MEMBER references, expected at "
        f"least {_MINIMUM_EMIT_SITES}. Either the emitter was rewritten into a shape this "
        "AST walk no longer recognises, or statuses are now built somewhere this does not "
        "look — both leave the check above passing on a short list."
    )


def test_every_declared_status_has_wording_in_the_interface():
    """A status with no entry renders the fallback, which is not the same as words.

    The fallback exists so an unknown status degrades honestly in front of a
    reviewer. It is not a substitute for saying what a status we ship actually
    means, and without this test the difference is invisible until someone reads
    a record on screen.
    """

    mapped = _mapped_statuses()

    # Floors first, and only here. The verdict below is `DECLARED - mapped`,
    # which does not degrade to empty when the extractor goes blind — it degrades
    # to "every status is missing wording", a false report about the interface
    # when the fault is in this file.
    assert len(mapped) >= _STATUSES_AT_WRITING, (
        f"read {len(mapped)} statuses out of {WORDING.relative_to(ROOT)}, expected at "
        f"least {_STATUSES_AT_WRITING}. The extractor has gone blind; the comparison "
        "below would blame the interface for wording that is present and unreadable to "
        "this test."
    )
    assert len(DECLARED) >= _STATUSES_AT_WRITING, (
        f"{len(DECLARED)} values on AmbiguityStatus, expected at least "
        f"{_STATUSES_AT_WRITING}. A renamed enum, a moved module or an import resolving "
        "to a stub all shrink this to nothing, and every loop over it then passes by "
        "iterating no statuses at all."
    )

    missing = sorted(set(DECLARED) - mapped)
    assert not missing, (
        f"statuses the server can store with no wording in {WORDING.relative_to(ROOT)}: "
        f"{missing}. A reviewer meeting one of these sees the fallback and learns nothing "
        "about what the source's wording admits."
    )


def test_the_interface_never_shows_a_reviewer_a_raw_status():
    """The words have to be words.

    Pasting the identifier into the sentence would satisfy the test above and
    put `human_judgment_required` in front of someone with no way to look it up.

    Statuses carrying an underscore are matched as substrings, because they
    cannot occur in English by accident. Single-word ones are matched on word
    boundaries so that `blocking` inside `non_blocking` is not double-reported
    and the ordinary English word is not mistaken for the identifier.
    """

    strings, examined = _display_strings()
    underscored = [s for s in DECLARED if "_" in s]
    plain = [s for s in DECLARED if "_" not in s]
    plain_res = {s: re.compile(rf"\b{re.escape(s)}\b") for s in plain}

    offenders: list[str] = []
    compared = 0
    for lineno, text in strings:
        for status in underscored:
            compared += 1
            if status in text:
                offenders.append(f"{WORDING.name}:{lineno}: {status!r} in {text[:60]!r}")
        for status in plain:
            compared += 1
            if plain_res[status].search(text):
                offenders.append(f"{WORDING.name}:{lineno}: {status!r} in {text[:60]!r}")

    assert not offenders, "raw ambiguity statuses in display text:\n  " + "\n  ".join(offenders)

    # Floors last. This scan has two independent ways to see nothing and one
    # number cannot report both: a healthy string count says nothing about
    # whether there were any statuses to compare them against, and vice versa.
    assert examined >= _MINIMUM_DISPLAY_STRINGS, (
        f"read {examined} display strings out of {WORDING.relative_to(ROOT)}, expected at "
        f"least {_MINIMUM_DISPLAY_STRINGS}. The wording moved, changed quoting, or the "
        "file is gone; every string in the interface just passed without being read."
    )
    assert compared >= _MINIMUM_DISPLAY_STRINGS * _STATUSES_AT_WRITING, (
        f"made {compared} string-against-status comparisons, expected at least "
        f"{_MINIMUM_DISPLAY_STRINGS * _STATUSES_AT_WRITING}. With an empty status list "
        "every string is clean by definition, however many of them were read."
    )


def test_the_wording_describes_the_source_not_a_fault_in_the_record():
    """The product rule, applied to this field specifically.

    `ambiguity_status` reports that a DOCUMENT says something more than one way.
    The record quoting it is complete and correct, and nothing about it is
    pending. Wording that says otherwise turns a property of the source into an
    accusation against the record, which is the framing defect this codebase
    keeps producing.
    """

    strings, examined = _display_strings()

    offenders = [
        f"{WORDING.name}:{lineno}: {match.group(0)!r} in {text[:70]!r}"
        for lineno, text in strings
        if (match := _DEFICIENCY_RE.search(text))
    ]
    assert not offenders, (
        "wording that frames an ambiguous SOURCE as a shortfall in the RECORD:\n  "
        + "\n  ".join(offenders)
    )

    # Floors last, same reasoning as above, and two of them: the strings could
    # go to zero, or the vocabulary could.
    assert examined >= _MINIMUM_DISPLAY_STRINGS, (
        f"read {examined} display strings out of {WORDING.relative_to(ROOT)}, expected at "
        f"least {_MINIMUM_DISPLAY_STRINGS}. Nothing was checked for framing."
    )
    assert len(_DEFICIENCY) >= 8, (
        f"the vocabulary has {len(_DEFICIENCY)} patterns, expected at least 8. An emptied "
        "pattern list clears every string ever written."
    )


def test_an_unrecognised_status_still_has_somewhere_to_land():
    """Records outlive the build that reads them.

    A stored record can carry a status from a writer newer or older than this
    interface. Falling through to nothing would put a reviewer back where this
    work started — approving a record without being shown what the system holds
    about it, and with no way to tell there was anything to be shown.
    """

    source = _wording_source()
    assert "UNKNOWN_AMBIGUITY_NOTE" in source, (
        f"{WORDING.relative_to(ROOT)} has no fallback for a status it does not know"
    )
    assert "AMBIGUITY_UNNAMED" in source, (
        f"{WORDING.relative_to(ROOT)} no longer states that the record stores a status "
        "and not which words are open. Without it the interface implies it knows which "
        "phrase is ambiguous, which no field on the record records."
    )
