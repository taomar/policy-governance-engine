"""Canonical normalization helpers (Section 13.4).

Deterministic canonical JSON serialization used for hashing. Property ordering
is fixed by sorting keys; dates use ISO 8601; numbers/booleans use native JSON
representations.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    """Serialize `data` to a canonical JSON string.

    - Keys sorted alphabetically at every level.
    - No insignificant whitespace.
    - UTF-8, non-ASCII characters kept as-is (ensure_ascii=False) for stable
      byte-for-byte comparison of the same logical content.
    """

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def canonical_hash(data: Any) -> str:
    """Return a stable SHA-256 hex digest over the canonical JSON of `data`."""

    payload = canonical_json(data).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
