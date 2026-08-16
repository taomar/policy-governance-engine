"""A route label must not be shown in a colour that argues with it.

Every policy record is either `deterministic` — the source states its test as a
comparison the engine computes — or it is `ai_ready`, where a judge reads the
rule against the case and returns a verdict with its confidence. Both are
routes. Neither is a fault.
The words the app uses for the two routes were fixed some time ago and are
now correct in every place they appear; the colours were not fixed with them,
so a reader met a route name written in the amber the same screen uses
for things that have gone wrong. The colour said one thing and the sentence
beside it said the opposite, and colour is read first.

This closes that class rather than the three instances of it, because the two
decisions are made in different places — a label chosen in one module, a colour
chosen in a component that never mentions the words — and nothing has been
holding them together.

WHAT COUNTS AS A ROUTE LABEL is not a list typed into this file. It is read out
of `ruleExecutability.ts`, which is where the app decides how to name the
route, so renaming a label moves this guard with it. Three forms are followed:

  * the literal wording, wherever it is written out;
  * `DETERMINISTIC_LABEL.no` and `deterministicLabel(...)`, the identifiers that
    stand in for that wording — the loudest instance was of this form and a
    scan for the literal text alone would have walked straight past it;
  * a constant, in the file being scanned, whose body carries route wording.
    `<Tag color="orange">{BLOCKER_COPY[b]?.label}</Tag>` puts the words and the
    colour four hundred lines apart, and that indirection is not an excuse.

WHERE THE FLOORS GO, AND WHY THEY GO THERE.

The verdict of this scan is a list of offenders, so a scan that has gone blind
returns an empty list and passes while proving nothing. The floors therefore
come LAST, after the offender assertion. Put them first and a real offender is
reported as a volume problem: the fails-before run stops naming the defect and
starts complaining about a count, and the evidence is lost.

(The opposite rule holds for a guard whose verdict is a set difference against
what a scan found — there, blindness does not go quiet, it accuses every item
in the set and produces a confident, precise, entirely wrong bug report about
the interface when the fault is in the test. Those floors go FIRST. Both shapes
exist in this suite; check which one you have before you place a floor.)

There are three separate ways for this scan to go blind and one number cannot
see all three, so there are three floors:

  * it reads no files — a moved directory, a wrong suffix;
  * it reads the files but recognises no route vocabulary — a renamed constant
    in `ruleExecutability.ts`, a reworded label;
  * it recognises the vocabulary but no longer finds coloured elements — a
    changed component library, a rewritten attribute syntax.

The file count stays perfectly healthy while either of the other two collapses,
which is exactly the failure this arrangement is here to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "src"
VOCABULARY_SOURCE = WEB / "ruleExecutability.ts"

# antd's palette for "something is wrong or needs attention". A route label
# rendered in any of these is arguing with itself.
ALARM_TONES = frozenset(
    {"gold", "orange", "red", "volcano", "warning", "error", "danger"}
)

# An opening JSX tag for a component: `<Tag color="gold" bordered={false}>`.
# Attribute values may contain braces, so a brace group is allowed, but not a
# nested one — that is enough for a call site and stops the match running on.
_OPEN_TAG = re.compile(r"<([A-Z][A-Za-z0-9_.]*)((?:[^<>{}]|\{[^{}]*\})*?)>", re.S)
_TONE_ATTR = re.compile(r'\b(?:color|type|status)\s*=\s*"([a-z]+)"')
_UPPER_CONST = re.compile(r"const\s+([A-Z][A-Z0-9_]*)\s*(?::[^=]*)?=\s*\{")

# How far past an opening tag to read for its content. Every call site of this
# shape is a short inline label; a window keeps an unclosed tag from swallowing
# the rest of the file.
_BODY_WINDOW = 400

_MINIMUM_FILES = 40
_MINIMUM_VOCABULARY_SIGHTINGS = 10
_MINIMUM_COLOURED_ELEMENTS = 10


def _route_label_wording() -> set[str]:
    """The words this app uses for its two routes, read from where it picks them.

    Deliberately not a list typed into this test. If `ruleExecutability.ts` is
    renamed or restructured this returns nothing, and the floor below turns that
    into a failure rather than a green run over an empty set.

    Both names are read, not just the judged one. The route names were
    consolidated so that each route has exactly one name, which means the
    module now yields two strings rather than the four the chooser used to
    invent; reading both keeps the floor below meaningful and extends the
    colour rule to whichever route is being named.
    """
    source = VOCABULARY_SOURCE.read_text(encoding="utf-8")
    wording: set[str] = set()

    label = re.search(r"DETERMINISTIC_LABEL\s*=\s*\{(.*?)\}", source, re.S)
    if label:
        wording.update(re.findall(r'\b(?:yes|no)\s*:\s*"([^"]+)"', label.group(1)))

    chooser = re.search(r"export function deterministicLabel\((.*?)\n\}", source, re.S)
    if chooser:
        wording.update(re.findall(r'return\s+"([^"]+)"', chooser.group(1)))

    return wording


def _scanned_files() -> list[Path]:
    return sorted(
        p
        for p in WEB.rglob("*.ts*")
        if p.is_file() and ".test." not in p.name and ".spec." not in p.name
    )


def _tokens_for(source: str, wording: set[str]) -> set[str]:
    """Every way this file can put route wording inside an element."""
    tokens = set(wording) | {"DETERMINISTIC_LABEL.no", "deterministicLabel("}

    # A constant in this file whose body carries the wording: referring to it is
    # referring to the words.
    for match in _UPPER_CONST.finditer(source):
        depth, index = 0, match.end() - 1
        while index < len(source):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        body = source[match.end() : index]
        if any(w.casefold() in body.casefold() for w in wording):
            tokens.add(match.group(1) + "[")
            tokens.add(match.group(1) + ".")

    return tokens


def _scan() -> tuple[list[str], int, int, int]:
    """Offenders, plus a count of each thing this scan has to be able to see."""
    wording = _route_label_wording()
    files = _scanned_files()

    offenders: list[str] = []
    vocabulary_sightings = 0
    coloured_elements = 0

    for path in files:
        source = path.read_text(encoding="utf-8")
        tokens = _tokens_for(source, wording)
        folded = source.casefold()
        vocabulary_sightings += sum(folded.count(t.casefold()) for t in tokens)

        for match in _OPEN_TAG.finditer(source):
            tones = {t for t in _TONE_ATTR.findall(match.group(2)) if t in ALARM_TONES}
            if not tones:
                continue
            coloured_elements += 1

            close = source.find("</", match.end())
            end = close if close != -1 else match.end() + _BODY_WINDOW
            body = source[match.end() : end][:_BODY_WINDOW]

            named = sorted(t for t in tokens if t.casefold() in body.casefold())
            if named:
                line = source[: match.start()].count("\n") + 1
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line} renders route wording "
                    f"({', '.join(named)}) inside <{match.group(1)}> coloured "
                    f"{', '.join(sorted(tones))}"
                )

    return offenders, len(files), vocabulary_sightings, coloured_elements


def test_a_route_label_is_never_shown_in_an_alarm_colour():
    offenders, files, vocabulary, coloured = _scan()

    assert not offenders, (
        "A label naming the reading route is rendered in a colour this app uses "
        "for faults, so the colour contradicts the words beside it. Being decided "
        "by reading is a route, not a problem; show it in the neutral tone the "
        "app already uses elsewhere.\n  " + "\n  ".join(offenders)
    )

    # Floors last: see the module docstring. Each covers a different blindness,
    # and no one of them can stand in for another.
    assert files >= _MINIMUM_FILES, (
        f"read only {files} web source files, expected at least {_MINIMUM_FILES} — "
        "the scan has gone blind and the assertion above proved nothing"
    )
    assert vocabulary >= _MINIMUM_VOCABULARY_SIGHTINGS, (
        f"recognised route wording only {vocabulary} times, expected at least "
        f"{_MINIMUM_VOCABULARY_SIGHTINGS} — the vocabulary is no longer being read "
        "out of ruleExecutability.ts, so nothing was actually checked"
    )
    assert coloured >= _MINIMUM_COLOURED_ELEMENTS, (
        f"found only {coloured} elements carrying an alarm colour, expected at "
        f"least {_MINIMUM_COLOURED_ELEMENTS} — the colour attribute is no longer "
        "being recognised, so nothing was actually checked"
    )


def test_the_vocabulary_is_read_from_the_module_that_chooses_it():
    """The enumeration must find real wording, not fall back to an empty set."""
    wording = _route_label_wording()

    assert wording, (
        "no route wording could be read out of ruleExecutability.ts — the guard "
        "above would pass while checking nothing"
    )
    assert all(w.strip() for w in wording), f"blank wording extracted: {wording!r}"
    # Two routes, two names. One means the extractor has stopped being read.
    assert len(wording) >= 2, (
        f"only extracted {sorted(wording)} — the module names two routes, so the "
        "extractor has stopped following it"
    )


@pytest.mark.parametrize(
    "snippet,should_flag",
    [
        ('<Tag color="gold">{DETERMINISTIC_LABEL.no}</Tag>', True),
        ('<Tag color="orange">AI Ready</Tag>', True),
        ('<Tag bordered={false} color="red">AI Ready</Tag>', True),
        ("<Tag>{DETERMINISTIC_LABEL.no}</Tag>", False),
        ('<Tag color="default">AI Ready</Tag>', False),
        ('<Tag color="blue">AI Ready</Tag>', False),
        ('<Tag color="gold">Missing facts</Tag>', False),
    ],
)
def test_the_detector_separates_an_arguing_colour_from_an_agreeing_one(
    snippet, should_flag
):
    """The detector must see the defect and must not imagine it.

    Without this, a detector that flags everything and a detector that flags
    nothing both satisfy the scan above on a clean tree.
    """
    wording = _route_label_wording()
    tokens = _tokens_for(snippet, wording)

    flagged = False
    for match in _OPEN_TAG.finditer(snippet):
        tones = {t for t in _TONE_ATTR.findall(match.group(2)) if t in ALARM_TONES}
        if not tones:
            continue
        body = snippet[match.end() : snippet.find("</", match.end())]
        if any(t.casefold() in body.casefold() for t in tokens):
            flagged = True

    assert flagged is should_flag, f"{snippet!r}: flagged={flagged}, expected {should_flag}"
