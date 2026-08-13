"""A candidate and a published rule describe the same record the same way.

There are two read paths. `mappers._rule_to_contract` rebuilds a published rule
from its stored columns; `candidate_rules._with_decision_readiness` rebuilds a
candidate from its formulation. Both derive the same set of views — readiness,
the attribute table, the fact model, the evaluation mode, the condition
provenance — and each has to be updated when one of those derivations is added
or corrected.

That is exactly what went wrong: the attribute table was added to the published
path and to extraction, and the candidate path kept returning an empty one. The
API served all forty-six records with `attributes` present and empty, which
reads as "this rule has no attributes" rather than as "nobody filled this in" —
the same conflation the condition provenance exists to prevent, one field over.

Rather than list the derived fields here and let the list rot, this compares
the two paths by inspecting what each actually assigns.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from policy_platform.api.routers import candidate_rules as candidate_module
from policy_platform.infrastructure.persistence import mappers as mappers_module


def _keys_assigned_in_model_copy(source: str) -> set[str]:
    """Field names passed in a `model_copy(update={...})` call."""

    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "model_copy"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "update" and isinstance(keyword.value, ast.Dict):
                keys.update(
                    key.value
                    for key in keyword.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
    return keys


def _keys_assigned_in_constructor(source: str, name: str) -> set[str]:
    """Keyword arguments passed to a `name(...)` constructor call."""

    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if called != name:
            continue
        keys.update(keyword.arg for keyword in node.keywords if keyword.arg)
    return keys


def test_the_candidate_path_derives_everything_the_published_path_does():
    """Neither path may quietly omit a view the other supplies.

    Read from the code rather than from a hand-maintained list, so a derivation
    added to one path and forgotten in the other fails here instead of shipping
    as an empty field.
    """

    candidate_source = inspect.getsource(candidate_module._with_decision_readiness)
    candidate_keys = _keys_assigned_in_model_copy(candidate_source)

    published_source = Path(inspect.getfile(mappers_module)).read_text(encoding="utf-8")
    published_keys = _keys_assigned_in_constructor(published_source, "CanonicalRule")

    derived = {
        "decision_readiness",
        "xacml_view",
        "condition_provenance",
        "evaluation_mode",
        "fact_model",
        "attributes",
    }

    missing_from_candidate = (derived & published_keys) - candidate_keys
    assert not missing_from_candidate, (
        "the candidate read path does not derive: "
        f"{sorted(missing_from_candidate)} — a candidate would serve these empty"
    )

    missing_from_published = (derived & candidate_keys) - published_keys
    assert not missing_from_published, (
        "the published read path does not derive: "
        f"{sorted(missing_from_published)} — a published rule would serve these empty"
    )


def test_both_paths_derive_the_attribute_table():
    """Named explicitly, because this is the one that shipped empty."""

    candidate_keys = _keys_assigned_in_model_copy(
        inspect.getsource(candidate_module._with_decision_readiness)
    )
    published_keys = _keys_assigned_in_constructor(
        Path(inspect.getfile(mappers_module)).read_text(encoding="utf-8"), "CanonicalRule"
    )

    assert "attributes" in candidate_keys
    assert "attributes" in published_keys
