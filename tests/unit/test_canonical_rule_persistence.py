"""Guards against silently dropping a `CanonicalRule` field at publish time.

This defect class has now occurred three times in this codebase:

1. `is_explicit_override` / `supersedes_rule_ids` and `RuleException.limit_value`
   / `limit_unit` — added to the contract, never persisted. Fixed by migration
   c9a1d4e0f2b3 (see ADR-0009 "related discovery").
2. The entire `AggregateLimit` construct — no table at all. Same migration.
3. `formulation` — the policy-formulator agent's canonical decomposition and DMN
   projection. Fixed by migration e4c7a2b8d190.

The shape is always identical. `contracts.policy.CanonicalRule` is the source of
truth, but `domain.models.ApprovedRule` is a *decomposed relational projection*
of it rather than a single stored document. Adding a field to the contract
therefore does not add a column, and nothing anywhere fails: the publish path
simply never reads the new field, and `mappers._rule_to_contract` rebuilds the
rule using the contract's own default. The rule round-trips as a valid object
that is quietly missing data, so no type error, no constraint violation and no
test failure ever points at it. It surfaces much later as "why did my data
disappear when I published?".

`_rule_to_contract` is the correct place to catch this. A field that is never
written cannot be read, so a read-side check catches both halves of the bug:
a missing column, and a column that exists but is not populated at publish.

These tests read the mapper's source rather than round-tripping through a
database so they stay in the fast unit suite and fail at the exact moment a
contributor adds a contract field.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure import mappers


# Fields the mapper legitimately derives from somewhere other than a same-named
# column, so a literal name match would not find them. Each entry records where
# the value actually comes from, so this set cannot quietly become a dumping
# ground for genuinely dropped fields.
DERIVED_FIELDS = {
    # Walks the relationship to the parent version rather than a local column.
    "policy_set_id": "rule.policy_version.policy_set_id",
    "policy_version_id": "rule.policy_version_id",
    # Stored as `revision`; `rule_revision` is the contract's name for it.
    "rule_revision": "rule.revision",
    # Built from the related PolicyAuthority row.
    "authority": "rule.authority",
    # Separate tables, loaded via relationships.
    "exceptions": "rule.exceptions",
    "evidence": "rule.evidence",
    # Constant contract metadata, not persisted per row.
    "schema_version": "contract default",
}


def _mapper_assigned_fields() -> set[str]:
    """Field names `_rule_to_contract` passes to the `CanonicalRule` constructor."""

    source = inspect.getsource(mappers._rule_to_contract)
    tree = ast.parse(textwrap.dedent(source))

    assigned: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "CanonicalRule":
            continue
        for keyword in node.keywords:
            if keyword.arg:
                assigned.add(keyword.arg)
    return assigned


def test_mapper_populates_every_canonical_rule_field() -> None:
    """Every contract field must be explicitly populated when reading a published rule.

    If this fails, a field was added to `CanonicalRule` without being persisted
    on `ApprovedRule` and read back in `_rule_to_contract`. The rule will still
    validate — it will just silently carry the contract default forever, and the
    data will be destroyed for every rule published in the meantime.
    """

    contract_fields = set(CanonicalRule.model_fields)
    assigned = _mapper_assigned_fields()
    missing = contract_fields - assigned - set(DERIVED_FIELDS)

    assert not missing, (
        "CanonicalRule field(s) not populated by mappers._rule_to_contract: "
        f"{sorted(missing)}. A published rule would silently carry the contract "
        "default for these, discarding whatever was approved. Add a column on "
        "ApprovedRule, write it in policy_version_import, read it here — or, if "
        "the value really is derived from elsewhere, record where in "
        "DERIVED_FIELDS with a justification."
    )


def test_derived_fields_are_real_contract_fields() -> None:
    """DERIVED_FIELDS must not outlive the fields it exempts.

    Without this, renaming or removing a contract field would leave a stale
    exemption behind that could later mask a genuinely dropped field of the same
    name.
    """

    stale = set(DERIVED_FIELDS) - set(CanonicalRule.model_fields)
    assert not stale, f"DERIVED_FIELDS names field(s) no longer on CanonicalRule: {sorted(stale)}"


def test_formulation_is_read_back() -> None:
    """Regression test for the specific field this guard was written after.

    `formulation` is the formulator agent's record, and the contract keeps it
    precisely because the executable fields are a lossy projection of it. It was
    dropped at publish for every rule until migration e4c7a2b8d190.
    """

    assert "formulation" in _mapper_assigned_fields()


@pytest.mark.parametrize("field", sorted(DERIVED_FIELDS))
def test_derived_field_documents_its_source(field: str) -> None:
    """Each exemption must say where the value comes from, not just that it is exempt."""

    assert DERIVED_FIELDS[field].strip(), f"{field} is exempted without recording its source"
