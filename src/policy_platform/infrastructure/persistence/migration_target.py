"""Decide which database a migration run is aimed at, and say so out loud.

WHY THIS EXISTS
---------------
`alembic/env.py` used to set the target unconditionally::

    config.set_main_option("sqlalchemy.url", get_settings().alembic_database_url)

which meant the documented, obvious way to point a programmatic migration
somewhere else -- calling ``Config.set_main_option("sqlalchemy.url", ...)``
before ``command.upgrade`` -- was read, overwritten and discarded without a
word. A caller who asked for a scratch database got the ambient default
instead, and the ambient default is production. That is not a hypothetical:
it happened here, during work whose whole purpose was to *avoid* touching the
live database. The migration in question was additive and nothing was lost,
but the same trap in front of ``downgrade`` destroys columns.

Two properties follow, and both are the point of this module:

* **An explicit instruction is never silently discarded.** If a caller named a
  target, that target is used. If for any reason it cannot be, that is an
  error, not a fallback -- silently substituting a different database is the
  exact failure this replaces.
* **The default path is unchanged.** A caller who names nothing still gets
  ``alembic_database_url`` from settings, which is what every existing
  invocation relies on.

WHY THE ON-DISK COMPARISON
--------------------------
Alembic offers no way to ask "was this option set programmatically?".
``Config.set_main_option`` mutates the same parsed ``ConfigParser`` the ini
file populated, so after the fact a caller's URL and the ini's own URL are
indistinguishable. Reading the ini back off disk is the only honest way to
tell "the caller chose this" from "the file has always said this". It reads a
file the run has already read; it invents nothing.

NOT A SECRET STORE
------------------
The resolved target is logged on every run, with credentials removed. An
operator running ``downgrade`` against the wrong database should be able to
see that from the output rather than from the wreckage.
"""
from __future__ import annotations

import configparser
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

#: How a target was chosen. Recorded rather than inferred, because "why is this
#: run pointed here" is the first question after a migration goes somewhere
#: unexpected.
UrlSource = str

#: The ``-x`` key a caller uses to name a target for one invocation, e.g.
#: ``alembic -x db_url=postgresql+psycopg://... upgrade head``. Offered because
#: it is the one channel Alembic already treats as per-invocation intent.
DB_URL_X_ARG = "db_url"

_URL_OPTION = "sqlalchemy.url"


class _ConfigLike(Protocol):
    """The slice of ``alembic.config.Config`` this module uses.

    Narrowed to a protocol so the resolution can be tested without constructing
    an Alembic environment -- a test that has to stand up the real thing to
    check a decision tends not to get written.
    """

    config_file_name: str | None
    config_ini_section: str

    def get_main_option(self, name: str, default: str | None = None) -> str | None: ...

    def set_main_option(self, name: str, value: str) -> None: ...

    def get_x_argument(self, as_dictionary: bool = False): ...


@dataclass(frozen=True)
class MigrationTarget:
    """The database a migration run will touch, and how that was decided."""

    url: str
    source: UrlSource

    @property
    def is_explicit(self) -> bool:
        """True when a caller named this target rather than inheriting it."""

        return self.source != "settings"

    @property
    def redacted(self) -> str:
        return redact_url(self.url)


def redact_url(url: str) -> str:
    """Return `url` with any password replaced, for logs and error messages.

    Everything else is preserved -- host, port and database name are precisely
    what an operator needs in order to notice that a run is aimed somewhere
    unintended, and removing them to be safe would defeat the purpose of
    logging the target at all.
    """

    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.password:
        return url
    userinfo = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{userinfo}:***@{host}{port}" if userinfo else f"{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def url_in_ini_file(config: _ConfigLike) -> str | None:
    """What the ini file on disk says the URL is, ignoring in-memory edits.

    Returns None when there is no ini file, no such section, or no such option
    -- all of which mean the same thing for this purpose: the file is not the
    source of whatever the config currently holds.
    """

    path = config.config_file_name
    if not path:
        return None
    parser = configparser.ConfigParser()
    try:
        if not parser.read(path, encoding="utf-8"):
            return None
        return parser.get(config.config_ini_section, _URL_OPTION, raw=True)
    except (OSError, UnicodeDecodeError, configparser.Error):
        # An unreadable or malformed ini tells us nothing about caller intent.
        # It must not be reported as "the caller chose this", and it must not
        # crash a run that would otherwise resolve fine from settings.
        return None


def explicit_url(config: _ConfigLike) -> MigrationTarget | None:
    """The target the caller asked for, or None if they expressed no preference.

    Two channels count as explicit, because both are things a caller does on
    purpose for one invocation:

    * ``-x db_url=...``, which Alembic already models as per-run arguments;
    * ``sqlalchemy.url`` holding something other than what the ini file holds
      on disk, which is precisely the state ``set_main_option`` leaves behind.

    An empty or whitespace-only value is not a preference. It is treated as
    absent rather than as an instruction to connect to nothing.
    """

    try:
        x_args = config.get_x_argument(as_dictionary=True) or {}
    except Exception:  # noqa: BLE001 - a config without -x support is not an error
        x_args = {}
    from_x = (x_args.get(DB_URL_X_ARG) or "").strip()
    if from_x:
        return MigrationTarget(url=from_x, source=f"-x {DB_URL_X_ARG}")

    current = (config.get_main_option(_URL_OPTION, None) or "").strip()
    if not current:
        return None
    on_disk = url_in_ini_file(config)
    if on_disk is not None and current == on_disk.strip():
        # Identical to the file: nobody chose it, it was simply read.
        return None
    # Either it differs from the file, or there is no file to have come from.
    # Both mean a caller put it there. Treating that as ambient is the bug.
    return MigrationTarget(url=current, source="sqlalchemy.url (set by caller)")


def resolve_migration_target(config: _ConfigLike, ambient_url: str) -> MigrationTarget:
    """Decide the target, preferring anything the caller named.

    `ambient_url` is the environment's default -- in practice
    ``get_settings().alembic_database_url``. It is passed in rather than read
    here so this decision can be exercised without a settings environment, and
    so the caller keeps ownership of where the default comes from.

    Raises ValueError when neither an explicit target nor a usable ambient URL
    exists. Returning something plausible instead would be the original defect
    with the arrow reversed.
    """

    chosen = explicit_url(config)
    if chosen is None:
        ambient = (ambient_url or "").strip()
        if not ambient:
            raise ValueError(
                "No migration target: nothing was supplied explicitly and no "
                "ambient database URL is configured. Set ALEMBIC_DATABASE_URL, "
                f"or pass -x {DB_URL_X_ARG}=<url>."
            )
        chosen = MigrationTarget(url=ambient, source="settings")
    return chosen


def apply_migration_target(config: _ConfigLike, ambient_url: str) -> MigrationTarget:
    """Resolve the target, write it back to `config`, and log where it came from.

    The write-back is what makes the rest of Alembic -- offline mode's
    ``get_main_option`` and online mode's ``engine_from_config`` -- see the same
    decision. Logging is not decoration: a run that quietly targets the wrong
    database is only recoverable if it said which one it chose.
    """

    target = resolve_migration_target(config, ambient_url)
    config.set_main_option(_URL_OPTION, target.url)
    logger.info(
        "alembic target: %s (source: %s)", target.redacted, target.source
    )
    return target
