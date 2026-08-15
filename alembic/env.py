import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ensure `src/` is importable when Alembic is invoked from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from policy_platform.domain import Base  # noqa: E402
from policy_platform.infrastructure.persistence.migration_target import (  # noqa: E402
    apply_migration_target,
)
from policy_platform.infrastructure.settings import get_settings  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Decide which database this run touches. Settings supply the default
# (ALEMBIC_DATABASE_URL uses the sync psycopg driver; DATABASE_URL uses async
# asyncpg for the runtime app — see docs/adr and .env.example), but a target the
# caller named explicitly wins.
#
# This used to be an unconditional `config.set_main_option("sqlalchemy.url",
# get_settings().alembic_database_url)`, which read a caller's explicitly
# supplied URL and threw it away without a word, pointing the run at the
# ambient default — production — instead. See
# `infrastructure/persistence/migration_target.py` for the full account and
# `tests/unit/test_migration_target_resolution.py` for the regression guard.
apply_migration_target(config, get_settings().alembic_database_url)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
