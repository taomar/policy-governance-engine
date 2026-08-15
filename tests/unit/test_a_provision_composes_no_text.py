"""A provision holds no words of its own.

THE CONSTRAINT

    Reducing records must not produce a sentence the document did not write.

A policy is a *container*. It groups rules that a section of a document states.
It does not describe them, summarise them, or introduce them. Everything a
reviewer reads on a policy card is either one of the document's own headings,
quoted whole, or something a rule carries.

WHY THE ASSERTION IS OVER THE TABLE AND NOT OVER BEHAVIOUR

A test that checked "no summary is generated today" would pass right up until
the afternoon somebody adds a `summary` column and fills it, which is exactly
how this happens: not as a decision to compose text, but as a helpful field on
a model. So the assertion is structural. `DocumentProvision` is allowed a fixed
set of columns and no others, and adding a prose column fails the build with a
message saying why rather than passing silently.

The heading columns are the deliberate exception, and they are exceptions in
form as well as intent: `heading_path_json` is a *list* of headings, never a
joined path, so no separator character this system chose can end up between two
of the document's words.

WHAT THIS DOES NOT CLAIM

It does not claim the rest of the system composes nothing. It claims the new
entity introduces no new place for composition to happen. The rule-level and
UI-level guards are elsewhere and stay there.
"""
from __future__ import annotations

import pytest

from policy_platform.domain.models import DocumentProvision

#: Every column `document_provisions` is allowed to have.
#:
#: Deliberately exhaustive rather than a deny-list of suspicious names: a
#: deny-list has to predict what a future field will be called, and the field
#: that breaks this will be called something reasonable.
_ALLOWED = {
    "id",
    "policy_set_id",
    "document_version_id",
    "provision_key",
    # The document's own headings, outermost first, each verbatim, as a list.
    "heading_path_json",
    # The same chain as element ids, so a grouping can be audited against the
    # document after the fact rather than only reproduced.
    "heading_element_ids_json",
    "first_page",
    "last_page",
    "first_sequence",
    "merged_run_count",
    "created_at",
    # From `TimestampMixin`, like every sibling table. Not written after
    # insert: `provision_row` is get-or-create and never issues an UPDATE, so
    # a second run leaves this untouched and the whole-table digest that
    # proves idempotence includes it rather than excusing it.
    "updated_at",
}

#: Column-name fragments that would mean the table had started holding prose.
_PROSE = (
    "summary",
    "description",
    "statement",
    "text",
    "body",
    "abstract",
    "overview",
    "narrative",
    "label",
    "caption",
    "note",
)


def _columns() -> set[str]:
    return {column.key for column in DocumentProvision.__table__.columns}


def test_a_provision_has_only_the_columns_it_is_allowed() -> None:
    unexpected = _columns() - _ALLOWED
    assert not unexpected, (
        "document_provisions gained column(s) "
        f"{sorted(unexpected)}. A policy is a container: it groups rules a "
        "section states and says nothing of its own. If the new column holds "
        "the document's own words verbatim, add it to _ALLOWED with a comment "
        "saying which words and why they cannot be read from the rules."
    )


def test_every_allowed_column_still_exists() -> None:
    # CONTROL. The test above passes perfectly on a table that lost half its
    # columns, which would break grouping while looking like tightening.
    missing = _ALLOWED - _columns()
    assert not missing, f"document_provisions lost column(s) {sorted(missing)}"


@pytest.mark.parametrize("fragment", _PROSE)
def test_no_column_name_suggests_prose(fragment: str) -> None:
    # Belt and braces with the allow-list: this one names the failure in the
    # language of the constraint, so a reader of the failure understands the
    # rule rather than only that a list needs editing.
    offending = sorted(
        name for name in _columns() if fragment in name and name not in _ALLOWED
    )
    assert not offending, (
        f"document_provisions column(s) {offending} look like prose. A policy "
        "never composes a sentence the document did not write."
    )


def test_the_heading_chain_is_a_list_and_not_a_joined_path() -> None:
    """The one place composition could hide inside an allowed column.

    A `heading_path` stored as `"1. Employment > 1.1 Probation"` puts a
    separator this system chose between two of the document's headings, and
    every consumer downstream then has to guess how to take it apart. Stored as
    a list, no character is added at all and rendering picks its own separator
    in markup where it is visibly not part of the text.
    """

    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    for name in ("heading_path_json", "heading_element_ids_json"):
        column = DocumentProvision.__table__.columns[name]
        assert isinstance(column.type, (JSON, JSONB)), (
            f"{name} must stay a JSON array. A string would mean the headings "
            "had been joined by a character the document did not write."
        )


def test_a_provision_carries_no_route() -> None:
    """Route is a property of a rule, and mixed is normal.

    A policy holding one would immediately raise "what is *the* policy's
    route" for a policy whose rules take both, and there is no answer to that
    question which does not present one route as the deficient one. The
    condition tree already refuses to store its own evaluation mode for the
    same reason: a second copy can disagree with the thing it describes.
    """

    route_ish = sorted(
        name
        for name in _columns()
        if "route" in name or "evaluation_mode" in name or "readiness" in name
    )
    assert not route_ish, (
        f"document_provisions gained {route_ish}. Route belongs to each rule; "
        "a policy holding both kinds is the ordinary case, not a degraded one."
    )
