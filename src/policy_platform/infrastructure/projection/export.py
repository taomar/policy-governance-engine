"""Deterministic export serialization for governed rule data.

Lets policy composers/reviewers and policy managers pull approved rules or
in-review candidates out of the platform in whichever shape their downstream
tooling (spreadsheets, other systems, archival) expects. Three formats are
supported: pretty-printed JSON (array), JSONL (one compact JSON object per
line — convenient for streaming/log-style ingestion), and CSV (flattened,
Excel-friendly). No field is ever summarized or reworded here — this is a
verbatim structural re-serialization of already-persisted data.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from pydantic import BaseModel

ExportFormat = Literal["json", "jsonl", "csv"]

_MEDIA_TYPES: dict[str, str] = {
    "json": "application/json",
    "jsonl": "application/x-ndjson",
    "csv": "text/csv",
}

_EXTENSIONS: dict[str, str] = {
    "json": "json",
    "jsonl": "jsonl",
    "csv": "csv",
}


def media_type_for(fmt: str) -> str:
    try:
        return _MEDIA_TYPES[fmt]
    except KeyError as exc:  # pragma: no cover - guarded by Literal at the API boundary
        raise ValueError(f"unsupported export format '{fmt}'") from exc


def extension_for(fmt: str) -> str:
    try:
        return _EXTENSIONS[fmt]
    except KeyError as exc:  # pragma: no cover
        raise ValueError(f"unsupported export format '{fmt}'") from exc


def _flatten_for_csv(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten one export row for CSV.

    Scalars pass through unchanged; nested structures (lists/dicts, e.g. a
    rule's `condition` or `exceptions`) are JSON-encoded into a single cell
    so no information is dropped — it just isn't further tabulated within
    that column. `None` becomes an empty cell rather than the literal
    string "None".
    """
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, default=str, ensure_ascii=False)
        elif value is None:
            flat[key] = ""
        else:
            flat[key] = value
    return flat


def rows_to_export(rows: list[dict[str, Any]], fmt: ExportFormat) -> bytes:
    """Serialize a list of plain (already JSON-safe) dict rows to `fmt`."""
    if fmt == "json":
        return json.dumps(rows, default=str, ensure_ascii=False, indent=2).encode("utf-8")
    if fmt == "jsonl":
        lines = [json.dumps(row, default=str, ensure_ascii=False) for row in rows]
        return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    if fmt == "csv":
        if not rows:
            return b""
        flat_rows = [_flatten_for_csv(r) for r in rows]
        # Union of keys across all rows, preserving first-seen order, so
        # rows with sparse/optional fields don't silently drop columns
        # that a later row does populate.
        fieldnames: list[str] = []
        seen: set[str] = set()
        for r in flat_rows:
            for k in r:
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)
        # utf-8-sig (BOM) so Excel opens the file with correct encoding
        # instead of mangling non-ASCII characters.
        return buffer.getvalue().encode("utf-8-sig")
    raise ValueError(f"unsupported export format '{fmt}'")  # pragma: no cover


def models_to_export(models: list[BaseModel], fmt: ExportFormat) -> bytes:
    """Convenience wrapper for a list of Pydantic models (e.g. `CanonicalRule`)."""
    rows = [m.model_dump(mode="json") for m in models]
    return rows_to_export(rows, fmt)


def content_disposition(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}
