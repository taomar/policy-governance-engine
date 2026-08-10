"""Run the extraction pipeline over the corpus and report the acceptance gates.

Produces the evidence the directive asks for per document — coverage, exact-span
resolution, verification findings, and repeat-run stability — rather than a
single aggregate score. Aggregates hide the case that matters: one document at
100% and another at 40% averages to something that looks acceptable.

    python scripts/docling_corpus_report.py [--pdf] [--only NAME] [--repeats N]

PDF is opt-in: layout inference costs roughly 195 seconds per document against
0.3 for DOCX, and needs TORCHDYNAMO_DISABLE=1 on Windows without a Visual C++
toolchain (see docs/specs/docling-integration-operating-notes.md).
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Must be set before torch is imported by the Docling pipeline.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
warnings.filterwarnings("ignore")

from policy_platform.infrastructure.docling.pipeline import (  # noqa: E402
    ExtractionResult,
    run_extraction,
)

SAMPLES = REPO_ROOT / "samples" / "source-documents"

DOCX_CORPUS = [
    "HR-Special-Leave-Policy-v1.0.docx",
    "IT-Security-Incident-Emergency-Access-Policy-v1.0.docx",
    "Workplace-Hardware-Provisioning-Policy-v3.2.docx",
    "Workplace-Hardware-Provisioning-Policy-v3.3.docx",
]
PDF_CORPUS = ["HR-Guide-Policy-and-Procedure-Template.pdf"]


def _stability(runs: list[ExtractionResult]) -> tuple[bool, str]:
    """Compare repeated runs of the same document.

    Element identities and the canonical hash must be identical: they are
    derived from content and structure, so any variation means identity is
    picking up something it should not. Discovery may legitimately vary, but
    that variation must surface as a diff rather than silently replacing a
    prior extraction.
    """

    if len(runs) < 2:
        return True, "single run"

    baseline = runs[0]
    baseline_ids = [e.element_id for e in baseline.document.elements]
    baseline_key = baseline.package.application_handoff.idempotency_key

    for index, run in enumerate(runs[1:], start=2):
        if [e.element_id for e in run.document.elements] != baseline_ids:
            return False, f"run {index}: element identities differ from run 1"
        if run.package.application_handoff.idempotency_key != baseline_key:
            return False, f"run {index}: idempotency key differs from run 1"
        if (
            run.package.canonical_document.canonical_hash
            != baseline.package.canonical_document.canonical_hash
        ):
            return False, f"run {index}: canonical hash differs from run 1"

    return True, f"{len(runs)} runs identical"


def _report_document(name: str, runs: list[ExtractionResult]) -> tuple[list[str], bool]:
    result = runs[0]
    package = result.package
    coverage = package.coverage
    stable, stability_detail = _stability(runs)

    passed = (
        result.ok
        and package.is_handoff_ready
        and coverage.is_complete
        and not package.rejected_spans
        and stable
    )

    lines = [
        f"## {name}",
        "",
        f"- verdict: **{'PASS' if passed else 'FAIL'}**",
        f"- canonical elements: {package.canonical_document.element_count}"
        f" across {package.canonical_document.page_count} page(s)",
        f"- fidelity: {result.document.fidelity}",
        f"- reading plan: {len(result.plan.units)} unit(s), exhaustive={result.plan.is_exhaustive}",
        f"- coverage: {coverage.accounted}/{coverage.total_leaf_elements} accounted, "
        f"{len(coverage.unaccounted_element_ids)} unaccounted, {coverage.unresolved} unresolved",
        f"- exact spans: {len(package.evidence_spans)} resolved, "
        f"{len(package.rejected_spans)} rejected",
        f"- verification: {len(package.verification.blockers)} blocker(s), "
        f"{len(package.verification.warnings)} warning(s)",
        f"- repeat-run stability: {stability_detail}",
        "",
        "| stage | status | seconds | detail |",
        "|---|---|---|---|",
    ]
    for stage in result.stages:
        lines.append(
            f"| {stage.name} | {stage.status} | {stage.duration_seconds:.2f} | {stage.detail} |"
        )
    lines.append("")

    for blocker in package.verification.blockers:
        lines.append(f"- **blocker:** {blocker}")
    for warning in package.verification.warnings[:5]:
        lines.append(f"- warning: {warning}")
    if package.verification.blockers or package.verification.warnings:
        lines.append("")

    diagnostics = {d.code for d in result.document.diagnostics}
    if diagnostics:
        lines.extend([f"- ingestion diagnostics: {sorted(diagnostics)}", ""])

    return lines, passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="include PDF fixtures (slow)")
    parser.add_argument("--only", default=None, help="restrict to fixtures matching this substring")
    parser.add_argument(
        "--repeats", type=int, default=2, help="runs per document for stability measurement"
    )
    parser.add_argument("--out", type=Path, default=None, help="write the report to a file")
    args = parser.parse_args()

    from docling.document_converter import DocumentConverter

    corpus = DOCX_CORPUS + (PDF_CORPUS if args.pdf else [])
    if args.only:
        corpus = [n for n in DOCX_CORPUS + PDF_CORPUS if args.only.lower() in n.lower()]
        if not corpus:
            print(f"no fixture matches --only {args.only!r}", file=sys.stderr)
            return 2

    converter = DocumentConverter()
    lines = ["# Docling extraction corpus report", ""]
    failures: list[str] = []

    for name in corpus:
        path = SAMPLES / name
        if not path.exists():
            print(f"skip {name}: not present", file=sys.stderr)
            continue

        runs = [
            run_extraction(path, title=path.stem, converter=converter)
            for _ in range(max(args.repeats, 1))
        ]
        document_lines, passed = _report_document(name, runs)
        lines.extend(document_lines)
        if not passed:
            failures.append(name)
        print(f"processed {name}", file=sys.stderr)

    lines.extend(
        [
            "## Verdict",
            "",
            (
                f"{len(failures)} document(s) failed: {failures}"
                if failures
                else f"All {len(corpus)} document(s) passed every gate."
            ),
            "",
        ]
    )

    report = "\n".join(lines)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"written to {args.out}", file=sys.stderr)
    else:
        print(report)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
