"""An ingestion problem must outlive the upload that produced it.

WHY THIS EXISTS

`upload_document` built `ingestion_diagnostics`, populated it from the extractor,
and returned it in the HTTP response -- and nothing wrote it anywhere. The same
was true of the extraction error caught by the deliberately non-blocking
`except` clause. So a diagnostic with `severity="error"` saying the source
fragments do not resolve to the recorded text was shown exactly once, to
whoever happened to run the upload, and was then unrecoverable. Every reviewer
and auditor who looked at that document afterwards saw a version row identical
to a clean one.

This is the ingestion half of an idea the codebase has now had to learn twice:
a check that runs, produces a correct answer, and reaches nobody. It already
cost a measurable thing -- an agent trying to establish whether a
fragment-resolution error was new or pre-existing could not, because no baseline
had its diagnostics stored, and had to prove it the hard way by comparing
content hashes and clause text across uploads.

The invariant guarded here is: **a document whose ingestion produced an error
must not present as clean.** That is a claim about three seams, and it fails if
any one of them breaks, so all three are checked separately:

  1. the WRITE seam -- the router assigns both facts onto the version before it
     commits (this is where the defect was);
  2. the DURABLE seam -- the columns exist on the model and are nullable, so an
     unobserved older version stays honestly unknown rather than being
     backfilled into looking clean;
  3. the READER seam -- the list endpoint carries them, the derivation refuses
     to call an unrecorded ingestion "ok", and the register renders every
     status the API can emit.

Seam 3 is the one worth insisting on. Storing the diagnostic and leaving it
unread would be the same defect one layer down -- which is exactly what happened
the morning a run status was fixed and the colour beside it still said
"pending".

FLOOR PLACEMENT -- WHY THE VOLUME CHECKS COME FIRST

Every verdict below is a SET DIFFERENCE: what the scan failed to find. That
inverts the usual placement rule.

  - A guard whose verdict is an OFFENDER LIST puts its floor LAST, so the floor
    cannot shadow a real offender during a fails-before proof.
  - A guard whose verdict is a SET DIFFERENCE puts its floor FIRST. A blind scan
    here does not fall silent -- it reports the produced set as empty and
    therefore accuses the router of storing nothing, the model of having no
    columns and the UI of covering no statuses, all at once, in detail, and
    wrongly. Someone would act on that. The floor has to fire before any
    difference is computed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from policy_platform.api.schemas import (
    INGESTION_STATUS_ERROR,
    INGESTION_STATUS_OK,
    INGESTION_STATUS_UNRECORDED,
    INGESTION_STATUS_WARNING,
    ingestion_status_of,
)

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "src" / "policy_platform" / "api" / "routers" / "documents.py"
MODELS = ROOT / "src" / "policy_platform" / "domain" / "models.py"
SCHEMAS = ROOT / "src" / "policy_platform" / "api" / "schemas.py"
UI_OUTCOMES = ROOT / "apps" / "web" / "src" / "ingestionOutcome.ts"
UI_REGISTER = ROOT / "apps" / "web" / "src" / "components" / "DocumentsPage.tsx"

#: The two facts that must survive the request. Named, not counted: this is the
#: whole point of the guard and a floor of "at least one" would let either half
#: disappear silently.
PERSISTED_COLUMNS = ("ingestion_diagnostics_json", "ingestion_error")

#: `upload_document` assigns a good number of locals. Six is a floor, not a
#: target -- it catches an AST walk that found nothing or latched onto some
#: small unrelated function, without breaking when a line is added.
_MINIMUM_ROUTER_STATEMENTS = 6
#: DocumentVersion carries the original five columns plus these two.
_MINIMUM_MODEL_COLUMNS = 5
#: ok / warning / error / unrecorded. Four is the count today; three would mean
#: the regex stopped matching part of the map.
_MINIMUM_UI_STATUSES = 3
#: _to_response builds each version from the original six keys plus three
#: ingestion ones, and also builds the document dict around them.
_MINIMUM_RESPONSE_KEYS = 6


# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------


def _upload_function() -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "upload_document":
            return node
    return None


def _version_attribute_writes() -> dict[str, int]:
    """`<something>.<attr> = ...` inside `upload_document`, attr -> line number."""
    fn = _upload_function()
    if fn is None:
        return {}
    writes: dict[str, int] = {}
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute):
                writes[target.attr] = target.lineno
    return writes


def _commit_line() -> int | None:
    """Line of the `session.commit()` that ends the upload transaction."""
    fn = _upload_function()
    if fn is None:
        return None
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
            return node.lineno
    return None


def _document_version_columns() -> dict[str, str]:
    """Column name -> the source of its `mapped_column(...)` call, for DocumentVersion."""
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    source = MODELS.read_text(encoding="utf-8").splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "DocumentVersion":
            continue
        columns: dict[str, str] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                end = stmt.end_lineno or stmt.lineno
                columns[stmt.target.id] = "\n".join(source[stmt.lineno - 1 : end])
        return columns
    return {}


def _response_version_keys() -> set[str]:
    """String keys of the per-version dict built in `_to_response`."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) or node.name != "_to_response":
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Dict):
                for key in inner.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
    return keys


def _api_statuses() -> set[str]:
    """Values of the `INGESTION_STATUS_*` constants, read from the source."""
    tree = ast.parse(SCHEMAS.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("INGESTION_STATUS_"):
                if isinstance(node.value.value, str):
                    found.add(node.value.value)
    return found


def _ui_statuses() -> set[str]:
    """Keys of the `INGESTION_OUTCOMES` map in the web layer."""
    if not UI_OUTCOMES.exists():
        return set()
    source = UI_OUTCOMES.read_text(encoding="utf-8")
    match = re.search(r"INGESTION_OUTCOMES[^=]*=\s*\{(.*?)\n\};", source, re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*):\s*\{", match.group(1), re.M))


# --------------------------------------------------------------------------
# Floors first. See the module docstring: a blind scan here accuses three
# separate layers rather than falling quiet.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [ROUTER, MODELS, SCHEMAS, UI_OUTCOMES, UI_REGISTER],
    ids=lambda p: p.name,
)
def test_every_scanned_file_is_readable(path: Path) -> None:
    assert path.exists(), f"scanned file not found at {path}; every check below it is vacuous"


def test_router_function_extraction_still_sees() -> None:
    fn = _upload_function()
    assert fn is not None, (
        "no function named 'upload_document' found in documents.py. It may have "
        "been renamed or moved; fix this extractor before trusting the "
        "persistence checks below, which would otherwise report that the "
        "router stores nothing."
    )
    assert len(fn.body) >= _MINIMUM_ROUTER_STATEMENTS, (
        f"upload_document parsed to only {len(fn.body)} top-level statement(s), "
        f"expected at least {_MINIMUM_ROUTER_STATEMENTS}. The AST walk has "
        "latched onto the wrong function."
    )


def test_model_column_extraction_still_sees() -> None:
    columns = _document_version_columns()
    assert len(columns) >= _MINIMUM_MODEL_COLUMNS, (
        f"read only {len(columns)} column(s) from DocumentVersion ({sorted(columns)}), "
        f"expected at least {_MINIMUM_MODEL_COLUMNS}. The class may have been "
        "renamed or its columns declared some other way."
    )


def test_status_extraction_still_sees_on_both_sides() -> None:
    api, ui = _api_statuses(), _ui_statuses()
    assert len(api) >= _MINIMUM_UI_STATUSES, (
        f"read only {len(api)} INGESTION_STATUS_* constant(s) from schemas.py ({sorted(api)}). "
        "Without them the coverage check below would pass while comparing nothing."
    )
    assert len(ui) >= _MINIMUM_UI_STATUSES, (
        f"read only {len(ui)} key(s) from INGESTION_OUTCOMES ({sorted(ui)}), expected "
        f"at least {_MINIMUM_UI_STATUSES}. The map may have been renamed or reshaped; "
        "a blind read here would accuse the UI of covering no statuses at all."
    )


def test_response_key_extraction_still_sees() -> None:
    """A blind read here accuses _to_response of carrying nothing at all."""
    keys = _response_version_keys()
    assert len(keys) >= _MINIMUM_RESPONSE_KEYS, (
        f"read only {len(keys)} key(s) from _to_response ({sorted(keys)}), expected "
        f"at least {_MINIMUM_RESPONSE_KEYS}. The function may have been renamed or "
        "changed to build versions somewhere else; fix this extractor before "
        "believing its verdict that the list endpoint carries no ingestion fields."
    )


# --------------------------------------------------------------------------
# Seam 1 -- the write path. This is where the defect was.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", PERSISTED_COLUMNS)
def test_upload_persists_the_ingestion_fact(column: str) -> None:
    writes = _version_attribute_writes()
    assert column in writes, (
        f"upload_document never assigns {column!r} onto the document version, so "
        "this ingestion fact exists only in the HTTP response and is lost the "
        "moment the request ends. That is the original defect: a diagnostic with "
        "severity='error' would be shown once to the uploader and be "
        "unrecoverable to every reviewer afterwards. Assigned attributes were: "
        f"{sorted(writes)}."
    )


@pytest.mark.parametrize("column", PERSISTED_COLUMNS)
def test_the_ingestion_fact_is_written_before_the_commit(column: str) -> None:
    """Assigning after the commit would leave it in memory only -- the same defect."""
    writes = _version_attribute_writes()
    commit = _commit_line()
    assert commit is not None, "no session.commit() found in upload_document"
    assert column in writes, f"{column!r} is not assigned at all; see the previous test"
    assert writes[column] < commit, (
        f"{column!r} is assigned on line {writes[column]}, after the commit on "
        f"line {commit}. The value would never reach the database, which is "
        "indistinguishable from not storing it at all."
    )


# --------------------------------------------------------------------------
# Seam 2 -- the durable columns.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", PERSISTED_COLUMNS)
def test_document_version_has_somewhere_to_put_it(column: str) -> None:
    columns = _document_version_columns()
    assert column in columns, (
        f"DocumentVersion has no {column!r} column, so the router's assignment "
        f"would be an ordinary Python attribute that SQLAlchemy never persists. "
        f"Declared columns: {sorted(columns)}."
    )


@pytest.mark.parametrize("column", PERSISTED_COLUMNS)
def test_unobserved_versions_stay_unknown_rather_than_clean(column: str) -> None:
    """Nullable with no backfill, on purpose.

    Every version that predates these columns was ingested without anyone
    recording the outcome. A NOT NULL column with a default would write a
    verdict of "clean" over rows nobody observed -- manufacturing the exact
    false assurance this guard exists to prevent.
    """
    declaration = _document_version_columns().get(column, "")
    assert "nullable=True" in declaration, (
        f"{column!r} is not declared nullable. Existing rows were ingested "
        "before the column existed, so a non-null default would assert an "
        "outcome for ingestions that were never observed."
    )


# --------------------------------------------------------------------------
# Seam 3 -- the reader. Storing it and leaving it unread is the same defect.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["ingestion_diagnostics", "ingestion_error", "ingestion_status"])
def test_the_document_list_carries_it(key: str) -> None:
    keys = _response_version_keys()
    assert key in keys, (
        f"_to_response does not put {key!r} on each version, so a reviewer "
        "listing documents cannot tell a version that failed to read from one "
        f"that read cleanly. Keys produced: {sorted(keys)}."
    )


def test_the_register_renders_the_outcome() -> None:
    """Called, not merely mentioned.

    This assertion was first written as `"ingestionOutcome" in source` and an
    injection renaming the identifier to `ingestionOutcomeXX` passed it -- a
    substring test cannot tell a live call from a superstring of its own name.
    That is the same failure the reachability guard had when a quoted string
    spelling a function's name counted as a reference to it. Both halves are
    checked because either can rot alone: the import can survive a deleted
    call site, and a call can survive an import pointed somewhere else.
    """
    source = UI_REGISTER.read_text(encoding="utf-8")
    imported = re.search(r"""import\s*\{[^}]*\bingestionOutcome\b[^}]*\}\s*from\s*["'][^"']*ingestionOutcome["']""", source)
    called = re.search(r"\bingestionOutcome\s*\(", source)
    assert imported, (
        "DocumentsPage does not import ingestionOutcome from the wording module. "
        "The ingestion status would arrive in the browser and never be drawn."
    )
    assert called, (
        "DocumentsPage imports ingestionOutcome but never calls it, so the "
        "ingestion status reaches the client and not the reader. A fact stored "
        "and never rendered is the same defect one layer down."
    )


def test_every_status_the_api_can_emit_has_wording() -> None:
    api, ui = _api_statuses(), _ui_statuses()
    unrendered = sorted(api - ui)
    assert not unrendered, (
        f"the API can report ingestion status(es) {unrendered} that the UI has no "
        f"wording for; they would render as an empty cell. UI covers {sorted(ui)}."
    )


# --------------------------------------------------------------------------
# The derivation itself. Behaviour, not structure.
# --------------------------------------------------------------------------


def test_an_extraction_error_reads_as_error() -> None:
    assert ingestion_status_of([], "boom") == INGESTION_STATUS_ERROR


def test_an_error_severity_diagnostic_reads_as_error() -> None:
    diagnostics = [
        {"code": "fragment_unresolved", "severity": "error", "detail": ""},
        {"code": "low_text_density", "severity": "warning", "detail": ""},
    ]
    assert ingestion_status_of(diagnostics, None) == INGESTION_STATUS_ERROR


def test_a_warning_reads_as_warning_not_as_clean() -> None:
    assert ingestion_status_of([{"code": "x", "severity": "warning"}], None) == INGESTION_STATUS_WARNING


def test_an_observed_ingestion_with_nothing_to_report_reads_as_ok() -> None:
    assert ingestion_status_of([], None) == INGESTION_STATUS_OK


def test_an_unobserved_ingestion_is_not_called_clean() -> None:
    """NULL is not "ok". The distinction is the whole point of the column.

    A version ingested before diagnostics were persisted has no record either
    way. Reporting that as clean would be a claim nobody checked -- the same
    shape as a run status reading `completed` when coverage was short.
    """
    assert ingestion_status_of(None, None) == INGESTION_STATUS_UNRECORDED
    assert ingestion_status_of(None, None) != INGESTION_STATUS_OK
