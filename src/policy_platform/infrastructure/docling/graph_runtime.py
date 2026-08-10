"""Runtime configuration for Docling Graph dense extraction.

The integration directive forbids changing the copied package's code, but
explicitly permits configuring it through its documented parameters and
environment variables. This module is the whole of that surface: it translates
the platform's own settings into a Docling Graph configuration and nothing else
in the codebase constructs one.

WHY THE MODEL CONFIGURATION IS SHARED, NOT DUPLICATED
-----------------------------------------------------
Dense extraction routes through LiteLLM, which can talk to any provider. It
would be easy to give it its own endpoint and key. That is precisely what this
avoids: two model configurations drift, and the resulting failure is a run
extracted by a different model than the one the platform believes it validated.
The Azure OpenAI deployment already configured for the platform is therefore the
only model source, and `docling_graph_model` names it in LiteLLM's `azure/<dep>`
form.

Dense extraction does not embed anything, so it deliberately does not require
the embedding deployment that `Settings.ai_enabled` insists on.
"""
from __future__ import annotations

from dataclasses import dataclass

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.contracts.graph_run import GraphRunConfig
from policy_platform.contracts.policy_document_graph import (
    TEMPLATE_VERSION,
    PolicyDocumentGraphV1,
)
from policy_platform.infrastructure.settings import Settings, get_settings


class GraphExtractionDisabled(RuntimeError):
    """Raised when dense extraction is requested but not configured.

    A distinct type, rather than a generic error, because "the feature is off"
    and "the model call failed" need different handling: the first is a
    configuration answer for an operator, the second is a run failure.
    """


@dataclass(frozen=True)
class DoclingGraphRuntime:
    """Everything needed to invoke Docling Graph, resolved from settings."""

    model: str
    api_base: str
    api_version: str
    #: Never logged or persisted. Present only to be handed to the client.
    api_key: str
    run_config: GraphRunConfig

    def pipeline_config(self, source: str) -> dict:
        """Build the ``PipelineConfig`` mapping for one source file.

        Only documented public options are set. Where the platform needs
        behaviour the package does not expose, that is solved in a project-owned
        adapter or recorded as a limitation — never by patching the package.
        """

        return {
            "source": source,
            "template": PolicyDocumentGraphV1,
            "backend": "llm",
            "inference": "remote",
            "processing_mode": self.run_config.processing_mode,
            "extraction_contract": self.run_config.extraction_contract,
            "use_chunking": self.run_config.use_chunking,
            "provenance": self.run_config.provenance,
            "dense_dedupe": self.run_config.dense_dedupe,
            "parallel_workers": self.run_config.parallel_workers,
            "dense_fill_nodes_cap": self.run_config.dense_fill_nodes_cap,
            "model_override": self.model,
        }


def build_runtime(settings: Settings | None = None) -> DoclingGraphRuntime:
    """Resolve the extraction runtime, or explain precisely why it is unavailable.

    The error names the missing setting. An operator debugging a disabled
    feature should not have to read this module to find out which value is
    absent.
    """

    settings = settings or get_settings()

    if not settings.docling_graph_enabled:
        raise GraphExtractionDisabled(
            "docling graph extraction is disabled; set DOCLING_GRAPH_ENABLED=true"
        )

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
        )
        if not value
    ]
    if missing:
        raise GraphExtractionDisabled(
            "docling graph extraction is enabled but unconfigured; missing: "
            + ", ".join(missing)
        )

    assert settings.azure_openai_endpoint and settings.azure_openai_api_key

    run_config = GraphRunConfig(
        template_name=TEMPLATE_VERSION,
        template_schema_hash=template_schema_hash(),
        model_provider="azure_openai",
        model_deployment=settings.azure_openai_deployment,
        docling_version=_version("docling"),
        docling_graph_version=_version("docling-graph"),
    )

    return DoclingGraphRuntime(
        model=settings.graph_extraction_model,
        api_base=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        api_key=settings.azure_openai_api_key,
        run_config=run_config,
    )


def template_schema_hash() -> str:
    """Stable hash of the extraction template's JSON schema.

    Recorded on every run so a change to the template is visible as a hash
    change rather than as unexplained drift in what gets extracted.
    """

    return canonical_hash(PolicyDocumentGraphV1.model_json_schema())


def _version(distribution: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None
