"""A route named beside a shortfall, in one breath.

`test_no_readiness_framing.py` forbids particular phrasings, and it works: five
attempts to say the forbidden thing were caught by it. What it cannot catch is
the sixth, because a lexicon only knows the wordings somebody has already
written down. Every evasion so far has had the same shape and a new vocabulary.

That shape is what this scans for. Whatever words are used, framing a decision
route as a shortfall requires naming the route and naming a shortfall close
enough together for a reader to join them -- which in practice means in one
sentence. So this reads the copy a sentence at a time, and fails any sentence
that names a route and, separately, says something is lacking, broken or less.

Three details make it usable rather than noisy.

**Only the route decided by reading is scanned.** The other route is this app's
own machinery, and a sentence about what our machinery does not do is a fact
about our machinery. `test_no_readiness_framing.py` had already found this
distinction from the other side and wrote it down: describing the engine's
reach is accurate where the engine is the subject, and is the fault where the
subject is the route the engine does not decide. Scanning both halves here
produced six reports over existing copy and every one of them was correct
prose about the evaluator's own behaviour.

**The route match is masked** before the shortfall scan runs, so a route term
that happens to contain an ordinary word -- and one of them does -- can never
report itself.

**The vocabulary is assembled from atoms**, never written out, for the reason
`policy_explainer` gives: written adjacently, some of these phrasings are ones
the older guard forbids in a string literal, and that guard cannot tell a
phrase quoted as data from one written as language.

The shortfall lexicon is about condition and not about topic: a sentence may
say a document is missing a page, and does, all over this repository. It may
not say so in the same sentence in which it names how a rule is decided.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"
WEB = ROOT / "apps" / "web" / "src"
DOCS = ROOT / "docs"

#: Documents whose purpose is recording the wording that was removed. The same
#: exclusion the older guard makes, for the same reason.
_FAILURE_RECORD = DOCS / "failures"

#: The route whose test is decided by a person reading it. Word sequences, so
#: the hyphenated, spaced and underscored spellings are all covered without any
#: of them being written down here.
_READING_ROUTE: tuple[tuple[str, ...], ...] = (
    ("ai", "ready"),
    ("documentation", "only"),
    ("manual", "review"),
    ("judge", "reads"),
    ("decided", "by", "reading"),
)
_ROUTE_RE = re.compile(
    rf"\b(?:{'|'.join(r'[-_ ]'.join(words) for words in _READING_ROUTE)})\b",
    re.IGNORECASE,
)

#: Words that say a thing is lacking, broken, or less than another thing.
#:
#: Chosen for what they assert rather than what they are about. Each is
#: word-bounded, because these are short words that live inside longer ones --
#: `gap` inside `gaps` is the same claim, `gap` inside `propagate` is not a
#: claim at all.
_SHORTFALL = (
    r"cannot",
    r"can ?not",
    r"can't",
    r"could not",
    r"unable",
    r"fail(?:s|ed|ing|ure|ures)?",
    r"deficien\w+",
    r"limitation\w*",
    r"shortcoming\w*",
    r"shortfall\w*",
    r"falls? short",
    r"gap\b",
    r"gaps\b",
    r"lack(?:s|ed|ing)?\b",
    r"missing",
    r"absent",
    r"incomplete",
    r"insufficient",
    r"inadequate",
    r"unsupported",
    r"not supported",
    r"weakness\w*",
    r"defect\w*",
    r"degraded",
    r"inferior",
    r"lesser",
    r"vaguer",
    r"vague",
    r"unfortunately",
    r"stuck",
    r"blocked",
    r"unresolved",
)
_SHORTFALL_RE = re.compile(rf"\b(?:{'|'.join(_SHORTFALL)})\b", re.IGNORECASE)

#: Code embedded in a line of interface, removed before the text is read.
_EXPRESSION = re.compile(r"\$?\{[^{}]*\}")
_TAG = re.compile(r"<[^<>]*>")
_QUOTED = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'|`([^`\n]*)`")

#: Punctuation that survives only in code.
#:
#: Deliberately one character narrower than the older guard's set, which counts
#: a colon as code. A caption ending in a colon is ordinary -- it is how a label
#: introduces the value beside it, and it is how this feature's own caption is
#: written -- and treating it as code makes every such caption invisible to the
#: scan. Found by mutation: a caption naming a route beside a shortfall was
#: injected into this feature's component, both guards passed, and the colon at
#: the end of the line was the whole reason.
#:
#: An expression or a tag is stripped before this is consulted, so the colons
#: that belong to type annotations and object literals never reach it.
_CODE_PUNCTUATION = set("{}()[]<>=;|&$#\"'`/\\")

#: A sentence ends at a stop, a question or an exclamation -- in either script's
#: punctuation -- or at a line break, which in this repository's prose is where
#: a bullet or a comment line ends.
_SENTENCE_END = re.compile(r"(?<=[.!?؟…])\s+|\n+|(?: -- )|(?: — )")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text or "") if part and part.strip()]


def _fingerprint(sentence: str) -> str:
    """A stable key for one sentence, case and spacing ignored."""

    return hashlib.sha256(" ".join(sentence.split()).casefold().encode("utf-8")).hexdigest()[:16]


#: Sentences that name a route beside a shortfall on purpose, in order to
#: forbid that phrasing. There is one, and it is a line of a system prompt
#: telling a model not to write the frame this guard exists to catch. A rule
#: that cannot tell a phrasing quoted as data from one written as language will
#: report it, and deleting it from the prompt would remove the instruction that
#: keeps the frame out of generated copy.
#:
#: Kept by fingerprint rather than by file, and rather than by writing the
#: sentence out. By file would be a standing permission for whatever is written
#: at that path next. Written out, this file would carry the phrasing the older
#: guard forbids, in a repository where five phrasings have already escaped by
#: being written somewhere nobody was scanning.
#:
#: A fingerprint stops matching the moment the sentence is edited, which is
#: exactly when somebody should look at it again.
_QUOTED_TO_FORBID_IT = {
    "aed132a967eb0905": "a system prompt line forbidding the frame",
}


def frames_a_route_as_a_shortfall(text: str) -> list[str]:
    """The sentences in `text` that name a route and a shortfall together.

    The route match is replaced with a space before the shortfall scan, so a
    route term is never itself read as one -- `documentation only` and the like
    are route vocabulary, and the sentence naming them says nothing about
    anything being wrong.
    """

    offenders: list[str] = []
    for sentence in _sentences(text):
        if not _ROUTE_RE.search(sentence):
            continue
        without_routes = _ROUTE_RE.sub(" ", sentence)
        if _SHORTFALL_RE.search(without_routes):
            if _fingerprint(sentence) in _QUOTED_TO_FORBID_IT:
                continue
            offenders.append(sentence)
    return offenders


def _string_literals(path: Path) -> list[tuple[int, str]]:
    """Every string literal in a Python file, excluding docstrings.

    A docstring is read by whoever edits the module and is where the reasoning
    for a decision belongs, including the reasoning about routes. What a user
    reads is what this scans.
    """

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
            if id(node) not in docstrings:
                found.append((node.lineno, node.value))
    return found


def _interface_captions(line: str) -> list[str]:
    """The display text on one line of interface source.

    Text between tags is rendered by construction; a quoted string is rendered
    when it reads as language rather than as a value. Code is removed first so
    an expression is never mistaken for the text around it.
    """

    captions: list[str] = []

    text = line
    previous = None
    while previous != text:
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


class TestTheGuardWorks:
    """Without these, a scan that matched nothing would pass everything."""

    def test_it_catches_a_route_called_a_shortfall(self) -> None:
        route = " ".join(["manual", "review"])
        for shortfall in ("cannot be checked here", "is a limitation of the engine"):
            sentence = f"A rule sent to {route} {shortfall}."
            assert frames_a_route_as_a_shortfall(sentence) == [sentence.strip()], sentence

    def test_it_catches_a_wording_no_lexicon_lists(self) -> None:
        """The case the older guard is blind to: nothing here is a forbidden
        phrase, and the sentence still tells a reader the route is the poorer
        one."""

        route = " ".join(["ai", "ready"])
        sentence = f"We are unable to do better than {route} for this one."
        assert frames_a_route_as_a_shortfall(sentence) == [sentence]

    def test_it_leaves_a_route_named_plainly_alone(self) -> None:
        route = " ".join(["ai", "ready"])
        assert frames_a_route_as_a_shortfall(f"This rule is {route}.") == []
        assert frames_a_route_as_a_shortfall(f"{route}: a judge reads it.") == []

    def test_it_leaves_a_shortfall_with_no_route_alone(self) -> None:
        """Copy about a missing page, a failed call or an absent answer is
        ordinary and appears throughout. Only the pairing is the fault."""

        for sentence in (
            "The page is missing from this document.",
            "The call failed and nothing was stored.",
            "No answer has been generated yet.",
        ):
            assert frames_a_route_as_a_shortfall(sentence) == [], sentence

    def test_a_route_term_is_not_read_as_its_own_shortfall(self) -> None:
        """One route term carries a word that reads as a restriction. Masking
        the route first is what keeps this guard off correct copy."""

        route = " ".join(["documentation", "only"])
        assert frames_a_route_as_a_shortfall(f"This rule is {route}.") == []

    def test_two_sentences_are_two_sentences(self) -> None:
        """Scoping is the rule. A paragraph that names a route and, elsewhere,
        says a document is missing a page has said nothing joining them."""

        route = " ".join(["ai", "ready"])
        text = f"This rule is {route}. The next page is missing."
        assert frames_a_route_as_a_shortfall(text) == []

    def test_every_exemption_is_earned(self) -> None:
        """An exemption matching nothing in the tree is a rule nobody holds.

        Each fingerprint has to still name a real sentence somewhere in the
        source, and that sentence has to still be one this scan would report.
        A fingerprint that matches nothing means the copy it excused has been
        edited, and the exemption has to go with it.
        """

        seen: set[str] = set()
        for path in sorted(SRC.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for _, value in _string_literals(path):
                for sentence in _sentences(value):
                    if not _ROUTE_RE.search(sentence):
                        continue
                    if _SHORTFALL_RE.search(_ROUTE_RE.sub(" ", sentence)):
                        seen.add(_fingerprint(sentence))

        unearned = set(_QUOTED_TO_FORBID_IT) - seen
        assert unearned == set(), sorted(unearned)


class TestTheCopyIsClean:
    def test_no_python_string_literal_frames_a_route_that_way(self) -> None:
        scanned = 0
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            for line, value in _string_literals(path):
                for sentence in frames_a_route_as_a_shortfall(value):
                    offenders.append(f"{path.relative_to(ROOT)}:{line}: {sentence}")
        assert scanned > 100, scanned
        assert offenders == [], offenders

    def test_no_interface_caption_frames_a_route_that_way(self) -> None:
        scanned = 0
        offenders: list[str] = []
        for path in sorted(p for p in WEB.rglob("*.ts*") if p.is_file()):
            scanned += 1
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for caption in _interface_captions(line):
                    for sentence in frames_a_route_as_a_shortfall(caption):
                        offenders.append(f"{path.relative_to(ROOT)}:{number}: {sentence}")
        assert scanned > 50, scanned
        assert offenders == [], offenders

    def test_no_document_frames_a_route_that_way(self) -> None:
        scanned = 0
        offenders: list[str] = []
        for path in sorted(DOCS.rglob("*.md")):
            if _FAILURE_RECORD in path.parents:
                continue
            scanned += 1
            for sentence in frames_a_route_as_a_shortfall(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.relative_to(ROOT)}: {sentence}")
        assert scanned > 10, scanned
        assert offenders == [], offenders
