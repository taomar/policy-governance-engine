"""Contracts for Stage 1 of extraction: verbatim policy-passage identification.

Stage 1 answers a narrow question — *which spans of this document are
policy-bearing, and what do they say word-for-word?* — and nothing else. It
deliberately performs no interpretation: no atomization, no pronoun
resolution, no cross-reference expansion, no normalization. All of that is
Stage 2's job (`contracts/formulation.py`).

Splitting the two matters because they have different failure modes. A Stage 2
mistake produces a badly-structured rule, which a reviewer can see and correct
against the source. A Stage 1 mistake produces text that *was never in the
document*, which a reviewer cannot detect without re-reading the original — the
error is invisible precisely where it is most dangerous. Stage 1 is therefore
constrained to a pure SELECT-and-COPY operation whose output can be
mechanically verified against the source (see
`infrastructure/passage_extractor.verify_verbatim`).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Section 23 of the specification: the only two classifications Stage 1 may
#: assign. `POLICY_AMBIGUOUS` means "looks policy-bearing, but whether it
#: creates an operative rule is uncertain" — it is *not* a licence to reword.
PassageClassification = Literal["POLICY", "POLICY_AMBIGUOUS"]


class PassageSource(BaseModel):
    """Where in the document a passage was copied from.

    `clause_ref` is the platform's own identifier, echoed back by the agent so
    a returned passage can be tied to the exact `Clause` row it came from. That
    turns verbatim verification from a fuzzy search across the whole batch into
    an exact containment check against one known string.
    """

    model_config = ConfigDict(extra="ignore")

    clause_ref: str | None = None
    #: The LAST clause of the span, when a passage necessarily runs across more
    #: than one clause block. Together with `clause_ref` this forms the span
    #: reference the architecture specification calls for: the agent reports
    #: *where* the policy is, and the application copies the text out of its own
    #: canonical store. Optional — a single-clause passage leaves it unset.
    end_clause_ref: str | None = None
    page: int | None = None
    section: str | None = None
    article: str | None = None
    paragraph: str | None = None


class PolicyPassage(BaseModel):
    """One contiguous, verbatim, policy-bearing span of the source document."""

    model_config = ConfigDict(extra="ignore")

    passage_id: str = ""
    classification: PassageClassification = "POLICY"
    text: str = ""
    source: PassageSource = Field(default_factory=PassageSource)
    #: How this passage's `text` came to be. `model_copied` means the agent
    #: returned the characters and the application verified them against the
    #: source; `application_copied` means the application sliced the text out of
    #: its own canonical store using the agent's span reference and the agent's
    #: characters were never used. The second is strictly stronger and is the
    #: direction the architecture specification mandates, but both are recorded
    #: so a reviewer can tell which guarantee a given passage carries.
    text_origin: Literal["model_copied", "application_copied"] = "model_copied"
    #: Specification Section 16. Set to `suspected_ocr_issue` when the supplied
    #: source itself looks damaged. The agent must still copy the text as-is;
    #: this flag exists so it can report the problem *without* repairing it.
    source_quality: str | None = None


class PassageExtraction(BaseModel):
    """The agent's complete Stage 1 output for one block of source text."""

    model_config = ConfigDict(extra="ignore")

    document_id: str = ""
    document_name: str = ""
    policy_passages: list[PolicyPassage] = Field(default_factory=list)
