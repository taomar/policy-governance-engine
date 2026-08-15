"""A migration must go where the caller said, and say where it went.

`alembic/env.py` used to set `sqlalchemy.url` from settings unconditionally, so
a caller who named a different database — by the documented route, calling
`Config.set_main_option` before `command.upgrade` — had that instruction read
and discarded without a word, and the run went to the ambient default instead.
The ambient default is production.

These tests pin two separate things, because either alone is insufficient:

* the *decision* honours an explicit target (the resolver's own behaviour); and
* `env.py` actually *asks* the resolver rather than deciding for itself.

A revert that reinstates the unconditional override would leave the first set
passing — the resolver would still exist and still work, reaching nobody. The
wiring test is what catches that.

Nothing here asserts any real URL, host or database name. The subject is the
precedence rule, which is a property of the code and not of any environment.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from policy_platform.infrastructure.persistence.migration_target import (
    DB_URL_X_ARG,
    MigrationTarget,
    apply_migration_target,
    explicit_url,
    redact_url,
    resolve_migration_target,
    url_in_ini_file,
)

_AMBIENT = "postgresql+psycopg://ambient_user:ambient_pw@ambient-host:5432/ambient_db"
_NAMED = "postgresql+psycopg://named_user:named_pw@named-host:5433/named_db"
_INI_VALUE = "driver://user:pass@localhost/dbname"

_ENV_PY = Path(__file__).resolve().parents[2] / "alembic" / "env.py"


class FakeConfig:
    """A stand-in for `alembic.config.Config`, matching the parts env.py uses.

    Deliberately mimics the behaviour that caused the incident: `set_main_option`
    writes into the same store `get_main_option` reads, so a programmatic value
    and an ini value are indistinguishable from the config object alone.
    """

    config_ini_section = "alembic"

    def __init__(
        self,
        *,
        ini_path: str | None = None,
        options: dict[str, str] | None = None,
        x_args: dict[str, str] | None = None,
    ) -> None:
        self.config_file_name = ini_path
        self._options = dict(options or {})
        self._x_args = dict(x_args or {})

    def get_main_option(self, name: str, default: str | None = None) -> str | None:
        return self._options.get(name, default)

    def get_section_option(
        self, section: str, name: str, default: str | None = None
    ) -> str | None:
        return self._options.get(name, default)

    def set_main_option(self, name: str, value: str) -> None:
        self._options[name] = value

    def get_x_argument(self, as_dictionary: bool = False):
        return dict(self._x_args) if as_dictionary else list(self._x_args)


def _ini_file(tmp_path: Path, url: str | None = _INI_VALUE) -> str:
    path = tmp_path / "alembic.ini"
    body = "[alembic]\nscript_location = alembic\n"
    if url is not None:
        body += f"sqlalchemy.url = {url}\n"
    path.write_text(body, encoding="utf-8")
    return str(path)


# --- The default path is unchanged -----------------------------------------


def test_a_caller_who_names_nothing_gets_the_ambient_default(tmp_path):
    """The overwhelmingly common invocation must behave exactly as before."""

    config = FakeConfig(
        ini_path=_ini_file(tmp_path), options={"sqlalchemy.url": _INI_VALUE}
    )
    target = resolve_migration_target(config, _AMBIENT)
    assert target.url == _AMBIENT
    assert target.source == "settings"
    assert target.is_explicit is False


def test_the_ini_placeholder_is_not_mistaken_for_a_choice(tmp_path):
    """Reading a value out of the ini is not the same as choosing it."""

    config = FakeConfig(
        ini_path=_ini_file(tmp_path), options={"sqlalchemy.url": _INI_VALUE}
    )
    assert explicit_url(config) is None


def test_surrounding_whitespace_in_the_ini_is_not_a_choice(tmp_path):
    """A value that differs only in spacing is still the file's own value."""

    config = FakeConfig(
        ini_path=_ini_file(tmp_path), options={"sqlalchemy.url": f"  {_INI_VALUE}  "}
    )
    assert explicit_url(config) is None


def test_an_empty_url_is_absence_not_an_instruction(tmp_path):
    config = FakeConfig(ini_path=_ini_file(tmp_path), options={"sqlalchemy.url": "   "})
    assert explicit_url(config) is None
    assert resolve_migration_target(config, _AMBIENT).url == _AMBIENT


# --- An explicit instruction is never discarded -----------------------------


def test_a_programmatically_set_url_beats_the_ambient_default(tmp_path):
    """The exact route that was silently ignored, and the reason this exists."""

    config = FakeConfig(ini_path=_ini_file(tmp_path))
    config.set_main_option("sqlalchemy.url", _NAMED)

    target = resolve_migration_target(config, _AMBIENT)

    assert target.url == _NAMED
    assert target.url != _AMBIENT
    assert target.is_explicit is True


def test_an_x_argument_beats_the_ambient_default(tmp_path):
    config = FakeConfig(
        ini_path=_ini_file(tmp_path),
        options={"sqlalchemy.url": _INI_VALUE},
        x_args={DB_URL_X_ARG: _NAMED},
    )
    target = resolve_migration_target(config, _AMBIENT)
    assert target.url == _NAMED
    assert target.is_explicit is True


def test_an_x_argument_beats_a_programmatically_set_url(tmp_path):
    """Per-invocation intent is the most recent statement of what is wanted."""

    config = FakeConfig(
        ini_path=_ini_file(tmp_path),
        options={"sqlalchemy.url": _NAMED},
        x_args={DB_URL_X_ARG: "postgresql+psycopg://x:y@x-host:5432/x_db"},
    )
    assert resolve_migration_target(config, _AMBIENT).url.endswith("/x_db")


def test_a_config_with_no_ini_file_still_honours_a_supplied_url():
    """With no file to have come from, a value can only have been chosen."""

    config = FakeConfig(ini_path=None, options={"sqlalchemy.url": _NAMED})
    assert resolve_migration_target(config, _AMBIENT).url == _NAMED


def test_an_unreadable_ini_does_not_turn_a_choice_into_the_default(tmp_path):
    """A missing file tells us nothing about intent, and must not overrule it."""

    config = FakeConfig(
        ini_path=str(tmp_path / "absent.ini"), options={"sqlalchemy.url": _NAMED}
    )
    assert url_in_ini_file(config) is None
    assert resolve_migration_target(config, _AMBIENT).url == _NAMED


def test_an_ini_without_the_option_leaves_a_supplied_url_standing(tmp_path):
    config = FakeConfig(
        ini_path=_ini_file(tmp_path, url=None), options={"sqlalchemy.url": _NAMED}
    )
    assert url_in_ini_file(config) is None
    assert resolve_migration_target(config, _AMBIENT).url == _NAMED


def test_the_resolved_target_is_written_back_so_the_rest_of_alembic_sees_it(tmp_path):
    """Offline mode reads `sqlalchemy.url`; online mode builds an engine from it."""

    config = FakeConfig(ini_path=_ini_file(tmp_path))
    config.set_main_option("sqlalchemy.url", _NAMED)

    apply_migration_target(config, _AMBIENT)

    assert config.get_main_option("sqlalchemy.url") == _NAMED


def test_applying_the_ambient_default_writes_it_back_too(tmp_path):
    config = FakeConfig(
        ini_path=_ini_file(tmp_path), options={"sqlalchemy.url": _INI_VALUE}
    )
    apply_migration_target(config, _AMBIENT)
    assert config.get_main_option("sqlalchemy.url") == _AMBIENT


def test_no_target_at_all_is_an_error_rather_than_a_guess(tmp_path):
    """Substituting a plausible database is the original defect, reversed."""

    config = FakeConfig(
        ini_path=_ini_file(tmp_path), options={"sqlalchemy.url": _INI_VALUE}
    )
    with pytest.raises(ValueError):
        resolve_migration_target(config, "")


# --- The run says where it is going -----------------------------------------


def test_the_target_is_reported_without_its_password():
    target = MigrationTarget(url=_NAMED, source="settings")
    assert "named_pw" not in target.redacted


def test_redaction_keeps_what_an_operator_needs_to_spot_a_wrong_target():
    """Host and database name are the whole point of logging the target."""

    redacted = redact_url(_NAMED)
    assert "named-host" in redacted
    assert "named_db" in redacted
    assert "named_pw" not in redacted


def test_a_url_without_a_password_is_left_alone():
    plain = "postgresql+psycopg://localhost:5432/plain_db"
    assert redact_url(plain) == plain


def test_an_unparseable_url_does_not_raise_from_redaction():
    assert isinstance(redact_url("postgresql://[unbalanced"), str)


# --- The wiring: env.py must ask, not decide --------------------------------


def _env_module() -> ast.Module:
    return ast.parse(_ENV_PY.read_text(encoding="utf-8"))


def _calls_named(tree: ast.AST, attribute: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


def test_env_py_does_not_set_the_url_itself():
    """The regression guard: an unconditional override reappearing here.

    `set_main_option("sqlalchemy.url", ...)` in env.py is exactly the shape of
    the bug — it runs after the caller has spoken and overwrites what they said.
    Setting the URL is the resolver's job precisely because the resolver looks
    first.
    """

    offenders = [
        call
        for call in _calls_named(_env_module(), "set_main_option")
        if call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "sqlalchemy.url"
    ]
    assert offenders == [], (
        "alembic/env.py sets sqlalchemy.url directly. That overwrites any target "
        "the caller named and silently sends the run to the ambient default. "
        "Use apply_migration_target instead."
    )


def test_env_py_resolves_its_target_through_the_shared_decision():
    """A resolver nothing calls is the failure this project keeps repeating."""

    called = {
        node.func.id
        for node in ast.walk(_env_module())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "apply_migration_target" in called


def test_env_py_does_not_pass_the_settings_url_straight_into_the_config():
    """Settings supply a default; they must not supply the decision."""

    tree = _env_module()
    for call in _calls_named(tree, "set_main_option"):
        for argument in call.args:
            assert not isinstance(argument, ast.Attribute) or (
                argument.attr != "alembic_database_url"
            )
