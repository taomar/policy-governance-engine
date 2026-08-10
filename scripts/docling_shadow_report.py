"""Run the Docling shadow comparison over the sample corpus.

Migration QA only: this compares the legacy parsers against Docling so the
cutover decision rests on measured fidelity rather than expectation. It is not
part of the ingestion path.

    python scripts/docling_shadow_report.py [--pdf] [--out PATH]

PDF is opt-in because layout inference costs roughly 195 seconds per document
against 0.3 seconds for DOCX, and because it needs TORCHDYNAMO_DISABLE=1 on
Windows without a Visual C++ toolchain (see
docs/specs/docling-integration-operating-notes.md).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Must be set before torch is imported by the Docling pipeline.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
warnings.filterwarnings("ignore")

from policy_platform.infrastructure.docling.converter import convert_document  # noqa: E402
from policy_platform.infrastructure.docling.shadow_comparison import (  # noqa: E402
    compare,
    format_report,
)

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
    ".pdf": "application/pdf",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="include PDF fixtures (slow)")
    parser.add_argument(
        "--only",
        default=None,
        help="restrict the run to fixtures whose filename contains this substring",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the report to a file")
    args = parser.parse_args()

    from docling.document_converter import DocumentConverter

    from policy_platform.infrastructure import document_extraction

    corpus = DOCX_CORPUS + (PDF_CORPUS if args.pdf else [])
    if args.only:
        # An explicit --only implies the caller wants that fixture regardless of
        # format, so the PDF opt-in is not additionally required.
        corpus = [name for name in DOCX_CORPUS + PDF_CORPUS if args.only.lower() in name.lower()]
        if not corpus:
            print(f"no fixture matches --only {args.only!r}", file=sys.stderr)
            return 2

    docling_converter = DocumentConverter()
    comparisons = []

    for name in corpus:
        path = SAMPLES / name
        if not path.exists():
            print(f"skip {name}: not present", file=sys.stderr)
            continue

        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        legacy = document_extraction.extract_document(str(path), _MIME[path.suffix.lower()])
        docling = convert_document(path, source_hash=source_hash, converter=docling_converter)

        comparisons.append(compare(legacy, docling, document_name=name))
        print(f"compared {name}", file=sys.stderr)

    report = format_report(comparisons)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"written to {args.out}", file=sys.stderr)
    else:
        print(report)

    return 1 if any(c.blocks_cutover for c in comparisons) else 0


if __name__ == "__main__":
    raise SystemExit(main())
