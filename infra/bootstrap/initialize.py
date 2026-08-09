"""Fresh Azure environment bootstrap: schema and Search indexes only.

This module deliberately does not import samples, local database rows, uploaded
files, or any backfill utility. It is safe to rerun because Alembic and Search
index PUT operations are idempotent at their respective boundaries.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SEARCH_SCHEMAS = ROOT / "infra" / "search"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required deployment setting {name} is missing")
    return value


def initialize_database_schema() -> None:
    required("ALEMBIC_DATABASE_URL")
    print("Initializing the empty PostgreSQL schema with Alembic...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
    )


def load_schema(path: Path, *, index_name: str, dimensions: int) -> dict:
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["name"] = index_name
    for field in schema["fields"]:
        if field["name"] == "body_vector":
            field["dimensions"] = dimensions
    return schema


def put_search_index(*, endpoint: str, api_key: str, api_version: str, schema: dict) -> None:
    index_name = schema["name"]
    url = f"{endpoint.rstrip('/')}/indexes/{index_name}?api-version={api_version}"
    request = Request(
        url,
        data=json.dumps(schema).encode("utf-8"),
        method="PUT",
        headers={"api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - endpoint is deployment-controlled
            if response.status not in (200, 201, 204):
                raise RuntimeError(f"Search index {index_name} returned HTTP {response.status}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Failed to initialize Azure AI Search index {index_name} "
            f"(HTTP {exc.code}): {body[:1000]}"
        ) from exc
    print(f"Azure AI Search index {index_name} is initialized.")


def initialize_search_indexes() -> None:
    endpoint = required("AZURE_SEARCH_ENDPOINT")
    api_key = required("AZURE_SEARCH_API_KEY")
    api_version = required("AZURE_SEARCH_API_VERSION")
    dimensions = int(required("AZURE_OPENAI_EMBEDDING_DIMENSIONS"))

    definitions = (
        ("policy-authoring.json", required("AZURE_SEARCH_AUTHORING_INDEX")),
        ("policy-evidence.json", required("AZURE_SEARCH_EVIDENCE_INDEX")),
    )
    for filename, index_name in definitions:
        schema = load_schema(
            SEARCH_SCHEMAS / filename,
            index_name=index_name,
            dimensions=dimensions,
        )
        put_search_index(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            schema=schema,
        )


def main() -> int:
    initialize_database_schema()
    initialize_search_indexes()
    print("Fresh environment initialization completed; no policy or document data was loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
