"""Tests for Docling Graph runtime configuration.

Two things matter here. The feature must fail *closed* and say why — a disabled
feature that raises a generic error costs an operator an afternoon. And it must
share the platform's single model configuration, because two configurations
drift and the resulting failure is a run extracted by a different model than the
one that was validated.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.policy_document_graph import TEMPLATE_VERSION
from policy_platform.infrastructure.docling.graph_runtime import (
    GraphExtractionDisabled,
    build_runtime,
    template_schema_hash,
)
from policy_platform.infrastructure.settings import Settings


def _settings(**overrides) -> Settings:
    base = {
        "database_url": "postgresql+asyncpg://u:p@localhost:5433/db",
        "alembic_database_url": "postgresql+psycopg://u:p@localhost:5433/db",
        "docling_graph_enabled": True,
        # Set explicitly rather than left to the environment: these tests pin
        # derivation behaviour, and a developer's own .env must not change the
        # verdict.
        "docling_graph_model": "",
        "azure_openai_endpoint": "https://foundryfordevtarek.cognitiveservices.azure.com/",
        "azure_openai_api_key": "test-key",
        "azure_openai_deployment": "gpt-4o",
    }
    base.update(overrides)
    return Settings(**base)


class TestFailsClosed:
    def test_disabled_by_default(self) -> None:
        settings = _settings(docling_graph_enabled=False)
        with pytest.raises(GraphExtractionDisabled, match="DOCLING_GRAPH_ENABLED"):
            build_runtime(settings)

    @pytest.mark.parametrize(
        ("field", "variable"),
        [
            ("azure_openai_endpoint", "AZURE_OPENAI_ENDPOINT"),
            ("azure_openai_api_key", "AZURE_OPENAI_API_KEY"),
            ("azure_openai_deployment", "AZURE_OPENAI_DEPLOYMENT"),
        ],
    )
    def test_missing_setting_is_named_in_the_error(self, field: str, variable: str) -> None:
        """An operator should not have to read the source to find the gap."""

        with pytest.raises(GraphExtractionDisabled, match=variable):
            build_runtime(_settings(**{field: None}))

    def test_every_missing_setting_is_reported_at_once(self) -> None:
        with pytest.raises(GraphExtractionDisabled) as exc:
            build_runtime(_settings(azure_openai_api_key=None, azure_openai_deployment=None))

        assert "AZURE_OPENAI_API_KEY" in str(exc.value)
        assert "AZURE_OPENAI_DEPLOYMENT" in str(exc.value)

    def test_disabled_is_a_distinct_type_from_a_run_failure(self) -> None:
        """Configuration answers and run failures need different handling."""

        assert issubclass(GraphExtractionDisabled, RuntimeError)


class TestSharedModelConfiguration:
    def test_runtime_uses_the_platform_azure_endpoint(self) -> None:
        runtime = build_runtime(_settings())
        assert runtime.api_base == "https://foundryfordevtarek.cognitiveservices.azure.com/"
        assert runtime.run_config.model_provider == "azure_openai"
        assert runtime.run_config.model_deployment == "gpt-4o"

    def test_model_is_derived_from_the_configured_deployment(self) -> None:
        """Not a literal default: a hardcoded model would keep pointing at one
        deployment after the platform's own was changed."""

        assert build_runtime(_settings(docling_graph_model="")).model == "azure/gpt-4o"

    def test_changing_the_deployment_moves_extraction_with_it(self) -> None:
        runtime = build_runtime(
            _settings(azure_openai_deployment="gpt-5.6-sol", docling_graph_model="")
        )
        assert runtime.model == "azure/gpt-5.6-sol"

    def test_an_explicit_override_wins(self) -> None:
        """Routing extraction at a different model must still be possible."""

        runtime = build_runtime(_settings(docling_graph_model="azure/other-deployment"))
        assert runtime.model == "azure/other-deployment"

    def test_embedding_deployment_is_not_required(self) -> None:
        """Dense extraction embeds nothing; requiring it would disable the
        feature in an environment perfectly able to run it."""

        settings = _settings(azure_openai_embedding_deployment=None)
        assert not settings.ai_enabled
        assert settings.graph_extraction_enabled
        assert build_runtime(settings).model


class TestPipelineConfig:
    def test_conservative_defaults_are_passed_through(self) -> None:
        config = build_runtime(_settings()).pipeline_config("policy.docx")

        assert config["extraction_contract"] == "dense"
        assert config["processing_mode"] == "many-to-one"
        assert config["provenance"] == "detailed"
        assert config["dense_dedupe"] == "off"
        assert config["parallel_workers"] == 1
        assert config["use_chunking"] is True

    def test_repository_owned_template_is_supplied(self) -> None:
        from policy_platform.contracts.policy_document_graph import PolicyDocumentGraphV1

        config = build_runtime(_settings()).pipeline_config("policy.docx")
        assert config["template"] is PolicyDocumentGraphV1

    def test_source_is_carried_through(self) -> None:
        config = build_runtime(_settings()).pipeline_config("samples/policy.docx")
        assert config["source"] == "samples/policy.docx"

    def test_api_key_is_not_placed_in_the_pipeline_config(self) -> None:
        """The config is loggable and persistable; the key must not ride in it."""

        config = build_runtime(_settings()).pipeline_config("policy.docx")
        assert "test-key" not in str(config)


class TestProvenanceRecording:
    def test_template_identity_is_recorded_on_the_run(self) -> None:
        run_config = build_runtime(_settings()).run_config
        assert run_config.template_name == TEMPLATE_VERSION
        assert run_config.template_schema_hash == template_schema_hash()

    def test_schema_hash_is_stable_across_calls(self) -> None:
        assert template_schema_hash() == template_schema_hash()

    def test_schema_hash_changes_when_the_template_changes(self) -> None:
        """A template change must be visible as a hash change, not as drift."""

        from policy_platform.contracts.canonical import canonical_hash
        from policy_platform.contracts.policy_document_graph import PolicyDocumentGraphV1

        schema = PolicyDocumentGraphV1.model_json_schema()
        mutated = dict(schema)
        mutated["title"] = "Something Else"

        assert canonical_hash(mutated) != template_schema_hash()
