"""A link in a published document must point at something else that is published.

This repository keeps a deliberate local-only tree (`docs/internal/`), and the
documents in it are excluded from the published repository by `.gitignore`. That
arrangement has a failure mode that is invisible from the machine that writes
it: a relative link from a published page to a local-only page resolves
perfectly in the author's editor and 404s for every reader on GitHub.

It had already happened. The published `README.md` linked to
`docs/running-path.md` and `docs/failures/README.md`, both correctly local, so
two rows of the documentation table were dead for everybody who was not the
author. Nothing detected it because both files existed on the workstation, and
the only way to see the defect was to look at the repository as a stranger.

WHY THIS IS ASSERTED AGAINST THE INDEX, NOT THE FILESYSTEM. `Path.exists()` is
the check that cannot find this class of defect, because the file does exist
locally -- that is the whole point. The question is whether git is publishing
it, so the question is put to git.

WHY THERE IS A FLOOR. A link scan that matched nothing would pass silently and
report success, and this repository has shipped a guard that measured an empty
set more than once. The count of links actually examined is asserted before
anything is concluded from it.

WHY THE ANCHOR IS CHECKED SEPARATELY. The file-level scan above deliberately
discards everything after `#`, so a link naming a heading that does not exist
passes it. That defect is quieter than a 404: GitHub serves the page and
silently leaves the reader at the top, so the link looks like it worked. It is
the same "invisible from the machine that wrote it" class, one level down, and
it is checked below.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]

#: `[text](target)` -- the only link form that can point at a repository path.
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

#: Links that name a location rather than a repository file.
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:")

#: An ATX heading, which is the only heading form used in this documentation.
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.MULTILINE)

#: Prefixes that make a link external for anchor purposes. `#` is absent here
#: on purpose: a bare `#anchor` is a same-page link and is worth checking.
_OFFSITE_PREFIXES = ("http://", "https://", "mailto:", "tel:")


def _tracked() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, errors="replace"
    )
    return {line for line in result.stdout.splitlines() if line}


def _normalise(base: Path, target: str) -> str:
    """Resolve `target` relative to `base` without touching the filesystem."""

    parts: list[str] = []
    for segment in (base / target).as_posix().split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment not in ("", "."):
            parts.append(segment)
    return "/".join(parts)


def _published_links() -> tuple[list[tuple[str, str, str]], int]:
    """Every relative link in a published markdown file, and how many were seen."""

    tracked = _tracked()
    directories = {Path(path).parent.as_posix() for path in tracked}

    broken: list[tuple[str, str, str]] = []
    examined = 0

    for path in sorted(p for p in tracked if p.endswith(".md")):
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        base = Path(path).parent
        for raw in _LINK.findall(text):
            target = unquote(raw.split("#")[0].strip())
            if not target or target.startswith(_EXTERNAL_PREFIXES):
                continue
            examined += 1
            resolved = _normalise(base, target)
            if resolved in tracked or resolved.rstrip("/") in directories:
                continue
            broken.append((path, raw, resolved))

    return broken, examined


def test_the_link_scan_examines_a_realistic_number_of_links():
    """The floor. An empty scan passes the assertion below while checking nothing."""

    _, examined = _published_links()
    assert examined > 100, (
        f"only {examined} relative links found across the published documentation; "
        "the scan is not reading what it thinks it is reading"
    )


def test_no_published_document_links_to_an_unpublished_one():
    broken, _ = _published_links()

    assert broken == [], "published documents link to files that are not published:\n" + "\n".join(
        f"  {source}\n      -> {written!r} resolves to {resolved!r}, which git does not track"
        for source, written, resolved in broken
    ) + (
        "\n\nA reader of the public repository gets a 404 for each of these, while the "
        "link resolves for whoever wrote it. Either publish the target, or stop linking "
        "to it and describe the material instead -- see `docs/internal/README.md`."
    )


def _slug(title: str) -> str:
    """The anchor GitHub derives from a heading.

    Follows `github-slugger`: strip inline markup, lowercase, drop everything
    that is not a word character, whitespace or hyphen, then map each space to
    one hyphen.

    THE SPACE RULE IS NOT A DETAIL. Runs of whitespace are NOT collapsed. A
    heading written with an em dash loses the dash as punctuation but keeps the
    space on either side, so ``Running locally \u2014 step by step`` becomes
    ``running-locally--step-by-step`` with two hyphens. An implementation that
    collapses whitespace reports three correct links in this repository as
    broken, which is how this function was first written and caught. Note that
    an ASCII hyphen is a different case: it SURVIVES the punctuation strip, so
    ``a - b`` yields ``a---b``, three hyphens, not two.
    """

    text = title.strip()
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def _without_fenced_blocks(text: str) -> str:
    """Blank fenced code so shell comments are not read as headings.

    A ``# frontend lint`` line inside a fenced block is a comment, not a
    heading, and GitHub serves no anchor for it. Collecting it would only ever
    make this guard ACCEPT a link that 404s, never reject a good one -- so this
    is closing a latent hole rather than a live defect. Lines are blanked
    rather than removed so that nothing downstream depends on line numbering.
    """

    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.lstrip()
        if fence is None:
            marker = re.match(r"(`{3,}|~{3,})", stripped)
            if marker:
                fence = marker.group(1)[0]
                out.append("")
                continue
            out.append(line)
        else:
            out.append("")
            if re.match(rf"{fence}{{3,}}\s*$", stripped):
                fence = None
    return "\n".join(out)


def _anchors_of(text: str) -> set[str]:
    """Every anchor a reader can reach in one markdown document.

    Repeated headings get the `-1`, `-2` suffixes GitHub appends, so a document
    with two `### Notes` sections offers both `#notes` and `#notes-1`.
    """

    seen: Counter[str] = Counter()
    anchors: set[str] = set()
    for _, title in _HEADING.findall(_without_fenced_blocks(text)):
        base = _slug(title)
        if not base:
            continue
        index = seen[base]
        seen[base] += 1
        anchors.add(base if index == 0 else f"{base}-{index}")
    return anchors


def _anchor_links(sources: dict[str, str] | None = None) -> tuple[list[tuple[str, str, str]], int]:
    """Every in-repo anchor link, and how many were actually examined.

    `sources` overrides file contents by path, so a control can prove this
    refuses a heading that is not there without editing a published document.
    """

    overrides = sources or {}
    tracked = {path for path in _tracked() if path.endswith(".md")}

    def read(path: str) -> str:
        if path in overrides:
            return overrides[path]
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")

    broken: list[tuple[str, str, str]] = []
    examined = 0

    for path in sorted(tracked):
        base = Path(path).parent
        for raw in _LINK.findall(read(path)):
            raw = raw.strip()
            if raw.startswith(_OFFSITE_PREFIXES) or "#" not in raw:
                continue
            file_part, _, anchor = raw.partition("#")
            anchor = unquote(anchor).strip()
            if not anchor:
                continue
            target = path if not file_part else _normalise(base, unquote(file_part))
            if target not in tracked:
                # An unpublished target is the file-level guard's finding, not
                # this one's. Reporting it twice would blame one defect on two
                # checks and obscure which is failing.
                continue
            examined += 1
            if anchor not in _anchors_of(read(target)):
                broken.append((path, raw, target))

    return broken, examined


def test_the_anchor_scan_examines_a_realistic_number_of_links():
    """The floor. Zero anchors examined passes the assertion below vacuously."""

    _, examined = _anchor_links()
    assert examined > 40, (
        f"only {examined} in-repo anchor links found across the published documentation; "
        "the anchor scan is not reading what it thinks it is reading"
    )


def test_no_published_document_links_to_a_heading_that_does_not_exist():
    broken, _ = _anchor_links()

    assert broken == [], "published documents link to headings that do not exist:\n" + "\n".join(
        f"  {source}\n      -> {written!r} names no heading in {target}"
        for source, written, target in broken
    ) + (
        "\n\nGitHub serves the page and leaves the reader at the top, so this looks "
        "like it worked. Either fix the anchor to match the heading, or change the "
        "heading and every link that names it."
    )


def test_the_anchor_scan_refuses_an_anchor_that_names_no_heading():
    """The control.

    Without this, the guard above could be passing because it finds nothing
    rather than because everything is correct. A document is rewritten in
    memory to point at a heading it does not contain, and the scan must say so
    -- and must still pass every other link, so it is refusing this one thing
    and not simply refusing.

    ASSERTED AGAINST A BASELINE, NOT AGAINST ZERO. An absolute
    ``len(broken) == 1`` would also fail the moment a genuine broken anchor
    lands, and would then blame the scan -- "a check that refuses everything"
    -- while the real guard above is simultaneously reporting the actual
    defect. Taking the baseline from an untampered run proves the same
    non-vacuity property and fails only for the reason it names.
    """

    source = "docs/README.md"
    original = (ROOT / source).read_text(encoding="utf-8")
    tampered = original + "\n\n[a heading that is not there](api.md#no-such-heading-anywhere)\n"

    baseline, _ = _anchor_links()
    broken, examined = _anchor_links({source: tampered})

    assert (source, "api.md#no-such-heading-anywhere", "docs/api.md") in broken, (
        "the anchor scan did not refuse a link naming a heading that does not exist; "
        "it cannot detect the defect it exists to detect"
    )
    assert len(broken) == len(baseline) + 1, (
        f"tampering added {len(broken) - len(baseline)} findings when it should have added "
        f"exactly one (baseline {len(baseline)}, tampered {len(broken)}). A check that "
        "refuses more than what changed is not evidence that this one is wrong."
    )
    assert examined > 40, "the control changed how much the scan examines"


def test_the_slug_keeps_the_double_hyphen_an_em_dash_leaves_behind():
    """Guards the rule that made three correct links look broken.

    Asserted directly because it is the one part of the slug that is easy to
    write plausibly and wrongly, and a wrong version fails closed -- it reports
    good links as defects, which trains a reader to ignore this test.
    """

    assert _slug("Running locally \u2014 step by step") == "running-locally--step-by-step"
    assert _slug("`additional_instructions` \u2014 what a caller may steer") == (
        "additional_instructions--what-a-caller-may-steer"
    )
    assert _slug("Timing and token telemetry") == "timing-and-token-telemetry"
    assert _slug("What `low` measured, on one corpus") == "what-low-measured-on-one-corpus"
    # An ASCII hyphen survives the strip, so it is NOT the em-dash case.
    assert _slug("Running locally - step by step") == "running-locally---step-by-step"


def test_a_heading_inside_a_fenced_block_is_not_an_anchor():
    """A shell comment is not a heading, however much it looks like one.

    Getting this wrong can only make the guard ACCEPT a link that 404s on
    GitHub, so it fails open. The control below proves real headings on either
    side of the fence are still collected, so the fence stripper is not simply
    discarding the document.
    """

    document = "\n".join(
        [
            "# Real heading",
            "",
            "```bash",
            "# frontend lint",
            "npm run lint",
            "```",
            "",
            "~~~",
            "# tilde fenced comment",
            "~~~",
            "",
            "## Another real heading",
        ]
    )

    anchors = _anchors_of(document)

    assert "real-heading" in anchors and "another-real-heading" in anchors, (
        f"real headings were lost by the fence stripper: {sorted(anchors)}"
    )
    assert "frontend-lint" not in anchors, "a comment inside a fenced block was read as a heading"
    assert "tilde-fenced-comment" not in anchors, "a tilde-fenced block was not recognised"

