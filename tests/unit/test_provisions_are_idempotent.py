"""Running the grouping twice gives the same policies, byte for byte.

WHY A WHOLE-TABLE DIGEST AND NOT "NOTHING WAS ADDED"

A pass that deleted one provision and created another would add nothing, and
"nothing was added" would pass. So would a pass that rewrote every heading in
place. The assertion here is over the *entire* content of every provision --
key, headings, element ids, pages, order, merge count -- reduced to one digest,
compared before and against after.

The digest deliberately includes fields that are not part of identity. A change
to `first_page` cannot change which rules group together, but it can change
what a reviewer is shown, and a test that only pinned identity would let that
drift silently.

WHY THE SENSITIVITY CHECK IS NOT OPTIONAL

A digest computed over the wrong thing -- an empty list, a constant, a field
that is always None -- is stable for the worst possible reason, and a stability
test is exactly the kind of test that cannot tell the difference. So every
digest assertion here is paired with a case that changes the document and
proves the digest moves. A guard that cannot fail guards nothing.

THE COST THIS EXISTS AGAINST

This system has already produced the failure it is written to prevent: a
supersede fired on a run that then failed, and a reviewer was left holding
fewer records than they started with. `document_provisions` is therefore
append-only by construction -- nothing in the pipeline updates or deletes a
provision -- and these tests are how that construction is held.
"""
from __future__ import annotations

import hashlib
import json

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.provision_grouping import (
    group_into_provisions,
    provision_key_for,
)
from policy_platform.contracts.structural_graph import build_structural_graph

RELEASE = "release-under-test"


def _element(
    element_id: str,
    text: str,
    element_type: str = "paragraph",
    order: int = 0,
    page: int = 1,
) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type=element_type,  # type: ignore[arg-type]
        logical_order=order,
        text=text,
        source_fragments=[
            SourceFragment(page=page, start_offset=0, end_offset=len(text), text=text)
        ],
    )


def _document(elements: list[CanonicalElement]) -> CanonicalDocument:
    pages = sorted({fragment.page for e in elements for fragment in e.source_fragments})
    return CanonicalDocument(
        document_id="DOC",
        page_count=max(pages) if pages else 1,
        pages=[CanonicalPage(page=page, raw_text="") for page in pages],
        elements=elements,
        parser="docling",
    )


def _group(elements: list[CanonicalElement], release: str = RELEASE):
    document = _document(elements)
    return group_into_provisions(
        document, build_structural_graph(document), source_release=release
    )


def _digest(provisions) -> str:
    """One hash over the whole table, every column of every row.

    Sorted by key rather than by position, so a pass that produced the same
    provisions in a different order still matches -- order of insertion is not
    something the pipeline promises and pinning it would make this test fail
    for a reason that is not a defect.
    """

    rows = sorted(
        (
            {
                "provision_key": provision.provision_key,
                "heading_path": list(provision.heading_path),
                "heading_element_ids": list(provision.heading_element_ids),
                "element_ids": list(provision.element_ids),
                "first_logical_order": provision.first_logical_order,
                "first_page": provision.first_page,
                "last_page": provision.last_page,
                "merged_run_count": provision.merged_run_count,
            }
            for provision in provisions
        ),
        key=lambda row: row["provision_key"],
    )
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _handbook() -> list[CanonicalElement]:
    """A document with the shapes that have caused trouble, and no others.

    A numbered section of several paragraphs; a nested sub-heading; a heading
    immediately followed by another heading, which is what a bilingual document
    produces; and a heading repeated across pages with its own rows in between,
    which is what a table continuing over a page break produces.
    """

    return [
        _element("H1", "1. Employment", "heading", 0),
        _element("E2", "Contracts begin at the start of the academic year.", "paragraph", 1),
        _element("E3", "A temporary contract is issued otherwise.", "paragraph", 2),
        _element("H4", "1.1 Probation", "heading", 3),
        _element("E5", "Probation lasts ninety days.", "paragraph", 4),
        _element("H6", "\u062c\u062f\u0648\u0644 \u0627\u0644\u0645\u062e\u0627\u0644\u0641\u0627\u062a", "heading", 5),
        _element("H7", "Table of Violations", "heading", 6),
        _element("E8", "1. | Late by 15 minutes | Written warning", "paragraph", 7),
        _element("H9", "Table of Violations", "heading", 8, page=2),
        _element("E10", "2. | Late by 30 minutes | 5% deduction", "paragraph", 9, page=2),
    ]


class TestTheTableIsUnchangedBySecondRun:
    def test_the_whole_table_digest_is_identical(self) -> None:
        first = _group(_handbook())
        second = _group(_handbook())

        assert _digest(first) == _digest(second)

    def test_the_same_provisions_arrive_in_the_same_order(self) -> None:
        # The digest sorts, so it would pass on a reordering. Reading order is
        # what a reviewer sees, and is asserted separately rather than folded
        # in -- a policy queue that shuffles between runs is a defect even
        # though the set of policies is right.
        first = _group(_handbook())
        second = _group(_handbook())

        assert [p.provision_key for p in first] == [p.provision_key for p in second]
        assert [p.first_logical_order for p in first] == [
            p.first_logical_order for p in second
        ]

    def test_a_third_run_still_matches_the_first(self) -> None:
        # Two runs agreeing could be two runs sharing a first-call cache. A
        # third is cheap and rules out the shape where run one seeds something
        # that runs two and three then both read.
        digests = {_digest(_group(_handbook())) for _ in range(3)}

        assert len(digests) == 1


class TestTheDigestCanFail:
    """SENSITIVITY. Every stability assertion above is worthless if this fails.

    A digest over nothing is perfectly stable. These prove it is computed over
    something that moves when the document moves.
    """

    def test_changing_a_heading_changes_the_digest(self) -> None:
        changed = _handbook()
        changed[0] = _element("H1", "1. Engagement", "heading", 0)

        assert _digest(_group(_handbook())) != _digest(_group(changed))

    def test_adding_a_paragraph_changes_the_digest(self) -> None:
        changed = [*_handbook(), _element("E11", "Notice is in writing.", "paragraph", 10, page=2)]

        assert _digest(_group(_handbook())) != _digest(_group(changed))

    def test_a_different_release_changes_the_digest(self) -> None:
        # Element ids are not unique across documents -- both stored documents
        # start at E000001 -- so the release is part of the key. If it stopped
        # being, two documents would share provisions and this would not move.
        assert _digest(_group(_handbook())) != _digest(
            _group(_handbook(), release="a-different-release")
        )

    def test_moving_a_paragraph_to_another_section_changes_the_digest(self) -> None:
        # The strongest sensitivity case: same elements, same texts, same
        # count. Only membership differs. A digest that missed this would pass
        # every test above while grouping rules under the wrong policy.
        changed = _handbook()
        changed[2] = _element("E3", "A temporary contract is issued otherwise.", "paragraph", 4)
        changed[4] = _element("E5", "Probation lasts ninety days.", "paragraph", 2)

        assert _digest(_group(_handbook())) != _digest(_group(changed))


class TestNothingIsRemovedByRunningAgain:
    def test_the_second_run_holds_every_provision_the_first_did(self) -> None:
        # Stated as a subset check as well as a digest, because this is the
        # exact failure the supersede incident produced: a run that left a
        # reviewer with fewer records than they started with. A digest says
        # "different"; this says which direction.
        first = {p.provision_key for p in _group(_handbook())}
        second = {p.provision_key for p in _group(_handbook())}

        assert first <= second
        assert second <= first

    def test_a_document_that_grows_keeps_every_provision_it_had(self) -> None:
        # The realistic re-run: a corrected parse finds one more paragraph. The
        # sections that were already there must still be there, under the same
        # keys, or every approval recorded against them is orphaned.
        before = {p.provision_key for p in _group(_handbook())}
        after = {
            p.provision_key
            for p in _group([*_handbook(), _element("E11", "Notice is in writing.", "paragraph", 10, page=2)])
        }

        assert before <= after


class TestTheKeyIsStable:
    def test_the_same_headings_give_the_same_key(self) -> None:
        assert provision_key_for(RELEASE, ("1. Employment",), 0) == provision_key_for(
            RELEASE, ("1. Employment",), 0
        )

    def test_a_second_occurrence_gets_its_own_key(self) -> None:
        # Two genuinely distinct sections written under the same words are told
        # apart by position and nothing else. Merging them would be the false
        # merge the adjacency rule exists to refuse.
        assert provision_key_for(RELEASE, ("Purpose",), 0) != provision_key_for(
            RELEASE, ("Purpose",), 1
        )

    def test_a_deeper_chain_is_not_the_same_as_a_shallower_one(self) -> None:
        assert provision_key_for(RELEASE, ("1. Employment",), 0) != provision_key_for(
            RELEASE, ("1. Employment", "1.1 Probation"), 0
        )
