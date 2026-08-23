"""A passage is the document's words, not the application's labels.

WHAT WAS WRONG

Sixteen records in one extraction of the AIS staff handbook had a
`source_text` beginning:

    (section: Table of Violations and Penalties) 7. | | Late for work more
    than 60 minutes without permission...

That handbook does not say "(section: Table of Violations and Penalties)"
anywhere. `ai_extraction._render_batch` writes it, along with
`[clause_ref=...]` and a table's column names, so Stage 1 can tell one clause
from the next and read a row in context. `_render_passages` strips them before
Stage 2 already, in its own words because they are "non-policy strings to
misread as content" — but Stage 1 sees them first, and sometimes copies one.

Measured: 0 of 362 parsed clauses contain "(section:". The string exists only
in what this application renders.

WHY verify_verbatim DID NOT CATCH IT

It is passed the rendered batch as its `source_text`. The batch is the document
*plus* the labels, so a passage that copied a label was checked for containment
against the very label it had copied, and passed. The guarantee the module
docstring calls "the one property of the pipeline that can be proven cheaply"
had a hole exactly the shape of the application's own scaffolding.

WHY THIS IS ALSO THE STAGE 1 VARIANCE

The handover held a re-segmentation proposal for a user decision, on the
grounds that Stage 1 picks *which* sentences are normative consistently but
*where a rule ends* inconsistently. Nobody could check it, because the database
had only ever held one extraction.

Two runs of the same document, same code, same prompt:

    run A  263 rules, 223 distinct spans
    run B  280 rules, 229 distinct spans
    181 spans identical -- 81.2% reproduction

    of the 42 spans A produced and B did not:
      38 are the same material cut differently
       4 share no text with any B span

So the diagnosis was right — the variance is boundaries, not selection. But 38
of those 38 boundary differences are this leak: the model copying the label on
one run and not the other. The fix the proposal called for is a behaviour change
to segmentation with real risk to lists, tables and published deltas. This is a
strip of known application output, and measurement says it is most of what that
change was meant to remove.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.extraction.passage_extractor import (
    strip_application_scaffolding,
    verify_verbatim,
)

#: Verbatim from the corpus. The document's text begins at "7. |".
LEAKED = (
    "(section: Table of Violations and Penalties) 7. | | Late for work more than "
    "60 minutes without permission or a valid reason."
)
CLEAN = (
    "7. | | Late for work more than 60 minutes without permission or a valid reason."
)


def test_the_live_leak_is_removed() -> None:
    assert strip_application_scaffolding(LEAKED) == CLEAN


@pytest.mark.parametrize(
    "prefix",
    [
        "[clause_ref=p23-c4] ",
        "(section: Table of Violations and Penalties) ",
        "(columns: Violation | 1 Time | 2 Time) ",
    ],
)
def test_each_label_the_renderer_writes_is_removed(prefix: str) -> None:
    """One case per shape `_render_batch` emits. If it adds a fourth, add a case."""

    assert strip_application_scaffolding(prefix + CLEAN) == CLEAN


def test_several_labels_stacked_are_all_removed() -> None:
    """A table row gets all three at once, which is how the batch renders it."""

    stacked = (
        "[clause_ref=p23-t1-r7]\n(section: Table of Violations and Penalties)\n"
        "(columns: Violation | 1 Time | 2 Time)\n" + CLEAN
    )
    assert strip_application_scaffolding(stacked) == CLEAN


# --------------------------------------------------------------------------
# What must survive untouched
# --------------------------------------------------------------------------


def test_a_parenthesis_the_document_wrote_is_kept() -> None:
    """The document uses brackets constantly. Only the app's labels go.

    "An employee can ask for exam leave (compensated for the first set of
    exams)" is a real sentence from this corpus, and its parenthesis is policy.
    """

    sentence = (
        "An employee can ask for exam leave (compensated for the first set of exams)."
    )
    assert strip_application_scaffolding(sentence) == sentence


def test_a_label_shaped_string_mid_sentence_is_kept() -> None:
    """Only leading labels are removed, because a passage is contiguous.

    A copied label can only be at the front of a span. Something later in the
    sentence is the document's own, whatever it looks like.
    """

    sentence = "Refer to the schedule (section: 8) before submitting the claim."
    assert strip_application_scaffolding(sentence) == sentence


def test_an_ordinary_passage_is_returned_unchanged() -> None:
    plain = "Alcohol and drugs are strictly forbidden."
    assert strip_application_scaffolding(plain) == plain


def test_empty_input_is_handled() -> None:
    assert strip_application_scaffolding("") == ""
    assert strip_application_scaffolding("   ") == ""


# --------------------------------------------------------------------------
# The interaction with the verbatim guarantee
# --------------------------------------------------------------------------


def test_stripping_first_is_what_makes_verification_meaningful() -> None:
    """The reason this runs before `verify_verbatim` rather than inside it.

    `source_text` at the call site is the rendered batch — the document plus
    the labels. A leaked passage is contained in it, so verification passes on
    a passage that is part document and part application. The label has to be
    gone before the question is asked.
    """

    rendered_batch = (
        "[clause_ref=p23-t1-r7]\n(section: Table of Violations and Penalties)\n" + CLEAN
    )

    # The hole: the leaked text verifies against the batch that contains it.
    assert verify_verbatim(LEAKED.replace(") 7.", ")\n7."), rendered_batch) is True

    # Stripped first, the passage verifies as what it actually is.
    assert verify_verbatim(strip_application_scaffolding(LEAKED), rendered_batch) is True


def test_a_fabrication_is_still_rejected() -> None:
    """Stripping must not become a way to pass verification.

    It removes known application output. It cannot make a sentence the document
    never contained verifiable.
    """

    rendered_batch = "[clause_ref=p1-c1]\n(section: Leave)\nEmployees may take leave."
    assert verify_verbatim("Employees may take a bonus.", rendered_batch) is False
    assert (
        verify_verbatim(
            strip_application_scaffolding("(section: Leave) Employees may take a bonus."),
            rendered_batch,
        )
        is False
    )


# --------------------------------------------------------------------------
# The strip has to be REACHED, not merely present
# --------------------------------------------------------------------------


class _StubClient:
    """Returns one leaked passage, as the live model did.

    The extractor's only dependency is its client, so a stub is enough to drive
    the real acceptance loop — which is the thing under test here. The first
    version of this file tested `strip_application_scaffolding` directly and
    every case passed with the call site deleted: proof the function works is
    not proof anything calls it, and that gap is this codebase's most-logged
    failure.
    """

    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.calls = 0

    async def chat(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN401
        self.calls += 1
        return self._payload


@pytest.mark.asyncio
async def test_the_extractor_strips_before_it_keeps() -> None:
    """Drive the real acceptance path and read what it kept."""

    import json

    from policy_platform.infrastructure.extraction.passage_extractor import (
        PassageExtractorAgent,
    )
    from policy_platform.infrastructure.settings import Settings

    rendered_batch = (
        "[clause_ref=p23-t1-r7]\n(section: Table of Violations and Penalties)\n" + CLEAN
    )
    payload = json.dumps(
        {
            "policy_passages": [
                {
                    "text": "(section: Table of Violations and Penalties)\n" + CLEAN,
                    "source": {"clause_ref": "p23-t1-r7"},
                }
            ]
        }
    )

    agent = PassageExtractorAgent(_StubClient(payload), Settings())
    kept, rejected = await agent.extract(rendered_batch, document_id="d", document_name="n")

    assert not rejected
    assert len(kept) == 1
    assert "(section:" not in kept[0].text, (
        "the application's label reached a stored passage — the strip is not "
        "wired into the acceptance path"
    )
    assert kept[0].text == CLEAN
