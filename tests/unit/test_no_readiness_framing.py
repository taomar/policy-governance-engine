"""Nothing shown to a user reports being decided by reading as a defect.

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

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"
WEB = ROOT / "apps" / "web" / "src"
DOCS = ROOT / "docs"

#: Documents whose purpose is recording the wording that was removed.
_FAILURE_RECORD = DOCS / "failures"

#: Prose that frames being decided by reading as a shortfall.
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
_MECHANISM = {
    SRC / "contracts" / "formulation.py",
}


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
    ):
        assert _FRAMING_RE.search(phrase), phrase

    # And does not fire on the field name, which is allowed.
    assert not _FRAMING_RE.search('"machine_executable": rule.machine_executable')


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


def test_no_readiness_framing_in_python_string_literals():
    """Text a user reads, wherever a string ends up being rendered."""

    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path in _MECHANISM:
            continue
        for lineno, value in _string_literals(path):
            match = _FRAMING_RE.search(value)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {value[:70]!r}"
                )

    assert not offenders, "readiness framing in code:\n  " + "\n  ".join(offenders)


def test_no_readiness_framing_in_rendered_web_strings():
    """The interface reaches every user, whatever they upload."""

    offenders: list[str] = []
    for path in sorted(p for p in WEB.rglob("*.ts*") if p.is_file()):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            match = _FRAMING_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {stripped[:70]!r}"
                )

    assert not offenders, "readiness framing in the interface:\n  " + "\n  ".join(offenders)


def test_no_bare_executability_in_interface_captions():
    """The bare noun, wherever a user reads it as the name of a thing."""

    offenders: list[str] = []
    for path in sorted(p for p in WEB.rglob("*.ts*") if p.is_file()):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            for caption in _interface_captions(line):
                match = _BARE_EXECUTABILITY.search(caption)
                if match:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {caption[:70]!r}"
                    )

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

    files = [p for p in WEB.rglob("*.ts*") if p.is_file()]
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

    `docs/failures/` is excluded for the same reason docstrings are: its whole
    purpose is recording the wording that was removed and why.
    """

    offenders: list[str] = []
    for path in sorted(DOCS.rglob("*.md")):
        if _FAILURE_RECORD in path.parents:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _FRAMING_RE.search(line)
            if match:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {match.group(0)!r} in {line.strip()[:70]!r}"
                )

    assert not offenders, "readiness framing in documentation:\n  " + "\n  ".join(offenders)


def test_the_documentation_scan_reaches_files_and_honours_its_exclusion():
    """Guard the guard: an empty glob or a swallowed root would prove nothing."""

    scanned = [p for p in DOCS.rglob("*.md") if _FAILURE_RECORD not in p.parents]
    assert len(scanned) > 20, f"only {len(scanned)} documents scanned; the glob is wrong"
    assert (DOCS / "user-guide.md") in scanned

    # The exclusion is real, and the excluded records do contain the wording --
    # so excluding them is a deliberate decision, not a way to pass.
    excluded = list(_FAILURE_RECORD.rglob("*.md"))
    assert excluded, "the failure records are missing, so the exclusion hides nothing"
    assert any(
        _FRAMING_RE.search(path.read_text(encoding="utf-8")) for path in excluded
    ), "no excluded document contains the framing, so the exclusion is unnecessary"
