"""Application settings loaded from environment (.env) — Section 5/Section 23.

Single source of truth for configuration; no component should read
`os.environ` directly outside this module.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "policy_platform"
    postgres_user: str = "policy_admin"
    postgres_password: str = "policy_admin_pw"

    database_url: str
    alembic_database_url: str

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    dev_auth_enabled: bool = True

    web_dev_server_port: int = 5173
    vite_api_base_url: str = "http://localhost:8000"
    #: Comma-separated browser origins allowed to call the API. Empty means
    #: "derive them", which is the developer-friendly default.
    #:
    #: Previously the allowlist was a hardcoded port range inside the app
    #: factory, so running the UI on any other port meant editing application
    #: code — and the resulting failure is a silent CORS block in the browser
    #: rather than a server-side error anyone would see in a log.
    cors_allowed_origins: str = ""
    #: Ports probed when `cors_allowed_origins` is empty. Vite increments its
    #: port when the preferred one is taken, so a single port is not enough to
    #: make `npm run dev` reliably work out of the box.
    cors_dev_port_range: str = "5173-5180"

    # Azure OpenAI (chat/extraction/rewrite/quality + embeddings). All
    # optional so the app still boots with AI features disabled if unset.
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployment: str | None = None
    azure_openai_fast_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_embedding_model: str | None = None
    azure_openai_embedding_dimensions: int = 3072

    # Azure AI Search (clause-level RAG grounding for chat/extraction/quality).
    azure_search_endpoint: str | None = None
    azure_search_api_key: str | None = None
    azure_search_api_version: str = "2025-09-01"
    azure_search_authoring_index: str = "policy-authoring"
    azure_search_evidence_index: str = "policy-evidence"

    # Which parser turns an uploaded file into a canonical document at upload
    # time. This is a DIFFERENT concern from `docling_graph_enabled` below,
    # which selects a model-driven dense-extraction backend; the two must not
    # be conflated or share a flag. This one chooses a deterministic converter.
    #
    #   "legacy"  — `ingestion.document_ingestion.ingest_document`. Emits one
    #               element per table *row*, pipe-joining the cells, so a cell's
    #               column header is lost before any downstream stage sees it.
    #   "docling" — `docling.converter.convert_document`. Emits one element per
    #               table *cell* carrying row/column index and header identity,
    #               which is what `structural_graph` needs to build `header_for`
    #               / `table_cell_of` / `merged_with` edges and what
    #               `reading_plan._add_table_context` needs to tell the model
    #               which column a value like "15 minutes" sits under.
    #
    # Defaults to "legacy" — the behaviour in production today. The conformance
    # map (docs/specs/docling-integration-conformance-map.md) calls for Docling
    # to become primary, but that flip is a deliberate, evidence-backed decision
    # and not something this setting's default should make on anyone's behalf.
    #
    # Typed as a Literal so an unrecognised value fails loudly at startup.
    # Coercing an unknown value to "legacy" would silently downgrade a
    # structured parse to a flattened one, which is precisely the class of
    # defect this setting exists to fix.
    document_converter: Literal["legacy", "docling"] = "legacy"

    # Docling Graph dense extraction. Off by default: the dependency is an
    # optional extra (`pip install -e .[graph]`), and importing it in a runtime
    # that lacks it must fail as "disabled", not as a crash.
    docling_graph_enabled: bool = False
    #: LiteLLM model identifier. Left empty by default so it is *derived* from
    #: `azure_openai_deployment` rather than hardcoded: a literal default would
    #: keep pointing at one deployment after the platform's own was changed,
    #: which is exactly the silent drift the shared-configuration rule exists to
    #: prevent. Set it explicitly only to route extraction at a different model
    #: on purpose.
    docling_graph_model: str = ""

    @property
    def ai_enabled(self) -> bool:
        """True only when both Azure OpenAI chat and embeddings are configured."""

        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_deployment
            and self.azure_openai_embedding_deployment
        )

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins permitted to call the API.

        An explicit `CORS_ALLOWED_ORIGINS` wins outright: an operator who names
        origins means those and no others, and quietly unioning them with a
        development range would widen production beyond what was asked for.

        With nothing set, the configured UI port and the Vite fallback range are
        allowed on both `localhost` and `127.0.0.1`. Both hostnames are needed
        because they are different origins to a browser, and which one a
        developer types is not predictable.
        """

        explicit = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        explicit = [origin for origin in explicit if origin]
        if explicit:
            return explicit

        ports = {self.web_dev_server_port, *self._dev_port_range()}
        return [f"http://localhost:{port}" for port in sorted(ports)] + [
            f"http://127.0.0.1:{port}" for port in sorted(ports)
        ]

    def _dev_port_range(self) -> range:
        """Parse `cors_dev_port_range`, falling back rather than failing to boot.

        A malformed range is a configuration typo. Refusing to start over it
        would turn a cosmetic mistake into an outage, so the documented default
        is used instead.
        """

        try:
            low, _, high = self.cors_dev_port_range.partition("-")
            return range(int(low), int(high) + 1)
        except (TypeError, ValueError):
            return range(5173, 5181)

    @property
    def search_enabled(self) -> bool:
        return bool(self.azure_search_endpoint and self.azure_search_api_key)

    @property
    def graph_extraction_model(self) -> str:
        """LiteLLM identifier for dense extraction.

        Derived from the platform's own chat deployment unless overridden, so
        changing the deployment moves extraction with it. Two independently
        configured models drift, and the resulting failure is a run extracted by
        a different model than the one that was validated.
        """

        if self.docling_graph_model:
            return self.docling_graph_model
        return f"azure/{self.azure_openai_deployment}" if self.azure_openai_deployment else ""

    @property
    def graph_extraction_enabled(self) -> bool:
        """True when dense extraction can actually run.

        Deliberately requires a chat endpoint, key and deployment but *not* an
        embedding deployment: dense extraction never embeds anything, and
        gating it on `ai_enabled` would make it unavailable in an environment
        that is perfectly capable of running it.
        """

        return bool(
            self.docling_graph_enabled
            and self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_deployment
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
