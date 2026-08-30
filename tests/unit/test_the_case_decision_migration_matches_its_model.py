"""The case-decision migration and its model describe the same table.

WHY THIS IS A STATIC CHECK

This repository has no test that executes a migration, and adding one would need
a live Postgres: the schema uses `JSONB` and `gen_random_uuid()`, neither of
which SQLite can stand in for without the check quietly stopping being about the
real DDL. So the convention here is followed rather than broken — the migration
is *applied* against a real database as part of shipping, and what is held in
the suite is the thing a manual apply cannot catch on its own.

That thing is drift. A model column added without a migration is invisible until
a deployed instance raises `UndefinedColumn` on a query nobody ran locally,
because the development database was created from `Base.metadata.create_all` and
already has it. The reverse — a migration column with no model — is a column
nothing reads and nobody deletes. Both are caught here by comparing the two
descriptions of one table: the model against the *sum* of the migration that
creates it and every migration that later alters it.

The revision graph is checked for the same reason: a second head is not
discovered at review time, it is discovered when `alembic upgrade head` refuses
to run, which is normally during a deployment. An altering migration is also
walked back to the creating one, because a column added before its table exists
is an ordering fault that only a deployment can find.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from policy_platform.domain.models import PolicyCaseDecision

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

#: The migration that creates the table.
MIGRATION = VERSIONS / "a4e2c7b18f36_policy_case_decisions_table.py"

#: Migrations that alter it afterwards, in the order they apply. The model is
#: compared against the *sum* of all of them: a column added by a later
#: migration is as real as one in the original `create_table`, and a check that
#: only read the first would report every subsequent addition as drift.
ALTERATIONS = (VERSIONS / "b8f3d2a67c14_case_decision_v2_columns.py",)

#: The revision this repository's history currently ends at. Named so that
#: adding a migration is a deliberate edit here rather than a test that quietly
#: follows whatever the tree happens to contain — a check that derives the
#: expected head from the tree cannot detect a second one.
#:
#: Moved by the projection-faithfulness gate, which added the
#: `policy_index_states.quality_*` columns on top of the corpus-projection
#: milestone's `projection_profile`. All three migrations are unrelated in
#: subject and strictly ordered in history, which is exactly what this constant
#: is here to make visible.
EXPECTED_HEAD = "e3a7c9d15b82"

TABLE = "policy_case_decisions"

_REVISION_RE = re.compile(r"^revision(?::[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
_DOWN_RE = re.compile(r"^down_revision(?::[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)


def _revision_graph() -> dict[str, str | None]:
    graph: dict[str, str | None] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        revision = _REVISION_RE.search(source)
        if revision is None:
            continue
        down = _DOWN_RE.search(source)
        graph[revision.group(1)] = down.group(1) if down else None
    return graph


def _created_columns() -> set[str]:
    """The column names the creating migration's `create_table` declares.

    Read from the syntax tree rather than by executing the module, because
    importing it runs `alembic.op` bindings that only exist inside a migration
    context. The parse is narrow on purpose: it looks for `sa.Column("name", …)`
    inside the `create_table` call for this table, so a `Column` mentioned in a
    comment or in `downgrade` cannot inflate the set.
    """

    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    columns: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "create_table"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != TABLE:
            continue
        for arg in node.args[1:]:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "Column"
                and arg.args
                and isinstance(arg.args[0], ast.Constant)
            ):
                columns.add(arg.args[0].value)
    return columns


def _added_columns(path: Path) -> set[str]:
    """The columns one later migration's `upgrade` adds to this table.

    Only `op.add_column(TABLE, sa.Column("name", …))` counts, and only for this
    table — the same narrowness as the create parse, for the same reason. The
    `add_column` calls in a `downgrade` do not exist (a downgrade drops), so
    scanning the whole module cannot double-count.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    columns: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_column"):
            continue
        if len(node.args) < 2:
            continue
        table = node.args[0]
        # The table may be a literal or the module's own `TABLE` constant.
        named_table = (
            table.value
            if isinstance(table, ast.Constant)
            else (table.id if isinstance(table, ast.Name) and table.id == "TABLE" else None)
        )
        if named_table not in (TABLE, "TABLE"):
            continue
        column = node.args[1]
        if (
            isinstance(column, ast.Call)
            and isinstance(column.func, ast.Attribute)
            and column.func.attr == "Column"
            and column.args
            and isinstance(column.args[0], ast.Constant)
        ):
            columns.add(column.args[0].value)
    return columns


def _migration_columns() -> set[str]:
    """Every column the migration history leaves on the table."""

    columns = _created_columns()
    for path in ALTERATIONS:
        columns |= _added_columns(path)
    return columns


def test_the_migration_file_exists_and_is_parseable() -> None:
    """The floor assertion. Every check below returns an empty set if it does not."""

    assert MIGRATION.exists(), f"{MIGRATION.name} is missing"
    assert _created_columns(), "no columns were parsed out of the creating migration"


def test_every_altering_migration_is_present_and_adds_something() -> None:
    """A later migration listed here but parsed as empty is a silent hole.

    Without this, renaming `op.add_column` or moving the additions into a helper
    would leave `_migration_columns` returning only the original create set — and
    the drift check above would then start passing for the wrong reason.
    """

    for path in ALTERATIONS:
        assert path.exists(), f"{path.name} is missing"
        assert _added_columns(path), f"no added columns were parsed out of {path.name}"


def test_the_migration_and_the_model_declare_the_same_columns() -> None:
    """Neither description of the table may grow a column the other lacks."""

    model_columns = {column.name for column in PolicyCaseDecision.__table__.columns}
    migration_columns = _migration_columns()

    missing_from_migration = sorted(model_columns - migration_columns)
    missing_from_model = sorted(migration_columns - model_columns)

    assert not missing_from_migration, (
        "these columns exist on the model and not in the migration, so a deployed "
        f"database will not have them: {missing_from_migration}"
    )
    assert not missing_from_model, (
        "these columns exist in the migration and not on the model, so nothing "
        f"reads or writes them: {missing_from_model}"
    )


@pytest.mark.parametrize(
    "constraint",
    [
        "uq_policy_case_decisions_idempotency",
        "ck_policy_case_decisions_status",
    ],
)
def test_the_constraints_that_carry_the_design_are_in_the_migration(constraint: str) -> None:
    """Two constraints are load-bearing, not decoration.

    The unique constraint is what makes a concurrent duplicate reservation
    *fail* rather than produce two decisions for one idempotency key — the
    application's race handling is built on catching it, so without it in the
    database that handling is unreachable code. The check constraint is what
    stops a receipt reaching a state no reader knows how to interpret.
    """

    source = MIGRATION.read_text(encoding="utf-8")
    assert constraint in source


def test_the_migration_reverses_what_it_creates() -> None:
    """A downgrade that leaves the table behind is not a downgrade.

    Both indexes are dropped before the table on purpose: dropping the table
    first works on Postgres but not on every backend, and an ordering that
    happens to work is the kind that stops working during a rollback.
    """

    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade()", 1)[1]

    assert f'op.drop_table("{TABLE}")' in downgrade
    for index in ("ix_policy_case_decisions_set_received", "ix_policy_case_decisions_correlation_id"):
        assert index in downgrade
        assert downgrade.index(index) < downgrade.index("drop_table")


def test_the_revision_chains_onto_the_previous_head_and_leaves_one() -> None:
    """A second head is discovered by `alembic upgrade head` refusing to run.

    That normally happens during a deployment, which is the most expensive place
    to learn it, so the graph is checked here instead.
    """

    graph = _revision_graph()
    assert len(graph) > 10, f"only {len(graph)} revisions parsed; the scan is broken"

    created = _REVISION_RE.search(MIGRATION.read_text(encoding="utf-8")).group(1)
    assert created in graph

    parents = {down for down in graph.values() if down}
    heads = sorted(rev for rev in graph if rev not in parents)

    assert heads == [EXPECTED_HEAD], f"expected a single head at {EXPECTED_HEAD}, found {heads}"


def test_every_altering_migration_chains_onto_the_creating_one() -> None:
    """A migration altering this table must come *after* it is created.

    Alembic would not order two unrelated revisions for us, and a column added
    before its table exists fails on the deployment that runs it rather than in
    review. Walking each alteration's ancestry back to the create is what makes
    that ordering a property of the file rather than of the filename.
    """

    graph = _revision_graph()
    created = _REVISION_RE.search(MIGRATION.read_text(encoding="utf-8")).group(1)

    for path in ALTERATIONS:
        revision = _REVISION_RE.search(path.read_text(encoding="utf-8")).group(1)
        assert revision in graph, f"{path.name} declares no revision the graph can see"

        ancestry: list[str] = []
        cursor: str | None = graph[revision]
        while cursor is not None and cursor not in ancestry:
            ancestry.append(cursor)
            cursor = graph.get(cursor)

        assert created in ancestry, (
            f"{path.name} alters {TABLE} but does not descend from the migration that "
            f"creates it ({created}); its ancestry is {ancestry}"
        )


def test_every_altering_migration_drops_what_it_adds() -> None:
    """An `upgrade` with no matching `downgrade` is a one-way door.

    The columns are nullable and additive, so a rollback is genuinely possible
    here — which means a downgrade that forgot one would leave a column nothing
    reads and nobody remembers adding.
    """

    for path in ALTERATIONS:
        source = path.read_text(encoding="utf-8")
        added = _added_columns(path)
        downgrade = source.split("def downgrade()", 1)[1]
        for column in sorted(added):
            assert f'drop_column(TABLE, "{column}")' in downgrade or (
                f'drop_column("{TABLE}", "{column}")' in downgrade
            ), f"{path.name} adds {column} and never drops it"
