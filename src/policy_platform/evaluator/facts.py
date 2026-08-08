"""Fact canonicalization (Section 13.4 / 15.2).

Normalizes a raw fact dict into a stable form before evaluation and hashing:
- Keys sorted (handled by canonical_json at hash time; this module focuses on
  value normalization).
- date/datetime values normalized to ISO-8601 strings so that repeated
  evaluations with equivalent-but-differently-typed inputs (e.g. a `date`
  object vs. its ISO string) produce identical canonical hashes.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def canonicalize_facts(facts: dict[str, Any]) -> dict[str, Any]:
    def normalize(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        return value

    return {key: normalize(value) for key, value in sorted(facts.items())}
