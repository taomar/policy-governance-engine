"""Run the Docling shadow comparison over the sample corpus.

Migration QA only: this compares the legacy parsers against Docling so the
cutover decision rests on measured fidelity rather than expectation. It is not
part of the ingestion path.

    python scripts/docling_shadow_report.py [--pdf] [--out PATH]
    python scripts/docling_shadow_report.py --path FILE [--path FILE] --decision

PDF is opt-in because layout inference costs roughly 195 seconds per document
against 0.3 seconds for DOCX, and because it needs TORCHDYNAMO_DISABLE=1 on
Windows without a Visual C++ toolchain (see
docs/specs/docling-integration-operating-notes.md).

`--path` measures documents outside the sample corpus, so a regression witness
can be run without being added to a fixture list.

`--decision` widens the report from "did Docling lose anything the legacy parser
found" to the evidence the `document_converter` setting actually needs. The
shadow comparison is a comparison between two outputs, so it cannot see text
that *neither* converter recovered, and it says nothing about whether the
structure Docling preserves survives as far as the thing that reads it. The
decision report adds, per converter:

* recall measured against the *source file* rather than against the other
  converter, so a loss common to both is visible instead of cancelling out;
* table cells and header identity actually emitted;
* structural edges actually built, by building the real graph;
* whether `reading_plan._add_table_context` can frame a bare cell, by building
  the real reading plan and reading back the context it produced;
* script fidelity, determinism across repeated runs, and wall-clock cost.

BOTH SIDES GO THROUGH THE SEAM
------------------------------
Each converter is selected by setting `DOCUMENT_CONVERTER` and calling
`document_extraction.extract_document`, because the question being answered is
what production would do if that setting changed. Calling `ingest_document` and
`convert_document` directly would compare two parsers and prove nothing about
the switch — and it is also how the legacy side of this script used to be wrong:
it relied on the *default* being legacy, so running it in an environment that
had already selected Docling would have compared Docling against itself and
reported perfect fidelity.

NOTHING HERE ASSERTS A NUMBER
-----------------------------
This script measures and prints. It carries no thresholds and no expected
values: a count observed on one corpus is a fact about that corpus, not a
property of the platform, and encoding one would turn a witness into a target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import unicodedata
import warnings
import zipfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Must be set before torch is imported by the Docling pipeline.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
warnings.filterwarnings("ignore")

from policy_platform.contracts.canonical_document import CanonicalDocument  # noqa: E402
from policy_platform.contracts.reading_plan import build_reading_plan  # noqa: E402
from policy_platform.contracts.structural_graph import build_structural_graph  # noqa: E402
from policy_platform.infrastructure.docling.converter import convert_document  # noqa: E402
from policy_platform.infrastructure.docling.shadow_comparison import (  # noqa: E402
    _TRIVIAL,
    _content_tokens,
    _tokens,
    compare,
    format_report,
)
from policy_platform.infrastructure.settings import get_settings  # noqa: E402

SAMPLES = REPO_ROOT / "samples" / "source-documents"

DOCX_CORPUS = [
    "HR-Special-Leave-Policy-v1.0.docx",
    "IT-Security-Incident-Emergency-Access-Policy-v1.0.docx",
    "Workplace-Hardware-Provisioning-Policy-v3.2.docx",
    "Workplace-Hardware-Provisioning-Policy-v3.3.docx",
]
PDF_CORPUS = ["HR-Guide-Policy-and-Procedure-Template.pdf"]

_MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}

#: The edge kinds that exist only because a converter kept cells apart. Named
#: here rather than counted inline so the report and the graph cannot drift.
_TABLE_EDGE_KINDS = ("table_cell_of", "header_for", "merged_with")


@contextmanager
def _converter_selected(name: str):
    """Select a converter for the duration of the block, then restore.

    The setting is read through `get_settings`, which is `lru_cache`d, so the
    cache is cleared on both entry and exit. Leaving it warm would make the
    second converter silently reuse the first one's choice.
    """

    previous = os.environ.get("DOCUMENT_CONVERTER")
    os.environ["DOCUMENT_CONVERTER"] = name
    get_settings.cache_clear()
    try:
        if get_settings().document_converter != name:
            raise RuntimeError(
                f"asked for DOCUMENT_CONVERTER={name} but the seam reads "
                f"{get_settings().document_converter!r}; the measurement would "
                "compare a converter against itself"
            )
        yield
    finally:
        if previous is None:
            os.environ.pop("DOCUMENT_CONVERTER", None)
        else:
            os.environ["DOCUMENT_CONVERTER"] = previous
        get_settings.cache_clear()


def _extract(path: Path, converter: str, docling_converter: Any | None) -> tuple[CanonicalDocument, float]:
    """Extract through the production seam with `converter` selected."""

    from policy_platform.infrastructure.ingestion import document_extraction

    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with _converter_selected(converter):
        started = time.perf_counter()
        document = document_extraction.extract_document(
            str(path),
            _MIME[path.suffix.lower()],
            document_id=path.stem,
            source_hash=source_hash,
            converter=docling_converter,
        )
        return document, time.perf_counter() - started


# ---------------------------------------------------------------------------
# The source-side reference
# ---------------------------------------------------------------------------
def source_tokens(path: Path) -> tuple[set[str], str]:
    """Distinct tokens present in the source file, read independently of both converters.

    Recall against the *source* is a different question from recall against the
    other converter, and it is the one the setting turns on: two parsers can
    agree perfectly about a page neither of them read.

    For DOCX the reference is the document part's own text runs, read straight
    out of the archive. That is the source rather than an interpretation of it.

    For PDF the reference is pdfminer's character stream, and it is **not
    neutral**: pdfplumber is built on pdfminer, so the reference shares a
    lineage with the legacy parser and will tend to flatter it. It is used
    anyway because the alternative is no source-side reference at all, and the
    bias has a known direction — measured this way, a Docling token deficit is
    an upper bound while a legacy token deficit is real.

    Tokens are NFKC-folded by `_tokens`, which maps a presentation form onto the
    character it renders. That is deliberate here and is the reason script
    fidelity is measured separately: without the folding, a converter that
    stored display glyphs would appear to have lost every word it actually kept,
    and the two defects would be impossible to tell apart.

    The same trivial-token filter the converter side uses is applied here.
    Comparing an unfiltered reference against a filtered extraction reports
    every "the" and "of" as lost content, which is not a fidelity measurement.
    """

    suffix = path.suffix.lower()
    if suffix in (".docx", ".doc"):
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", "replace")
        # `<w:t` alone also matches `<w:tbl`, `<w:tblGrid`, `<w:tcPr` and every
        # other table-property tag, which would pull WordprocessingML attribute
        # values such as "dxa" and "nohband" into the reference and report them
        # as text both converters lost.
        runs: list[str] = []
        cursor = 0
        while True:
            start = xml.find("<w:t", cursor)
            if start == -1:
                break
            after = xml[start + 4 : start + 5]
            if after not in (">", " ", "/"):
                cursor = start + 4
                continue
            open_end = xml.find(">", start)
            if open_end == -1:
                break
            if xml[open_end - 1] == "/":  # <w:t/>, an empty run
                cursor = open_end + 1
                continue
            close = xml.find("</w:t>", open_end)
            if close == -1:
                break
            runs.append(xml[open_end + 1 : close])
            cursor = close + 1
        return _reference_tokens(" ".join(runs)), "docx:word/document.xml"

    from pdfminer.high_level import extract_text

    return (
        _reference_tokens(extract_text(str(path))),
        "pdf:pdfminer.six (shares a lineage with pdfplumber)",
    )


def _reference_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _TRIVIAL}


# ---------------------------------------------------------------------------
# Per-converter measurement
# ---------------------------------------------------------------------------
def _script_profile(document: CanonicalDocument) -> dict[str, int]:
    """Presentation forms against the characters they stand for.

    Counted over element text, because element text is what downstream stages
    quote. Nothing is altered: this reports what is stored.
    """

    presentation = standard_rtl = letters = 0
    for element in document.elements:
        for char in element.text:
            if char.isalpha():
                letters += 1
            if unicodedata.decomposition(char).startswith(
                ("<isolated>", "<initial>", "<medial>", "<final>")
            ):
                presentation += 1
            elif unicodedata.bidirectional(char) in ("R", "AL"):
                standard_rtl += 1
    return {
        "presentation_forms": presentation,
        "standard_rtl_letters": standard_rtl,
        "letters": letters,
    }


def _direction_profile(document: CanonicalDocument) -> dict[str, Any]:
    """What the converter itself recorded about paint order versus reading order.

    This deliberately does not sniff the characters to guess whether they are in
    visual order. A guess presented as a measurement is worse than no
    measurement, and the platform's rule is that text is reported and never
    repaired. What is reported here is the converter's own claim: a page
    carrying `visual_order_raw_text` is a page where the parser said the two
    orders differed and kept both.
    """

    return {
        "pages": len(document.pages),
        "pages_retaining_visual_order": sum(
            1 for page in document.pages if page.visual_order_raw_text is not None
        ),
        "diagnostics": sorted({d.code for d in document.diagnostics}),
    }


def _table_framing(
    document: CanonicalDocument, graph: Any, plan: Any, samples: int = 4
) -> dict[str, Any]:
    """Whether the reading plan hands a model the header that frames each bare value.

    Resolved **per cell**, not per unit. A unit routinely carries several target
    cells, so reading `unit.context` as a whole and attributing all of it to each
    target reports one table's headers as framing another's — which looks like a
    spectacular result and is a measurement artefact.

    So the framing for a cell is taken from the same graph relations
    `_add_table_context` reads, and each one is then *confirmed present in the
    unit the cell was actually placed in* — as context or as a target, since
    `_build_unit` deliberately declines to add an element to context when it is
    already a target and the model sees it either way. Both halves matter: the
    first says the structure exists, the second says it survived as far as the
    thing that reads it. A converter can pass the first and fail the second, and
    that combination is precisely the failure this whole exercise is about.
    """

    by_id = {e.element_id: e for e in document.elements}
    body_cells = {
        e.element_id
        for e in document.elements
        if e.table_cell is not None and not e.table_cell.is_header
    }

    framed = unframed = delivered = 0
    examples: list[dict[str, Any]] = []
    for unit in plan.units:
        visible = {c.element_id for c in unit.context} | set(unit.target_element_ids)
        for target in unit.target_element_ids:
            if target not in body_cells:
                continue
            expected: list[tuple[str, str]] = []
            for header in graph.sources(target, "header_for"):
                expected.append(("table_header", header))
            for merged in graph.sources(target, "merged_with"):
                expected.append(("merged_header", merged))
            for table_id in graph.targets(target, "table_cell_of"):
                for sibling in graph.sources(table_id, "table_cell_of"):
                    cell = graph.table_cells.get(sibling)
                    own = graph.table_cells.get(target)
                    if not cell or not own or sibling == target:
                        continue
                    if cell.row_index == own.row_index and cell.column_index == 0:
                        expected.append(("table_row_label", sibling))

            if not expected:
                unframed += 1
                continue
            framed += 1
            present = [(r, e) for r, e in expected if e in visible]
            if len(present) == len(expected):
                delivered += 1

            cell = by_id[target]
            if len(examples) < samples and cell.text.strip():
                examples.append(
                    {
                        "unit_id": unit.unit_id,
                        "cell_text": cell.text,
                        "row": cell.table_cell.row_index,
                        "column": cell.table_cell.column_index,
                        "framing_in_graph": [
                            {"reason": r, "text": by_id[e].text}
                            for r, e in expected
                            if e in by_id
                        ],
                        "framing_delivered_to_unit": [
                            {"reason": r, "text": by_id[e].text}
                            for r, e in present
                            if e in by_id
                        ],
                    }
                )

    return {
        "body_cells": len(body_cells),
        "framed_by_graph": framed,
        "unframed": unframed,
        "framing_fully_delivered_to_reading_unit": delivered,
        "examples": examples,
    }


def _persistence_round_trip(document: CanonicalDocument) -> dict[str, Any]:
    """What survives the store-and-rebuild every downstream consumer goes through.

    A converter is measured twice on purpose. The first measurement reads the
    document the converter *returns*; this one reads the document the rest of
    the platform actually gets, because nothing downstream is handed that
    in-memory object. An upload is flattened to clauses, the clauses are stored,
    and every later stage rebuilds a canonical document from the stored rows --
    `ai_extraction`, `provision_linking` and the structure, reading-plan and
    coverage endpoints all do exactly this.

    So the honest question is not "what can this converter recover" but "what of
    it is still there when something reads it". Measuring only the first is how
    a capability gets built, tested against the converter's own output, and
    reaches nobody. This runs the real flatten (`clauses_from_document`) and the
    real rebuild (`canonical_from_clauses`), then rebuilds the graph and plan
    from the result, so the difference between the two is a property of the
    round trip and not of anything this script decided.

    The clause stand-in carries exactly the attributes the rebuild reads, which
    are exactly the columns the table has. Constructing ORM instances would need
    a session; a stand-in with the same fields makes the same measurement.
    """

    from policy_platform.infrastructure.ingestion.canonical_rebuild import (
        canonical_from_clauses,
    )
    from policy_platform.infrastructure.ingestion.document_extraction import (
        clauses_from_document,
    )

    class _StoredClause:
        __slots__ = (
            "element_id",
            "element_type",
            "sequence",
            "text",
            "section",
            "source_fragments",
            "table_id",
            "table_headers",
        )

        def __init__(self, data: Any, sequence: int) -> None:
            self.element_id = data.element_id
            self.element_type = data.element_type
            self.sequence = sequence
            self.text = data.text
            self.section = data.section
            self.source_fragments = data.source_fragments
            self.table_id = data.table_id
            self.table_headers = data.table_headers

    stored = [
        _StoredClause(data, index)
        for index, data in enumerate(clauses_from_document(document))
    ]
    rebuilt = canonical_from_clauses(document.document_id, stored)  # type: ignore[arg-type]
    graph = build_structural_graph(rebuilt)
    plan = build_reading_plan(rebuilt, graph)
    edge_kinds = Counter(e.kind for e in graph.edges)
    cells = [e for e in rebuilt.elements if e.table_cell is not None]

    return {
        "clauses_stored": len(stored),
        "elements_rebuilt": len(rebuilt.elements),
        "element_types": dict(sorted(Counter(e.element_type for e in rebuilt.elements).items())),
        "table_cells": len(cells),
        "header_cells": sum(1 for e in cells if e.table_cell.is_header),
        "tables": len({e.table_id for e in rebuilt.elements if e.table_id}),
        "edge_kinds": dict(sorted(edge_kinds.items())),
        "table_edges": {k: edge_kinds.get(k, 0) for k in _TABLE_EDGE_KINDS},
        "table_edge_total": sum(edge_kinds.get(k, 0) for k in _TABLE_EDGE_KINDS),
        "reading_plan_units": len(plan.units),
        "table_framing": _table_framing(rebuilt, graph, plan),
        # Row-level table identity, measured separately from cell structure
        # because the two are carried by different fields and only one of them
        # survives storage. `rows_with_headers` counts rows whose grid had a row
        # stating column labels; `rows_without_headers` counts rows of a grid
        # where none did. The second is a fact ingestion established, so it is
        # reported rather than folded into the first.
        "rows_with_table_id": sum(1 for e in rebuilt.elements if e.table_id),
        "rows_with_headers": sum(1 for e in rebuilt.elements if e.table_headers),
        "rows_without_headers": sum(
            1 for e in rebuilt.elements if e.table_id and e.table_headers is None
        ),
        "table_continuations": len(graph.table_continuations),
    }


def _text_samples(document: CanonicalDocument, samples: int = 3) -> list[dict[str, Any]]:
    """The first non-trivial element texts, verbatim, with a codepoint census.

    Recorded because a token-level recall number cannot distinguish "this text
    was dropped" from "this text was reordered": reversing a run of letters
    changes every token it touches, so the two look identical in a recall
    column. The stored string is the only thing that separates them, so the
    report carries it.

    Reported, never altered -- the census counts presentation forms and RTL
    letters and leaves the string exactly as the converter produced it.
    """

    out: list[dict[str, Any]] = []
    for element in document.elements:
        text = element.text.strip()
        if len(text) < 8:
            continue
        out.append(
            {
                "element_id": element.element_id,
                "element_type": element.element_type,
                "text": element.text,
                "presentation_forms": sum(
                    1
                    for c in element.text
                    if 0xFB50 <= ord(c) <= 0xFDFF or 0xFE70 <= ord(c) <= 0xFEFF
                ),
                "rtl_letters": sum(
                    1
                    for c in element.text
                    if unicodedata.bidirectional(c) in {"R", "AL"}
                ),
            }
        )
        if len(out) >= samples:
            break
    return out


def _row_samples(document: CanonicalDocument, samples: int = 3) -> list[dict[str, Any]]:
    """Whole table rows as an element, with whatever header the parser kept.

    Emitted for any converter that produces `table_row`, so the report shows the
    shape a downstream stage receives rather than asserting what it must be.
    """

    out: list[dict[str, Any]] = []
    for element in document.elements:
        if element.element_type != "table_row":
            continue
        out.append(
            {
                "element_id": element.element_id,
                "text": element.text,
                "table_headers": element.table_headers,
                "table_id": element.table_id,
                "has_cell_coordinates": element.table_cell is not None,
            }
        )
        if len(out) >= samples:
            break
    return out


def _determinism(documents: list[CanonicalDocument]) -> dict[str, Any]:
    """Whether repeated runs over identical bytes produced identical output.

    Identity and text are compared rather than a summary hash, so a failure says
    which of the two moved. Element identity drifting between runs is the more
    serious of the two: it breaks every reference already recorded against it.
    """

    if len(documents) < 2:
        return {"runs": len(documents), "stable": None, "detail": "single run"}

    base_ids = [e.element_id for e in documents[0].elements]
    base_text = [e.text for e in documents[0].elements]
    for index, document in enumerate(documents[1:], start=2):
        ids = [e.element_id for e in document.elements]
        text = [e.text for e in document.elements]
        if ids != base_ids:
            return {
                "runs": len(documents),
                "stable": False,
                "detail": f"run {index}: element ids differ from run 1",
            }
        if text != base_text:
            differing = sum(1 for a, b in zip(base_text, text) if a != b)
            return {
                "runs": len(documents),
                "stable": False,
                "detail": f"run {index}: {differing} element text(s) differ from run 1",
            }
    return {"runs": len(documents), "stable": True, "detail": "identical ids and text"}


def _measure_converter(
    path: Path,
    converter: str,
    docling_converter: Any | None,
    repeats: int,
    reference: set[str],
) -> tuple[CanonicalDocument, dict[str, Any]]:
    runs = [_extract(path, converter, docling_converter) for _ in range(max(repeats, 1))]
    documents = [d for d, _ in runs]
    document = documents[0]

    graph = build_structural_graph(document)
    plan = build_reading_plan(document, graph)

    recovered = set(_content_tokens(document))
    missing = reference - recovered
    reference_chars = sum(len(t) for t in reference)
    missing_chars = sum(len(t) for t in missing)

    edge_kinds = Counter(e.kind for e in graph.edges)
    cells = [e for e in document.elements if e.table_cell is not None]

    measurements = {
        "parser": document.parser,
        "seconds_per_run": [round(s, 3) for _, s in runs],
        "pages": document.page_count,
        "elements": len(document.elements),
        "element_types": dict(sorted(Counter(e.element_type for e in document.elements).items())),
        "fidelity": str(document.fidelity),
        "fragment_resolution_failures": len(document.verify_fragments()),
        "source_token_recall": (
            round((len(reference) - len(missing)) / len(reference), 4) if reference else None
        ),
        "source_char_recall": (
            round((reference_chars - missing_chars) / reference_chars, 4)
            if reference_chars
            else None
        ),
        "source_tokens_missing": len(missing),
        "source_tokens_missing_sample": sorted(missing)[:20],
        "tokens_absent_from_reference": len(recovered - reference),
        "tables": len({e.table_id for e in document.elements if e.table_id}),
        "table_cells": len(cells),
        "header_cells": sum(1 for e in cells if e.table_cell.is_header),
        "spanning_cells": sum(
            1 for e in cells if e.table_cell.column_span > 1 or e.table_cell.row_span > 1
        ),
        "table_rows": sum(1 for e in document.elements if e.element_type == "table_row"),
        "row_samples": _row_samples(document),
        "text_samples": _text_samples(document),
        "edge_kinds": dict(sorted(edge_kinds.items())),
        "table_edges": {k: edge_kinds.get(k, 0) for k in _TABLE_EDGE_KINDS},
        "table_edge_total": sum(edge_kinds.get(k, 0) for k in _TABLE_EDGE_KINDS),
        "elements_with_bbox": sum(
            1 for e in document.elements if any(f.bbox is not None for f in e.source_fragments)
        ),
        "reading_plan_units": len(plan.units),
        "reading_plan_exhaustive": plan.is_exhaustive,
        "reading_plan_uncovered_targets": len(plan.uncovered_target_ids),
        "reading_plan_divided_provisions": len(plan.divided_provisions),
        "table_framing": _table_framing(document, graph, plan),
        "after_persistence_round_trip": _persistence_round_trip(document),
        "script": _script_profile(document),
        "direction": _direction_profile(document),
        "determinism": _determinism(documents),
    }
    return document, measurements


@dataclass
class DocumentEvidence:
    name: str
    source_reference: str = ""
    source_distinct_tokens: int = 0
    converters: dict[str, Any] = field(default_factory=dict)
    legacy_vs_docling: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def measure_document(
    path: Path, docling_converter: Any | None, repeats: int
) -> DocumentEvidence:
    reference, reference_name = source_tokens(path)
    evidence = DocumentEvidence(
        name=path.name,
        source_reference=reference_name,
        source_distinct_tokens=len(reference),
    )

    produced: dict[str, CanonicalDocument] = {}
    for converter in ("legacy", "docling"):
        try:
            document, measurements = _measure_converter(
                path, converter, docling_converter, repeats, reference
            )
        except Exception as exc:  # a converter that cannot run is evidence too
            evidence.converters[converter] = {
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        produced[converter] = document
        evidence.converters[converter] = measurements

    if "legacy" in produced and "docling" in produced:
        shadow = compare(produced["legacy"], produced["docling"], document_name=path.name)
        evidence.legacy_vs_docling = {
            "legacy_token_recall_in_docling": round(shadow.recall, 4),
            "tokens_legacy_only": shadow.missing_token_count,
            "tokens_legacy_only_sample": shadow.missing_tokens,
            "tokens_docling_only": shadow.added_token_count,
            "tokens_docling_only_sample": shadow.added_tokens,
            "blocks_cutover": shadow.blocks_cutover,
        }
    return evidence


def _resolve_corpus(args: argparse.Namespace) -> list[Path]:
    if args.path:
        return list(args.path)
    names = DOCX_CORPUS + (PDF_CORPUS if args.pdf else [])
    if args.only:
        # An explicit --only implies the caller wants that fixture regardless of
        # format, so the PDF opt-in is not additionally required.
        names = [n for n in DOCX_CORPUS + PDF_CORPUS if args.only.lower() in n.lower()]
    return [SAMPLES / name for name in names]


def _run_decision(corpus: list[Path], repeats: int) -> tuple[str, int]:
    from docling.document_converter import DocumentConverter

    docling_converter = DocumentConverter()
    results: list[DocumentEvidence] = []
    for path in corpus:
        if not path.exists():
            print(f"skip {path}: not present", file=sys.stderr)
            continue
        print(f"measuring {path.name} ...", file=sys.stderr, flush=True)
        results.append(measure_document(path, docling_converter, repeats))
        print(f"  done {path.name}", file=sys.stderr, flush=True)

    payload = [
        {
            "document": r.name,
            "source_reference": r.source_reference,
            "source_distinct_tokens": r.source_distinct_tokens,
            "converters": r.converters,
            "legacy_vs_docling": r.legacy_vs_docling,
        }
        for r in results
    ]
    failures = sum(
        1
        for r in results
        for measurements in r.converters.values()
        if isinstance(measurements, dict) and "error" in measurements
    )
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str), failures


def _run_shadow(corpus: list[Path], docling_converter: Any) -> tuple[str, int]:
    from policy_platform.infrastructure.ingestion import document_extraction

    comparisons = []
    for path in corpus:
        if not path.exists():
            print(f"skip {path}: not present", file=sys.stderr)
            continue

        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        # Explicitly selected rather than assumed: this comparison used to take
        # the legacy side from whatever the environment's default happened to
        # be, which in a Docling-selected environment compared Docling with
        # itself and reported perfect fidelity.
        with _converter_selected("legacy"):
            legacy = document_extraction.extract_document(
                str(path), _MIME[path.suffix.lower()]
            )
        docling = convert_document(path, source_hash=source_hash, converter=docling_converter)

        comparisons.append(compare(legacy, docling, document_name=path.name))
        print(f"compared {path.name}", file=sys.stderr)

    return format_report(comparisons), sum(1 for c in comparisons if c.blocks_cutover)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="include PDF fixtures (slow)")
    parser.add_argument(
        "--only",
        default=None,
        help="restrict the run to fixtures whose filename contains this substring",
    )
    parser.add_argument(
        "--path",
        action="append",
        type=Path,
        default=[],
        help="measure this document instead of the sample corpus; repeatable",
    )
    parser.add_argument(
        "--decision",
        action="store_true",
        help="emit the full converter-decision evidence as JSON rather than the token report",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=2,
        help="runs per converter, for the determinism measurement (--decision only)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the report to a file")
    args = parser.parse_args()

    corpus = _resolve_corpus(args)
    if not corpus:
        print("no document selected", file=sys.stderr)
        return 2

    if args.decision:
        report, failures = _run_decision(corpus, args.repeats)
    else:
        from docling.document_converter import DocumentConverter

        report, failures = _run_shadow(corpus, DocumentConverter())

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"written to {args.out}", file=sys.stderr)
    else:
        print(report)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
