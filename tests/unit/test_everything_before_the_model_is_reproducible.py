"""Everything before the model call must give the same answer every time.

The pipeline asks a language model to read a document, and a language model is
allowed to be inconsistent. Nothing else here is. Ingest, canonical rebuild,
structural graph, provision grouping, the clause→provision index, batching and
the rendered prompt are ordinary functions of the stored clauses: run them twice
on the same input and any difference is a defect, not model variance.

That distinction is the whole reason this file exists. When re-extraction
produced different rule counts from an unchanged document, the first question
was which stage moved — and without this guard the honest answer was "we assume
the deterministic ones are deterministic". Assumption is cheap to replace here:
these stages need no database, no network and no model, so they can be re-run in
milliseconds and compared to themselves.

Two properties are asserted, and neither is a number:

    single-valuedness — repeated computation over one input yields one result
    hash-seed independence — that result does not depend on PYTHONHASHSEED

The second is not paranoia. Iterating a `set` is the classic way a pipeline
acquires run-to-run variance that looks exactly like a model being unstable, and
Python randomises string hashing per process by default, so a set that leaked
into an ordered output would produce a different order in each *run* while
looking perfectly stable within one. Every artefact is therefore recomputed
under several explicit seed values in-process, and the ordered structures are
additionally checked directly.

Deliberately no expected counts. What this corpus grouped into some number of
provisions is a fact about these fixtures on this day; asserting it would make a
test that fails when the fixture improves and passes when determinism breaks.
Invariance is the property; the values are the fixture's business.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from policy_platform.contracts.provision_grouping import group_into_provisions
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.domain.models import Clause
from policy_platform.infrastructure.extraction.ai_extraction import (
    _batch_clauses,
    _render_batch,
)
from policy_platform.infrastructure.ingestion.canonical_rebuild import canonical_from_clauses

_DOCUMENT_VERSION_ID = "00000000-0000-4000-8000-00000000d0c5"
_SOURCE_RELEASE = "fixed-release"

#: Enough repeats that an intermittent ordering difference has to be unlucky
#: several times over to escape, and few enough that the file stays instant.
_REPEATS = 8

#: Explicit hash-seed values rather than whatever the runner happened to start
#: with. A test that only ever sees one seed cannot see seed dependence at all.
_HASH_SEEDS = (0, 1, 42, 12345)


def _clause(seq: int, text: str, element_type: str = "paragraph", section: str | None = None) -> Clause:
    return Clause(
        clause_ref=f"c{seq:03d}",
        section=section,
        page=1 + seq // 6,
        text=text,
        sequence=seq,
        element_id=f"E{seq:06d}",
        element_type=element_type,
        source_fragments=[{"page": 1, "start_offset": 0, "end_offset": len(text), "text": text}],
    )


@pytest.fixture
def clauses() -> list[Clause]:
    """A document with the shapes that have historically moved between runs.

    Repeated headings, a heading whose body is long enough to be split across
    batches, sibling provisions with near-identical text, and a table. Each is a
    case where an implementation might reach for a set or a dict of unordered
    keys and get away with it on simpler input.
    """

    out: list[Clause] = []
    seq = 0

    def add(text: str, element_type: str = "paragraph", section: str | None = None) -> None:
        nonlocal seq
        seq += 1
        out.append(_clause(seq, text, element_type, section))

    for heading, bodies in (
        ("Leave", ["Staff may take leave.", "Leave must be approved.", "Unused leave lapses."]),
        ("Conduct", ["Staff shall behave.", "Breaches are escalated."]),
        # Same heading text again: a grouping keyed on the heading alone rather
        # than on position would collapse these two and do it unpredictably.
        ("Leave", ["Leave may be carried over once.", "Carry-over expires in March."]),
        # Long enough to force several batch boundaries, and one provision long
        # enough that it cannot fit in a batch alone and must be divided —
        # division is where an ordering bug would do the most damage, so the
        # fixture has to reach it.
        ("Pay", ["a" * 1800, "b" * 1800, "c" * 1800, "d" * 1800]),
        ("Allowances", ["e" * 1500, "f" * 1500]),
        ("Conduct", ["Staff shall behave."]),
        ("Travel", ["g" * 1200, "h" * 1200, "Receipts are required."]),
    ):
        add(heading, "heading")
        for body in bodies:
            add(body, "paragraph", section=heading)

    add("Schedule", "heading")
    add("Grade | Allowance", "table", section="Schedule")
    add("A | 100", "table", section="Schedule")
    add("B | 200", "table", section="Schedule")
    return out


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _artefacts(clauses: list[Clause]) -> dict[str, str]:
    """Every pre-model derivation, as a digest per stage.

    Computed together rather than one test per stage so that a stage added to
    the pipeline and to this function is covered by every property below at
    once, instead of by whichever tests its author remembered.
    """

    document = canonical_from_clauses(_DOCUMENT_VERSION_ID, clauses)
    graph = build_structural_graph(document)
    provisions = group_into_provisions(document, graph, source_release=_SOURCE_RELEASE)
    batches, divided = _batch_clauses(clauses, _DOCUMENT_VERSION_ID)

    return {
        "canonical rebuild": _digest([element.model_dump() for element in document.elements]),
        "structural graph": _digest(
            graph.model_dump() if hasattr(graph, "model_dump") else repr(graph)
        ),
        "provision keys": _digest([p.provision_key for p in provisions]),
        "provision shape": _digest(
            [
                [
                    p.provision_key,
                    list(p.heading_path),
                    list(p.element_ids),
                    p.first_page,
                    p.last_page,
                    p.first_logical_order,
                ]
                for p in provisions
            ]
        ),
        "batch boundaries": _digest([[c.clause_ref for c in batch] for batch in batches]),
        "divided provisions": _digest([repr(d) for d in divided]),
        # The bytes actually sent. Every stage above could agree and this still
        # differ, which would mean the model is being asked a different question
        # from the same document.
        "rendered model input": _digest([_render_batch(batch) for batch in batches]),
    }


def test_every_pre_model_stage_is_single_valued(clauses: list[Clause]) -> None:
    """Recomputing from one input must not produce a second answer."""

    runs = [_artefacts(clauses) for _ in range(_REPEATS)]

    for stage in runs[0]:
        distinct = {run[stage] for run in runs}
        assert len(distinct) == 1, (
            f"{stage} produced {len(distinct)} different results from identical input over "
            f"{_REPEATS} repeats. This is upstream of the model, so it is a defect and not "
            "extraction variance: something here depends on iteration order, wall-clock "
            "time or a random value."
        )


@pytest.mark.parametrize("hash_seed", _HASH_SEEDS)
def test_pre_model_stages_do_not_depend_on_hash_seed(
    clauses: list[Clause], hash_seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same answer whatever PYTHONHASHSEED the process started with.

    A set or a dict keyed on strings, iterated into an ordered result, gives a
    stable order within one process and a different one in the next. That is
    indistinguishable from model drift when looking at two runs, and it is the
    single most likely way for this pipeline to acquire non-determinism it would
    then blame on the model.
    """

    monkeypatch.setenv("PYTHONHASHSEED", str(hash_seed))
    seeded = _artefacts(clauses)
    baseline = _artefacts(clauses)

    for stage, digest in baseline.items():
        assert seeded[stage] == digest, (
            f"{stage} changed under PYTHONHASHSEED={hash_seed}. An unordered collection is "
            "reaching an ordered output, so this stage produces different results in "
            "different processes while looking stable inside one."
        )


def test_the_provision_set_is_identical_run_to_run(clauses: list[Clause]) -> None:
    """The unit a reviewer thinks of as "a policy" must not move underneath them.

    This is the property that answers the question the whole stability
    investigation was opened to settle. Rules are produced by a model and will
    differ between runs; provisions are computed from the document's structure
    and must not. If provisions hold while rules move, then what a reviewer
    organises their work around is stable and the churn is confined to the layer
    below it — which is a far better position than the rule counts alone suggest.

    Asserted as a set *and* as a sequence. The set catches a provision appearing
    or vanishing; the sequence catches two provisions swapping places, which
    leaves the set identical while changing which batch each one is read in.
    """

    runs = []
    for _ in range(_REPEATS):
        document = canonical_from_clauses(_DOCUMENT_VERSION_ID, clauses)
        graph = build_structural_graph(document)
        runs.append(
            [
                p.provision_key
                for p in group_into_provisions(document, graph, source_release=_SOURCE_RELEASE)
            ]
        )

    first = runs[0]
    assert first, (
        "the fixture produced no provisions, so every assertion below holds vacuously."
    )
    for other in runs[1:]:
        assert set(other) == set(first), (
            "the set of provisions changed between two computations over the same clauses. "
            f"Only in one: {sorted(set(other) ^ set(first))}. A provision that appears or "
            "vanishes moves rules between policies, so a reviewer's queue is reorganised by "
            "a re-run that read nothing new."
        )
        assert other == first, (
            "the provisions are the same but their order changed, which changes how they "
            "are batched and therefore what the model reads together."
        )


def test_provision_keys_are_derived_from_content_not_from_identity(
    clauses: list[Clause],
) -> None:
    """Rebuilding from equal-but-distinct clause objects must give equal keys.

    The positive control for the test above. Recomputing from the *same* list
    twice would also pass if a key were derived from object identity or from a
    counter — and such a key would be stable within a process and different in
    the next one, which is exactly the failure being excluded.
    """

    def keys(source: list[Clause]) -> list[str]:
        document = canonical_from_clauses(_DOCUMENT_VERSION_ID, source)
        graph = build_structural_graph(document)
        return [
            p.provision_key
            for p in group_into_provisions(document, graph, source_release=_SOURCE_RELEASE)
        ]

    rebuilt = [
        _clause(c.sequence, c.text, c.element_type, c.section) for c in clauses
    ]

    assert keys(rebuilt) == keys(clauses), (
        "an equal document rebuilt as fresh objects produced different provision keys, so "
        "a key depends on something other than the content it is supposed to identify."
    )
