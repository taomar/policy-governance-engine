"""A refused reply is a sample of the model, not a fact about the passage.

Two behaviours here, and real corpus readings drove both of them. Neither is a
measurement written into logic: the readings said *that* a rule was wrong, and
the rules that replaced them are stated structurally, so they behave the same on
a document nobody has read.

The first: a mark with a letter on either side of it is part of a word. A
passage whose own heading contains a typographic apostrophe was refused a label
for containing that same apostrophe, which made the check hostile to every
language that writes elision or possession with one.

The second: the model was asked once, and one reply that failed validation was
stored as the passage's outcome. Asked a second time, the same passage, the same
words and the same prompt frequently produced a usable subject name -- so the
stored outcome was recording which sample arrived first.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from policy_platform.infrastructure.assistants.provision_topic_label import (
    ASK_ATTEMPTS,
    UNAVAILABLE_MODEL_FAILED,
    UNAVAILABLE_REPLY_UNUSABLE,
    LabelSource,
    build_source,
    generate_label,
    validate_label,
)

_MODULE = Path("src/policy_platform/infrastructure/assistants/provision_topic_label.py")


def _source(*texts: str) -> LabelSource:
    return build_source(["A heading"], list(texts))


# --------------------------------------------------------------------------
# a mark inside a word is part of the word
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Employees\u2019 travel day",  # typographic apostrophe
        "Employees' travel day",  # typewriter apostrophe
        "L\u2019emploi du personnel",  # elision, another language
        "Kanunu\u2019n uygulanmasi",  # a suffix joined by an apostrophe
    ],
)
def test_a_mark_joining_two_letters_does_not_refuse_a_label(reply: str) -> None:
    """The document writes words this way, so a label may too."""

    source = _source(reply + " and some further words of the passage")
    label, code = validate_label(reply, source)
    assert code is None, f"{reply!r} was refused"
    assert label == reply


@pytest.mark.parametrize(
    "reply",
    [
        "Working hours\u201d",  # a stray closing quote
        "He said \u201chours\u201d then",  # quotes around one word inside
        "Working hours \u2019 deductions",  # an apostrophe touching no letter
        "Working hours.",  # a statement's full stop
        "Hours, deductions",  # a clause comma
        "\u0633\u0627\u0639\u0627\u062a \u0627\u0644\u0639\u0645\u0644\u060c",
    ],
)
def test_a_mark_that_separates_runs_still_refuses_a_label(reply: str) -> None:
    """Sentence machinery is always followed by a space or by nothing."""

    source = _source(reply + " plus the rest of what the passage said")
    label, code = validate_label(reply, source)
    assert label is None, f"{reply!r} was accepted"
    assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_a_pair_wrapping_the_whole_reply_is_a_habit_not_a_quotation() -> None:
    """Stripping it is deliberate; what is left still has to survive every check."""

    source = _source("The passage said something about working hours here")
    label, code = validate_label('"Working hours"', source)
    assert code is None
    assert label == "Working hours"


def test_the_word_rule_consults_no_language() -> None:
    """It decides from position, never from which characters a language uses."""

    from policy_platform.infrastructure.assistants import provision_topic_label

    tree = ast.parse(inspect.getsource(provision_topic_label._marks_between_words))
    function = tree.body[0]
    own_docstring = function.body[0].value
    leaked = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node is not own_docstring
        and any(char.isalpha() for char in node.value)
    ]
    assert not leaked, f"the rule reads a word out of a literal: {leaked}"


# --------------------------------------------------------------------------
# a refused reply is asked again
# --------------------------------------------------------------------------


class _Replies:
    """A client that hands back a scripted reply per call and counts the calls."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.calls = 0

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ARG002
        self.calls += 1
        return self._replies[min(self.calls - 1, len(self._replies) - 1)]


class _Raises:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ARG002
        self.calls += 1
        raise self._error


@pytest.mark.asyncio
async def test_a_usable_reply_is_taken_without_asking_again() -> None:
    client = _Replies("Working hours")
    source = _source("The passage says something about working hours here")

    attempt = await generate_label(source, client=client)

    assert attempt.label == "Working hours"
    assert client.calls == 1, "a usable reply was second-guessed"


@pytest.mark.asyncio
async def test_a_reply_that_is_not_a_subject_name_is_asked_again() -> None:
    client = _Replies(
        "Employees must work forty hours every week without exception at all.",
        "Working hours",
    )
    source = _source("The passage says something about working hours here")

    attempt = await generate_label(source, client=client)

    assert client.calls == 2, "one refused sample was recorded as the outcome"
    assert attempt.label == "Working hours"
    assert attempt.unavailable_code is None


@pytest.mark.asyncio
async def test_asking_again_is_bounded() -> None:
    """A validator that is asked until something passes has stopped deciding."""

    client = _Replies("Employees must work forty hours every single week here.")
    source = _source("The passage says something about working hours here")

    attempt = await generate_label(source, client=client)

    assert client.calls == ASK_ATTEMPTS
    assert attempt.label is None
    assert attempt.unavailable_code == UNAVAILABLE_REPLY_UNUSABLE


@pytest.mark.asyncio
async def test_a_service_that_refuses_the_text_is_not_asked_again() -> None:
    """Repeating a decision about the text only spends the quota twice."""

    client = _Raises(RuntimeError("content management policy"))
    source = _source("The passage says something about working hours here")

    attempt = await generate_label(source, client=client)

    assert client.calls == 1
    assert attempt.unavailable_code == UNAVAILABLE_MODEL_FAILED


@pytest.mark.asyncio
async def test_asking_again_changes_nothing_a_reader_is_told() -> None:
    """The second ask is how the label was obtained, not what it claims."""

    once = _Replies("Working hours")
    twice = _Replies("Employees shall work forty hours in every week.", "Working hours")
    source = _source("The passage says something about working hours here")

    first = await generate_label(source, client=once)
    second = await generate_label(source, client=twice)

    assert first.label == second.label
    assert first.source_digest == second.source_digest
    assert first.prompt_version == second.prompt_version


def test_the_ceiling_on_asking_is_named_not_written_into_the_loop() -> None:
    """So it can be argued about, and so no reading of a corpus hides in it."""

    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    generate = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_label"
    )
    ranges = [
        node
        for node in ast.walk(generate)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    ]
    assert ranges, "the ask is not bounded by a range at all"
    for node in ranges:
        for arg in node.args:
            assert not isinstance(arg, ast.Constant), (
                "the number of asks is a literal in the loop; name it instead"
            )
