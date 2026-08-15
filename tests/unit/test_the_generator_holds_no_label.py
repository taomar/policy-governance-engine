"""The generator knows no subjects, and the label is never the document's words.

TWO PROPERTIES, ONE FILE, BECAUSE THEY ARE THE SAME PROPERTY SEEN TWICE

A generated label is safe only if two things hold at once. It must not come from
this system's own idea of what documents are about — otherwise it describes our
assumptions rather than the customer's text. And it must not be filed anywhere a
consumer reads the document's characters — otherwise it becomes evidence.

WHY THE FIRST IS ASSERTED THROUGH THE SYNTAX TREE

`test_no_domain_specific_wording.py` already scans this module for named terms,
which catches a leaked word. It cannot catch a leaked *structure*: a fallback
string, a table of defaults, a rewrite of a rejected reply into something
plausible. Those need no domain word to be a taxonomy — the taxonomy would be
the shape of the code.

So what is asserted is that no literal written in the generator can ever reach a
stored label. The value assigned to `label` comes from the model's reply and
from nowhere else, and the syntax tree is where that is decidable.

A first attempt asserted instead that no string literal in the module would pass
the validator. That is unsound: the role names a chat request needs would pass
it, and so would half the identifiers in any module. Passing that test would
have meant nothing.

WHY THE SECOND IS ASSERTED THROUGH FIELD NAMES AND NOT THROUGH CHARACTERS

A good subject name legitimately reuses the document's nouns — that is what
naming a subject is. Forbidding overlap would push generation towards
paraphrase, which reads *less* like the document while being no safer.

What is provable, and what actually protects a reader, is placement: the label
never enters a field that carries the source's characters, it leaves the system
under its own key with its own provenance, and the interface renders it outside
the title and outside every quotation. Those are asserted here and in
`apps/web/src/policyCards.test.ts`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from policy_platform.domain.models import DocumentProvision, ProvisionTopicLabel

_MODULE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "policy_platform"
    / "infrastructure"
    / "assistants"
    / "provision_topic_label.py"
)


def _tree() -> ast.Module:
    return ast.parse(_MODULE.read_text(encoding="utf-8"))


def _prompt_literals() -> list[str]:
    """Every instruction the module states, read off the source rather than run.

    Read from the syntax tree so these hold whether or not a model is reachable:
    what is being checked is what this repository asks for, which is a property
    of the file.
    """

    return [
        node.value.value
        for node in ast.walk(_tree())
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id.endswith("_PROMPT")
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]


def _label_assignments(tree: ast.Module) -> list[ast.expr]:
    """Every value the module hands over as a label, wherever it does so."""

    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in {"label", "label_text"}:
            found.append(node.value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in {
                    "label",
                    "label_text",
                }:
                    found.append(node.value)
    return found


def test_the_generator_hands_over_a_label_in_more_than_one_place() -> None:
    """Guards the guard.

    A test that scans for assignments proves nothing if the scan finds none —
    it would pass just as well against a file that no longer generates
    anything. This fails if the shape it depends on has moved.
    """

    assert len(_label_assignments(_tree())) >= 2


def test_no_label_the_generator_hands_over_is_written_in_it() -> None:
    """The subject of a document is never named out of this system's vocabulary.

    Every value that becomes a label must be a name or an attribute — something
    carrying what came back from the model. A literal here would be this system
    deciding what a passage is about, which is the one thing the product exists
    not to do, and it needs no recognisable word to be exactly that.
    """

    for value in _label_assignments(_tree()):
        if isinstance(value, ast.Constant) and value.value is None:
            # The absence of a label, which is a legitimate outcome and is not
            # a label. Everything else written in this file would be.
            continue
        assert not isinstance(value, ast.Constant | ast.JoinedStr | ast.FormattedValue), (
            "a label must come from the model's reply, never from this file"
        )
        assert isinstance(value, ast.Name | ast.Attribute), (
            "a label must be handed over as a value read from the reply"
        )


def test_the_generator_hands_over_at_least_one_label_it_did_not_write() -> None:
    """Guards the exemption above.

    The `None` exemption would swallow the whole test if every hand-over were a
    `None` — the file would pass while generating nothing. At least one value
    must be read from the reply.
    """

    values = _label_assignments(_tree())
    assert any(isinstance(value, ast.Name | ast.Attribute) for value in values)


def test_the_instruction_settles_which_language_without_naming_one() -> None:
    """A passage written twice over, in two languages, has no single language.

    The generator must therefore answer the question rather than leave it to
    whichever language the model happened to read most of — an unstated rule is
    one that changes between runs. But answering it must not smuggle in a
    preference for a particular language or script, which would be building for
    one corpus. So: the rule must be present, and it must be expressible without
    naming any language, script, direction or writing system.
    """

    tree = _tree()
    prompts = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id.endswith("_PROMPT")
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert prompts, "the module must state its instruction as a literal to be checkable"

    settled = [p for p in prompts if "more than one language" in p.lower()]
    assert settled, (
        "the instruction must say which language wins when the text uses several, "
        "or the answer varies run to run for the same passage"
    )

    # Whatever it says, it must say it about no language in particular. These are
    # not a list of the languages this corpus happens to contain -- they are the
    # words by which any instruction would have to name a specific one at all.
    for prompt in prompts:
        lowered = prompt.lower()
        for naming in (
            "english",
            "arabic",
            "latin",
            "roman",
            "right-to-left",
            "left-to-right",
            "rtl",
            "ltr",
            "translate",
            "translation",
        ):
            assert naming not in lowered, (
                f"the instruction must not name a language or script: {naming}"
            )


def test_the_instruction_separates_the_subject_from_what_is_merely_mentioned() -> None:
    """Naming something present in the text is not naming what it is about.

    Measured against the corpus, this was the whole of the wrongness: a passage
    directing readers to an office came back named after that office, and two
    unrelated introductory passages both came back named after the document they
    introduce. Each of those names is a true statement about something in the
    text and a false statement about what the text is about, and a false subject
    sitting above verbatim evidence is worse than an absent one.

    So the instruction must draw that distinction itself. It must also require
    the answer to separate this part of a document from the rest of it -- a name
    that fits every part identifies none, and two passages coming back with the
    same name is the observable form of that failure.

    Both requirements are about the shape of an answer. Neither may be met by
    naming a subject, a category or a kind of thing this corpus contains, which
    is what the second half of this test holds.
    """

    prompts = _prompt_literals()
    assert prompts, "the module must state its instruction as a literal to be checkable"
    joined = " ".join(prompts).lower()

    assert "not something the text mentions" in joined or "mentions" in joined, (
        "the instruction must distinguish what the text is about from what it "
        "names in passing, or a mentioned entity will keep coming back as a subject"
    )
    assert "document as a whole" in joined, (
        "the instruction must forbid naming the whole document, or two different "
        "parts of one document can come back with the same name"
    )
    assert "no subject you can name" in joined, (
        "declining must be offered as an answer, or the model must guess when "
        "there is nothing honest to say"
    )

    # And none of it may be bought with vocabulary. These are the words by which
    # a prompt would have to point at a kind of subject at all -- not a list of
    # what this corpus contains. Matched at a word boundary rather than as bare
    # substrings, because a substring check finds "hr" inside "phrase" and would
    # fail on an instruction that names nothing.
    for naming in (
        "policy",
        "policies",
        "employee",
        "leave",
        "attendance",
        "salary",
        "hr",
        "human resources",
        "handbook",
        "staff",
        "department",
        "topic such as",
        "categor",
    ):
        assert not re.search(rf"\b{re.escape(naming)}", joined), (
            f"the instruction must not name a subject or a kind of subject: {naming}"
        )


def test_a_decline_is_recorded_apart_from_a_reply_that_could_not_be_used() -> None:
    """Two different facts about a passage must not be filed under one code.

    "I was asked and there is no subject here to name" and "a reply arrived and
    did not hold a name" say different things. The first is an answer about the
    passage; the second is an accident of one call. Only the second is worth
    asking again about, and a reviewer looking at why a policy has no name is
    owed the difference.
    """

    from policy_platform.infrastructure.assistants.provision_topic_label import (
        DECLINE_REPLY,
        UNAVAILABLE_DECLINED,
        UNAVAILABLE_REPLY_UNUSABLE,
        LabelSource,
        validate_label,
    )

    source = LabelSource(
        heading_path=("A heading",),
        texts=("Some words the document wrote.",),
        rule_count=1,
    )

    label, code = validate_label(DECLINE_REPLY, source)
    assert label is None
    assert code == UNAVAILABLE_DECLINED

    # Case is not part of the answer.
    assert validate_label(DECLINE_REPLY.lower(), source)[1] == UNAVAILABLE_DECLINED

    # And the two codes stay distinguishable, which is the entire point.
    assert UNAVAILABLE_DECLINED != UNAVAILABLE_REPLY_UNUSABLE

    # A name that merely contains the word is still a name. The decline word is
    # an ordinary word, and a passage about it must survive.
    kept, kept_code = validate_label(f"{DECLINE_REPLY} of the above", source)
    assert kept_code is None
    assert kept is not None


def test_the_instruction_names_no_subject_and_gives_no_example() -> None:
    """You cannot enumerate example subjects without saying you are about to.

    A prompt carrying "for example" and a noun has taught the model what kind of
    answer this system expects, which is a taxonomy delivered by suggestion. The
    instruction must describe the shape of the answer and nothing about its
    content.
    """

    tree = _tree()
    prompts = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id.endswith("_PROMPT")
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert prompts, "the module must state its instruction as a literal to be checkable"

    for prompt in prompts:
        lowered = prompt.lower()
        for opener in ("for example", "e.g", "such as", "for instance", "like this"):
            assert opener not in lowered, f"the instruction must not enumerate: {opener}"
        # A quotation mark in an instruction is nearly always wrapping a sample
        # answer, and a sample answer is one entry of a taxonomy.
        for quote in ('"', "'", "\u201c", "\u2018"):
            assert quote not in prompt, "the instruction must carry no sample answer"


def test_the_label_lives_where_the_document_s_words_do_not() -> None:
    """Distinguishable in the database from anything the document said.

    `document_provisions` is a copy of the source's headings. A generated string
    in that row would be indistinguishable from a copied one by every later
    reader and every later query. Separation by table is the only form of that
    guarantee which cannot be lost by someone selecting the wrong column.
    """

    provision_columns = {column.name for column in DocumentProvision.__table__.columns}
    label_columns = {column.name for column in ProvisionTopicLabel.__table__.columns}

    assert provision_columns.isdisjoint(label_columns - {"id", "created_at", "updated_at"})
    assert ProvisionTopicLabel.__tablename__ != DocumentProvision.__tablename__


def test_a_stored_label_carries_what_produced_it() -> None:
    """A generated string with no history is a claim nobody can check.

    Which model, under which instruction, from which words, and when. Without
    all four, a label found in the database a year from now cannot be told from
    one generated under a rule that no longer holds.
    """

    columns = {column.name for column in ProvisionTopicLabel.__table__.columns}
    for required in (
        "model_deployment",
        "prompt_version",
        "source_digest",
        "source_rule_count",
        "generated_at",
    ):
        assert required in columns


def test_exactly_one_outcome_is_recorded_per_attempt() -> None:
    """A row holding neither a label nor a reason is a card rendering a blank.

    Enforced in the schema rather than in the writer, because the writer is one
    caller and the table outlives it.
    """

    checks = {
        constraint.name
        for constraint in ProvisionTopicLabel.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert any("one_outcome" in (name or "") for name in checks)
