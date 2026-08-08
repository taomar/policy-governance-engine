"""Unit tests for canonical JSON serialization and hashing (Section 13.4/27.5)."""
from __future__ import annotations

from policy_platform.contracts.canonical import canonical_hash, canonical_json


class TestCanonicalJson:
    def test_key_order_does_not_affect_output(self):
        a = {"b": 1, "a": 2, "c": 3}
        b = {"a": 2, "c": 3, "b": 1}
        assert canonical_json(a) == canonical_json(b)

    def test_nested_key_order_does_not_affect_output(self):
        a = {"outer": {"z": 1, "y": 2}}
        b = {"outer": {"y": 2, "z": 1}}
        assert canonical_json(a) == canonical_json(b)

    def test_no_insignificant_whitespace(self):
        result = canonical_json({"a": 1, "b": [1, 2, 3]})
        assert " " not in result

    def test_different_content_produces_different_output(self):
        assert canonical_json({"a": 1}) != canonical_json({"a": 2})


class TestCanonicalHash:
    def test_same_content_same_hash_regardless_of_key_order(self):
        a = {"z": 1, "a": {"y": 2, "x": 3}}
        b = {"a": {"x": 3, "y": 2}, "z": 1}
        assert canonical_hash(a) == canonical_hash(b)

    def test_different_content_different_hash(self):
        assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})

    def test_hash_is_stable_sha256_hex_length(self):
        result = canonical_hash({"a": 1})
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_is_deterministic_across_repeated_calls(self):
        payload = {"list": [3, 1, 2], "nested": {"b": True, "a": None}}
        assert canonical_hash(payload) == canonical_hash(payload)
