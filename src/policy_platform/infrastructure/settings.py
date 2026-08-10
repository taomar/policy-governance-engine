"""Application settings loaded from environment (.env) — Section 5/Section 23.

Single source of truth for configuration; no component should read
`os.environ` directly outside this module.
"""
from __future__ import annotations

from functools import lru_cache

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

    # Docling Graph dense extraction. Off by default: the dependency is an
    # optional extra (`pip install -e .[graph]`), and importing it in a runtime
    # that lacks it must fail as "disabled", not as a crash.
    docling_graph_enabled: bool = False
    #: LiteLLM model identifier. Defaults to the Azure OpenAI deployment above
    #: so the platform has one model configuration rather than a second parallel
    #: one that could silently drift to a different model.
    docling_graph_model: str = "azure/gpt-4o"

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
    def search_enabled(self) -> bool:
        return bool(self.azure_search_endpoint and self.azure_search_api_key)

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
