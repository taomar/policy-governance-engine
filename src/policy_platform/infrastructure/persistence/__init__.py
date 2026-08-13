"""Reading and writing the database, and the mapping either side of it.

Everything here is on the path between a SQLAlchemy row and a contract object:
the async engine and session, the repositories that query, the mappers that
rebuild a `CanonicalRule` from stored columns, and the two writers that put
approved versions and audit events on the record.

Grouped because these six modules were previously spread through a flat
directory of forty-four, where nothing distinguished the code that touches the
database from the code that calls a model. `docs/architecture.md` already
described them as one concern -- "persistence access", listing repositories,
mappers and db together -- so this makes the layout agree with the description
rather than proposing a new one.

`mappers` reaches into the extraction and projection modules to derive the
views a published rule carries. That direction is deliberate: a stored row is
not a served record until those derivations run, and running them on read is
what keeps a published rule and a candidate describing the same thing.
"""
from __future__ import annotations
