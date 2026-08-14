"""The delete order is written by hand; the schema checks it.

`policy_set_teardown._DELETION_ORDER` cannot be derived from the schema, because
*how* each table reaches a policy set is semantic. The order it has to be in
can be derived, so it is checked here rather than trusted.

Two ways this goes wrong in production and neither is loud:

* A table is added with a `policy_set_id` and nobody updates the list. The
  delete then fails partway through against a real project, having already
  removed some of it.
* The order looks right by eye and is not. `candidate_rules` is one hop from
  `policy_sets` but also references `extraction_runs`, which is three hops away,
  so ordering by "distance from the policy set" -- the obvious reading -- puts
  the runs first and violates the constraint.

Both are structural, so both are caught here without a database.
"""
from __future__ import annotations

import pytest

from policy_platform.domain.models import Base
from policy_platform.infrastructure.persistence.policy_set_teardown import (
    RETAINED_TABLES,
    _DELETION_ORDER,
)

ROOT = "policy_sets"


def _fk_edges() -> set[tuple[str, str]]:
    """(child, parent) for every foreign key in the mapped schema."""

    edges: set[tuple[str, str]] = set()
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            if parent != table.name:
                edges.add((table.name, parent))
    return edges


def _reachable_from_root() -> set[str]:
    """Every table that hangs off `policy_sets`, at any depth."""

    edges = _fk_edges()
    seen = {ROOT}
    frontier = [ROOT]
    while frontier:
        nxt = []
        for parent in frontier:
            for child, target in edges:
                if target == parent and child not in seen:
                    seen.add(child)
                    nxt.append(child)
        frontier = nxt
    return seen - {ROOT}


def _order_violations(order: list[str]) -> list[str]:
    """Tables deleted before something that still points at them.

    Kept as a function taking the order so the test below can prove it catches
    a bad order, rather than only that the current one passes. A guard that has
    never been shown to fail is not evidence.
    """

    position = {table: i for i, table in enumerate(order)}
    violations = []
    for child, parent in sorted(_fk_edges()):
        if child in position and parent in position and position[parent] < position[child]:
            violations.append(f"{parent} is deleted before {child}, which references it")
    return violations


def test_every_reachable_table_is_deleted_or_deliberately_retained():
    """A new table hanging off a policy set must be handled, not forgotten."""

    handled = {table for table, _ in _DELETION_ORDER} | set(RETAINED_TABLES)
    unhandled = _reachable_from_root() - handled
    assert not unhandled, (
        f"tables reach policy_sets but teardown neither deletes nor retains them: "
        f"{sorted(unhandled)}. Add a DELETE to _DELETION_ORDER, or add it to "
        f"RETAINED_TABLES with the reason it should survive its project."
    )


def test_deletion_order_never_removes_a_parent_before_its_children():
    """The actual order, checked against the actual foreign keys."""

    order = [table for table, _ in _DELETION_ORDER]
    violations = _order_violations(order)
    assert not violations, "deletion order violates foreign keys:\n  " + "\n  ".join(violations)


def test_the_order_check_catches_the_mistake_it_exists_for():
    """Floor test: prove the check above can fail.

    Specifically the trap that the obvious ordering falls into -- deleting
    `extraction_runs` before `candidate_rules` because the runs look further
    from the policy set. If this passes, the check above is not testing
    anything.
    """

    order = [table for table, _ in _DELETION_ORDER]
    assert "candidate_rules" in order and "extraction_runs" in order

    broken = [t for t in order if t != "extraction_runs"]
    broken.insert(broken.index("candidate_rules"), "extraction_runs")

    violations = _order_violations(broken)
    assert any("candidate_rules" in v and "extraction_runs" in v for v in violations), (
        "the order check did not notice extraction_runs being deleted before the "
        f"candidate rules that reference it; it reported: {violations}"
    )


def test_no_table_is_both_deleted_and_retained():
    """Retention has to be a decision, not a duplicate entry."""

    deleted = {table for table, _ in _DELETION_ORDER}
    overlap = deleted & set(RETAINED_TABLES)
    assert not overlap, f"listed as both deleted and retained: {sorted(overlap)}"


def test_audit_events_are_retained():
    """A project's deletion must not erase the record that it existed.

    Pinned rather than left to convention: this codebase already treats a
    rejection as evidence rather than a deletion, and the same reasoning applies
    with more force to a whole project.
    """

    assert "audit_events" in RETAINED_TABLES
    assert "audit_events" not in {table for table, _ in _DELETION_ORDER}


@pytest.mark.parametrize("table", [t for t, _ in _DELETION_ORDER])
def test_every_delete_is_scoped_to_one_policy_set(table: str):
    """No statement may delete rows belonging to another project.

    Every statement has to be parameterised on `:sid`. An unscoped DELETE here
    would empty the table for every project on the instance, and would look
    exactly like a correct one in review.
    """

    statement = dict(_DELETION_ORDER)[table]
    assert ":sid" in statement, f"{table}: DELETE is not scoped to a policy set"
    assert "WHERE" in statement.upper(), f"{table}: DELETE has no WHERE clause"
