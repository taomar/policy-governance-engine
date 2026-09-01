"""Nothing shown to a user reports the AI Ready route as a defect.

A policy is served one of two ways. `deterministic` means the source states its
test as a comparison the engine can compute. `ai_ready` means the source states
it in words, and a judge decides it by reading the record. Most policy text is
the second — 53 of 55 in the live corpus — and that is a property of how policy
is written, not a shortcoming of the extraction.

Text that calls the second kind "not machine-executable" turns the ordinary
case into a standing fault. It had spread into six places, and the loudest was
a high-severity quality finding raised against nearly every policy on every
run, recommending a configuration exercise that would never be done and could
not help. Findings that always fire teach a reader to ignore findings.

Scope is the same as the domain-wording guard beside this one: string literals
in behavioural code, prompt instructions, and strings the interface renders.
Comments and docstrings are excluded, because recording the wording that was
removed is how the next reader learns why the rule exists.

The field name `machine_executable` is deliberately allowed. It is a real field
on a real contract, it appears in payloads a model reads, and renaming it is a
migration rather than a wording fix. What is forbidden is the prose.

Every phrase below is hyphenated or spaced, and the bare noun is neither. So
`Executability` shipped as a column header over the project register, above a
count reading "0 of 273" for the only project in it. A header naming a property
turns the two routes into one scale with most records at the bottom of it, which
is the same claim the phrases make, in one word and with none of them present.
The second rule catches the bare word, and only where a user reads it as a
label. Identifiers keep the word: `machine_executable` is the field,
`executableRuleCount` is a variable, `"executable"` is a discriminant the code
compares. None of them is language, and the rule separates them by shape rather
than by a list of lines, so it still holds after the next rename.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.unit.published_docs import ignored_documents, published_documents

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"
WEB = ROOT / "apps" / "web" / "src"
DOCS = ROOT / "docs"

def _scanned_documents() -> list[Path]:
    """The published documents this guard is about."""

    return published_documents()

#: Prose that frames the AI Ready route as a shortfall.
#:
#: Hyphenated and spaced forms only. `machine_executable` with an underscore is
#: the field, and is allowed everywhere.
_FRAMING = (
    r"machine[- ]executable",
    r"machine[- ]ready",
    r"documentation[- ]only",
    r"FACT_MODEL_REQUIRED",
    r"OUTPUT_MODEL_REQUIRED",
    r"requires? (?:a )?(?:formal )?fact[- ]model",
    r"configure a fact model",
    r"supply the missing mapping",
    # Fourth evasion, found by contrast rather than by vocabulary. Naming the
    # two routes by the form of the sentence that produced them is taxonomy and
    # stays: "in words" says nothing without "rather than as a comparison",
    # because every document is words. What is banned is contrast drawn against
    # our own machinery or against failure.
    #
    # The contrastive frame is required, and that requirement is the rule rather
    # than a convenience. `ai_test_proposal`'s system prompt defines both routes
    # side by side -- "a comparison the engine can compute" against "in words
    # and a judge decides it by reading" -- and there the engine's reach is
    # describing the route that *is* the engine's, which is simply accurate. The
    # defect is using that reach to describe the other route, so the pattern
    # only fires after "rather than".
    r"rather than(?:\s+\w+){0,3}\s+comparison(?:\s+\w+){0,3}\s+"
    r"(?:the\s+)?(?:engine|evaluator|platform)\s+can",
    # Denying a fault raises it. A reader who is told this is not a failure has
    # been told failure was on the table.
    r"(?:is|are)\s+not\s+a\s+fail(?:ed|ure)",
)
_FRAMING_RE = re.compile(rf"(?:{'|'.join(_FRAMING)})", re.IGNORECASE)

#: The same claim in one bare word: `Executability`, `not executable`.
#:
#: The lookarounds are the whole rule. An identifier glues the word to another
#: token -- `machine_executable`, `executableRuleCount`, `machineExecutableFor`,
#: `rule.machine_executable` -- and English does not. So the word is read as
#: language only when nothing is fused to either end of it. A leading hyphen is
#: not a fusion, which is what makes `non-executable` a match.
_BARE_EXECUTABILITY = re.compile(
    r"(?<![A-Za-z0-9_$.])executab(?:ilities|ility|les|le|ly)(?![A-Za-z0-9_$])",
    re.IGNORECASE,
)

#: Code embedded in a line of interface: `{...}` holds an expression, `${...}`
#: holds one inside a template, and `<...>` is a tag. What is left is text.
_EXPRESSION = re.compile(r"\$?\{[^{}]*\}")
_TAG = re.compile(r"<[^<>]*>")
_QUOTED = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'|`([^`\n]*)`")

#: Punctuation that survives only in code. A caption may carry a comma or a
#: full stop; it does not carry a brace, a colon or a semicolon.
_CODE_PUNCTUATION = set("{}()[]<>=;:|&$#\"'`/\\")

#: Files whose whole purpose is the mechanism rather than the message.
#:
#: `contracts/formulation.py` declares the requirement codes as an enum: the
#: names have to exist for the agent's replies to parse. They are excluded from
#: serialization, so they reach no reader.
#:
#: An entry has to keep earning its place. `test_every_exemption_is_earned`
#: holds each one to that: the path must exist, and the file must still carry a
#: phrase that needs excusing. An entry failing either is not a narrow
#: exemption, it is a standing permission for whatever lands at that path next.
#: A file whose name marks it as a test rather than as something that ships.
#: Matched on the name so it holds for `.test.ts`, `.test.tsx` and `.spec.*`
#: alike, and keeps holding after a rename that this list would not have known
#: about.
_IS_TEST_FILE = re.compile(r"\.(test|spec)\.tsx?$")

_MECHANISM = {
    SRC / "contracts" / "formulation.py",
}

#: ---------------------------------------------------------------------------
#: ONE NAME PER ROUTE
#:
#: There are two routes and each has exactly one name: `Deterministic`, where
#: the engine computes a comparison, and `AI Ready`, where a judge reads the
#: rule against the case and returns a verdict with its confidence.
#:
#: The interface had been using at least three names for the second one at
#: once. That is not a cosmetic problem. Every extra name is read as an extra
#: property of the record: a reader meeting the same route called one thing on
#: the card, another on the tab and a third in a tooltip concludes the three
#: are distinct states and that a record is somewhere in a progression between
#: them. A route that a reader believes is a stage has become a shortfall
#: without a single shortfall word being written, which is precisely what the
#: rest of this file is here to stop.
#:
#: So the retired names are forbidden outright, in the same places the framing
#: rules apply. `Parties & readiness` is here because the rule tab and the
#: policy tab drew the same content under two names, one of which named the
#: retired vocabulary.
_RETIRED_ROUTE_NAMES = (
    r"decided[- ]by[- ]reading",
    r"evaluated[- ]directly",
    r"parties\s*(?:&(?:amp;)?|and)\s*readiness",
    r"human[- ]judg(?:e)?ment[- ]requirement",
)
_RETIRED_RE = re.compile(rf"(?:{'|'.join(_RETIRED_ROUTE_NAMES)})", re.IGNORECASE)

#: Files carrying a retired name that this change was not permitted to edit.
#:
#: EMPTY, and that is the finished state: the two files that were here --
#: `PublishedPolicyCard.tsx` and `PolicyInspector.tsx` -- belonged to a
#: concurrent change on the same tree, and both have since been fixed by the
#: hand that owns them. Naming them was the only honest alternative to either
#: leaving the rule out, which would let the retired names return everywhere,
#: or editing files another hand owned.
#:
#: The mechanism stays because the situation recurs. `test_every_retired_name_
#: exemption_is_earned` holds each entry to existing AND still carrying a
#: retired name, so an entry fails the moment its file is fixed and has to be
#: deleted rather than quietly outliving its reason -- which is exactly how
#: both of the original entries left.
_AWAITING_ANOTHER_HAND: set[Path] = set()


def _string_literals(path: Path) -> list[tuple[int, str]]:
    """Every string literal in a Python file, excluding docstrings."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            found.append((node.lineno, node.value))
    return found


def _interface_captions(line: str) -> list[str]:
    """The display text on one line of interface source.

    Two things reach a user as a label. Text between tags is rendered by
    construction, and a quoted string is rendered when it reads as language
    rather than as a value.

    Length is not a test. An earlier version of this rule read only short
    text, on the theory that a caption names a thing while a sentence explains
    a mechanism. That theory was wrong in the way that matters: a user reads a
    sentence in the interface exactly as they read a label, and the longest
    strings were the ones stating the fault outright. Whether text is shown to
    a user does not depend on how many words it has.

    Code is removed first, so an expression is never mistaken for the text
    around it. That is what keeps the rule off `{published - executable}`,
    which renders a number beside the words "decided by reading".

    A lone lowercase token in quotes is a value the code compares -- a
    discriminant, a key, a class name. Language starts with a capital or has a
    second word.
    """

    captions: list[str] = []

    text = line
    previous = None
    while previous != text:  # a tag may be revealed by removing an expression
        previous = text
        text = _EXPRESSION.sub(" ", text)
        text = _TAG.sub(" ", text)
    text = text.strip()
    if text and not any(character in _CODE_PUNCTUATION for character in text):
        captions.append(text)

    for match in _QUOTED.finditer(line):
        value = next((group for group in match.groups() if group is not None), "")
        value = _EXPRESSION.sub(" ", value).strip()
        if value and (" " in value or value[0].isupper()):
            captions.append(value)

    return [caption for caption in captions if caption.split()]


def test_the_guard_would_notice_the_wording_it_forbids():
    """Proves the pattern matches, so a clean run means something.

    Every phrase here was in served output or a prompt before this file
    existed.
    """

    for phrase in (
        "3 rule(s) are not machine-executable.",
        "0% machine-ready",
        "this rule is documentation-only",
        "it still reports FACT_MODEL_REQUIRED",
        "Configure a fact model, or publish a revision",
        "a reviewer must supply the missing mapping",
        # Both were in served output until the contrast rule was added.
        "states what it requires in words rather than as a comparison the engine can compute",
        "This is not a failed policy decision.",
    ):
        assert _FRAMING_RE.search(phrase), phrase

    # And does not fire on the field name, which is allowed.
    assert not _FRAMING_RE.search('"machine_executable": rule.machine_executable')

    # Naming the two routes by the form of the sentence behind them is how a
    # reviewer learns why a record went the way it did, and it stays allowed.
    # "in words" carries nothing on its own -- every document is words -- so the
    # comparison has to be named for the sentence to say anything at all.
    for allowed in (
        "The source states this rule's test in words rather than as a comparison "
        "between named quantities, so a judge settles a case by reading it.",
        "The source states their test in words rather than as a comparison, so a "
        "judge reads the record.",
    ):
        assert not _FRAMING_RE.search(allowed), allowed

    # And the prompt that defines both routes side by side keeps its wording:
    # there the engine's reach describes the route that is the engine's, which is
    # accurate. Narrowing the pattern to the contrastive frame is what lets this
    # stand, and this line is why that narrowing must not be undone.
    assert not _FRAMING_RE.search(
        'A policy is either "deterministic", meaning the source states its test as a '
        'comparison the engine can compute, or "ai_ready", meaning the source states '
        "it in words and a judge decides it by reading the record."
    )


def test_the_exclusion_has_not_blunted_the_guard(tmp_path):
    """The exclusion is narrow: a shipping file is still caught.

    An exclusion is the cheapest way to make a red guard green, and the cheap
    version excludes too much. This runs the scan's own two rules over a file
    named as something that ships and over one named as a test, with identical
    contents, and requires them to disagree. If the exclusion ever widens to the
    point of covering the interface, the first half fails.
    """

    shipped = "  <span>not machine-executable</span>"
    header = "            <span>Executability</span>"

    assert _IS_TEST_FILE.search("PolicyRow.test.tsx")
    assert _IS_TEST_FILE.search("policyCards.spec.ts")
    assert not _IS_TEST_FILE.search("PolicyRow.tsx")
    assert not _IS_TEST_FILE.search("policyCards.ts")
    # A file merely *about* testing still ships, so it is still read.
    assert not _IS_TEST_FILE.search("testScenarioPanel.tsx")

    # Both rules still fire on the wording itself.
    assert _FRAMING_RE.search(shipped)
    assert any(_BARE_EXECUTABILITY.search(caption) for caption in _interface_captions(header))

    # And the scan still reaches real interface files: excluding tests must not
    # have emptied it.
    scanned = _rendered_web_files()
    assert len(scanned) > 50, f"only {len(scanned)} files scanned after the exclusion"
    assert not any(_IS_TEST_FILE.search(path.name) for path in scanned)

    # The exclusion is load-bearing rather than decorative: at least one test
    # file does carry a phrase, which is why it had to exist.
    excluded = [
        path
        for path in WEB.rglob("*.ts*")
        if path.is_file() and _IS_TEST_FILE.search(path.name)
    ]
    assert excluded, "no test files found, so the exclusion hides nothing"
    assert any(
        _FRAMING_RE.search(path.read_text(encoding="utf-8")) for path in excluded
    ), "no excluded test carries the framing, so the exclusion is unnecessary"


def test_the_guard_would_notice_a_bare_executability_caption():
    """Proves the second rule fires on labels and stays off identifiers.

    The first line is the one that shipped. It is a column header in the
    project register, above "0 of 273" for the only project loaded -- a header
    naming a property, and a number reporting almost none of it.
    """

    for line in (
        "            <span>Executability</span>",
        "                stated, not executable",
        "              Select executable",
        '            <span title="Executability">',
        "                non-executable",
        '  { value: "all", label: "Not executable" },',
    ):
        captions = _interface_captions(line)
        assert any(_BARE_EXECUTABILITY.search(caption) for caption in captions), line

    # Identifiers, keys and discriminants. Every one of these is in the
    # interface today, and none of them is language.
    for line in (
        "  machine_executable: boolean;",
        "  machine_executable_count: number;",
        "  executableRuleCount: number | null;",
        'import { machineExecutableFor } from "../ruleExecutability";',
        "      acc.executable += current?.machine_executable_count ?? 0;",
        '  | { kind: "executable"; node: ConditionNode }',
        "      executable: rule.machine_executable,",
        '  testability_reason: "rule_not_machine_executable" | null;',
        'export type AggregateBlocker = "not_machine_executable" | "no_numeric_fact";',
        "        if (row.when.kind === \"executable\") {",
        # The dashboard states the ordinary route correctly, and the variable
        # it interpolates is called `executable`. Reading the expression as
        # text would condemn the one line that gets the wording right.
        "          : `${published - executable} decided by reading`,",
    ):
        offenders = [
            caption
            for caption in _interface_captions(line)
            if _BARE_EXECUTABILITY.search(caption)
        ]
        assert not offenders, f"{line!r} read as display text: {offenders!r}"


def test_every_exemption_is_earned():
    """An exemption that protects nothing is a hole with a comment over it.

    Two ways one rots. The path stops existing, because the file moved and the
    entry kept the old name -- that is how `infrastructure/dmn_parity.py` sat
    here after the real module became `infrastructure/projection/dmn_parity.py`,
    excusing a path nothing occupied. Or the file stays put but loses the phrase
    that earned it, and the entry outlives its reason.

    Either way what remains is not a narrow exemption for a known mechanism. It
    is a standing permission for whatever is written at that path next, and it
    reads as deliberate to whoever finds it. So each entry has to keep paying.
    """

    for path in sorted(_MECHANISM):
        assert path.exists(), (
            f"{path.relative_to(SRC)} is exempt but does not exist. "
            "The entry now excuses whatever lands at that path next -- "
            "point it at the real file, or delete it."
        )
        earned = [
            value for _, value in _string_literals(path) if _FRAMING_RE.search(value)
        ]
        assert earned, (
            f"{path.relative_to(SRC)} is exempt but carries no banned phrase. "
            "Delete the entry rather than leave it standing."
        )


def _rendered_web_files() -> list[Path]:
    """Interface files a user's eyes can reach, which excludes the tests.

    A test that asserts the interface never says "machine executable" has to
    write "machine executable" down to look for it. Scanning tests made this
    guard fire on the sentence stating its own rule, and there is no wording of
    that assertion that would survive: any spelling of the phrase precise enough
    to catch is precise enough to trip on. So the two rules were in a standoff
    no edit to either test could settle, and the scan was the half that was
    wrong -- a test renders to no user, and this guard is about what a user
    reads.

    `test_the_exclusion_has_not_blunted_the_guard` holds the exclusion to being
    narrow: the phrase is still caught in a file that ships.
    """

    return sorted(
        path
        for path in WEB.rglob("*.ts*")
        if path.is_file() and not _IS_TEST_FILE.search(path.name)
    )


def test_no_readiness_framing_in_python_string_literals():
    """Text a user reads, wherever a string ends up being rendered."""

    offenders: list[str] = []
    examined = 0
    for path in sorted(SRC.rglob("*.py")):
        if path in _MECHANISM:
            continue
        for lineno, value in _string_literals(path):
            examined += 1
            match = _FRAMING_RE.search(value)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {value[:70]!r}"
                )

    assert examined > 2000, f"only {examined} strings read; a blind scan finds nothing"
    assert not offenders, "readiness framing in code:\n  " + "\n  ".join(offenders)


def test_no_readiness_framing_in_rendered_web_strings():
    """The interface reaches every user, whatever they upload."""

    offenders: list[str] = []
    examined = 0
    for path in _rendered_web_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            examined += 1
            match = _FRAMING_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {stripped[:70]!r}"
                )

    assert examined > 10000, f"only {examined} lines read; a blind scan finds nothing"
    assert not offenders, "readiness framing in the interface:\n  " + "\n  ".join(offenders)


def test_no_bare_executability_in_interface_captions():
    """The bare noun, wherever a user reads it as the name of a thing."""

    offenders: list[str] = []
    examined = 0
    for path in _rendered_web_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            for caption in _interface_captions(line):
                examined += 1
                match = _BARE_EXECUTABILITY.search(caption)
                if match:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {caption[:70]!r}"
                    )

    assert examined > 2000, f"only {examined} strings read; a blind scan finds nothing"
    assert not offenders, (
        "executability named as a property of a policy:\n  " + "\n  ".join(offenders)
    )


def test_the_caption_scan_reads_the_interface():
    """Guard the guard: an extractor returning nothing would pass on silence.

    The last assertion is the one that matters most. This rule used to read
    only text of six words or fewer, and the strings it missed were the long
    ones. Counting text beyond that length means the scan cannot quietly
    narrow back to captions and still report a clean run -- if the limit
    returns, this figure drops to nothing and says so.
    """

    files = _rendered_web_files()
    assert len(files) > 50, f"only {len(files)} interface files found; the glob is wrong"

    captions = 0
    beyond_a_caption = 0
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            for caption in _interface_captions(line):
                captions += 1
                if len(caption.split()) > 6:
                    beyond_a_caption += 1

    assert captions > 3000, f"only {captions} strings read; the extractor sees no text"
    assert beyond_a_caption > 300, (
        f"only {beyond_a_caption} strings longer than a caption were read; "
        "the scan is reading short text only, which is how the wording it "
        "exists to catch got through the first time"
    )


def test_no_readiness_framing_in_the_documentation():
    """Documentation reaches users too, and it was never checked.

    Scope started at code and the interface, so `docs/` went unscanned. The
    user guide accordingly told a reader to "improve machine-executable
    coverage" and listed it beside publication and ownership as something a
    package should be — presenting the ordinary case as a gap to close, in the
    one document written for the person least able to tell it was wrong.

    `docs/internal/` is excluded for the same reason docstrings are: its whole
    purpose is recording the wording that was removed and why, and none of it
    is published.
    """

    offenders: list[str] = []
    examined = 0
    for path in _scanned_documents():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            examined += 1
            match = _FRAMING_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {line.strip()[:70]!r}"
                )

    assert examined > 3000, f"only {examined} lines read; a blind scan finds nothing"
    assert not offenders, "readiness framing in documentation:\n  " + "\n  ".join(offenders)


def test_the_documentation_scan_reaches_files_and_honours_its_exclusion():
    """Guard the guard: an empty glob or a swallowed root would prove nothing."""

    scanned = _scanned_documents()
    assert len(scanned) > 20, f"only {len(scanned)} documents scanned; the glob is wrong"
    assert (DOCS / "user-guide.md") in scanned

    # Private records are optional local state. Their contents cannot be a
    # precondition for a guard over published text, or identical commits pass on
    # a clean clone and fail on whichever subset a developer happens to retain.
    assert set(scanned).isdisjoint(ignored_documents())


# ---------------------------------------------------------------------------
# ONE NAME PER ROUTE
# ---------------------------------------------------------------------------


def _retired_names_in(text: str) -> list[str]:
    """Every retired route name in a block of text, in the order they appear."""
    return [m.group(0) for m in _RETIRED_RE.finditer(text)]


def test_the_retired_route_names_are_gone_from_the_interface():
    """One route, one name. The interface had been using three at once.

    "Decided by reading", "Human Judgment Requirement" and "AI Ready" were all
    on screen for the same route at the same time. A reader has no way to know
    they are one thing, and the natural reading of three names is three states
    with a record moving between them -- so the route acquires a before and an
    after, and the one that is named last starts to look like the finished one.
    That is the shortfall reading arriving without a shortfall word, which is
    why it belongs in this file and not in a style checklist.

    "AI Ready" is the surviving name. "Deterministic" is its counterpart.
    """

    offenders: list[str] = []
    examined = 0
    for path in _rendered_web_files():
        if path in _AWAITING_ANOTHER_HAND:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            examined += 1
            for found in _retired_names_in(line):
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {found!r} in {line.strip()[:70]!r}"
                )

    assert examined > 10000, f"only {examined} lines read; the scan found no interface"
    assert not offenders, (
        "a retired route name is still on screen -- the route is called "
        "'AI Ready' and its counterpart 'Deterministic':\n  " + "\n  ".join(offenders)
    )


def test_the_retired_route_names_are_gone_from_the_service():
    """The same names reach a user through an API message or a finding."""

    offenders: list[str] = []
    examined = 0
    for path in sorted(SRC.rglob("*.py")):
        for lineno, text in _string_literals(path):
            examined += 1
            for found in _retired_names_in(text):
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {found!r} in {text.strip()[:70]!r}"
                )

    assert examined > 2000, f"only {examined} literals read; the scan found no service"
    assert not offenders, "a retired route name is still served:\n  " + "\n  ".join(offenders)


def test_the_retired_route_names_are_gone_from_the_documentation():
    """Only published documentation is held to the current route vocabulary."""

    offenders: list[str] = []
    examined = 0
    for path in _scanned_documents():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            examined += 1
            for found in _retired_names_in(line):
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {found!r} in {line.strip()[:70]!r}"
                )

    assert examined > 3000, f"only {examined} lines read; a blind scan finds nothing"
    assert not offenders, (
        "a retired route name is still documented:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "wording",
    [
        "Decided by reading",
        "decided by reading",
        "decided-by-reading",
        "Evaluated directly",
        "evaluated-directly",
        "Parties & readiness",
        "Parties &amp; readiness",
        "Parties and readiness",
        "Human Judgment Requirement",
        "human judgement requirement",
        "human-judgment-requirement",
    ],
)
def test_the_guard_would_notice_a_retired_name(wording):
    """Positive control: a rule that matches nothing passes on any tree."""
    assert _retired_names_in(wording), f"{wording!r} would be allowed back"


@pytest.mark.parametrize(
    "wording",
    [
        "AI Ready",
        "ai_ready",
        "Deterministic",
        "Deterministic and AI Ready",
        "a judge reads the rule against the case",
        "a judge decides it by reading the record",
        "the engine computes the comparison",
        "Parties & routes",
        "Required facts",
        "the AI Ready route returns a verdict with its confidence",
    ],
)
def test_the_guard_leaves_the_surviving_names_alone(wording):
    """Negative control: a rule that matches everything forbids the fix itself.

    "a judge decides it by reading the record" is the sentence this codebase
    uses to explain the route in plain words. It has to stay legal, which is
    why the rule wants the past participle -- a name -- and not the verb.
    """
    assert not _retired_names_in(wording), f"{wording!r} was wrongly rejected"


def test_every_retired_name_exemption_is_earned():
    """An exemption outliving its reason is how the wording comes back.

    Each entry must exist AND still carry a retired name. When the hand that
    owns those files fixes them, this test goes red and the entry has to be
    deleted -- the exemption cannot quietly become permanent.

    The set is empty, which is the state this is aiming at, so the loop below
    is a no-op today. It stays because the situation recurs, and because an
    empty set is only trustworthy while something still checks the entries a
    later change adds.
    """

    for path in sorted(_AWAITING_ANOTHER_HAND):
        assert path.exists(), (
            f"{path.relative_to(ROOT)} is exempt but does not exist -- remove the entry"
        )
        assert _retired_names_in(path.read_text(encoding="utf-8")), (
            f"{path.relative_to(ROOT)} no longer carries a retired name; remove it "
            "from _AWAITING_ANOTHER_HAND so the rule covers it again"
        )


def test_the_exemption_has_not_swallowed_the_scan():
    """Guard the guard: exempting the whole interface would pass on nothing."""

    scanned = [p for p in _rendered_web_files() if p not in _AWAITING_ANOTHER_HAND]
    assert len(scanned) > 100, f"only {len(scanned)} files left after exemption"
    assert (WEB / "components" / "ReviewQueue.tsx") in scanned
    assert (WEB / "components" / "ProjectsPage.tsx") in scanned
    assert (WEB / "ruleExecutability.ts") in scanned