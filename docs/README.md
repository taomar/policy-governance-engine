# Documentation

Documentation for the Policy Platform — a local-first system that turns policy
documents into deterministic, machine-evaluable rules.

New here? Read the [root README](../README.md) first, then
[Architecture](architecture.md). For a specific feature, go straight to
[Capability flows](capability-flows.md).

## Core pages

| Page | What it covers |
|---|---|
| [User guide](user-guide.md) | Illustrated walkthrough of the dashboard, HR and Saudi Labor Law projects, document intake, review, publication, quality, tests, evaluation, and grounded Ask AI. |
| [Architecture](architecture.md) | Runtime components, boundaries, how they are invoked, and where the deterministic/probabilistic line sits. |
| [Capability flows](capability-flows.md) | A concise set of high-impact Mermaid diagrams for document control, evidence, evaluation, tests, quality, grounding, and outputs. |
| [Azure deployment](azure-deployment.md) | Recommended Container Apps architecture, lower Standard SKUs, VNet/private connectivity, parameters and future `azd up` sequence. |
| [Azure deployment variants](azure-deployment-variants.md) | App Service, hardened-private and Foundry IQ alternatives and their trade-offs. |
| [Azure prerequisites](azure-prerequisites.md) | Required tools, permissions, providers, quotas, Entra registration, models and address ranges. |
| [Azure operations](azure-operations.md) | Fresh schema/index initialization, health, scaling, backup, rotation and rollback. |
| [Testing and scripts](testing.md) | The active pytest process, capability groups it protects, invocation commands, expected behavior, and coverage gaps. |
| [Workflows](workflows.md) | UI navigation and the main flows: ingestion, extraction, review, publish, evaluate, quality, correlation, tests. |
| [Frameworks & technologies](frameworks.md) | Every framework the code actually uses, where it is configured, how it is invoked, why it fits — and what is deferred or explicitly not used. |
| [Microsoft technologies](microsoft-technologies.md) | Azure OpenAI, Azure AI Search, Foundry IQ as an architectural alternative, responsible-AI and reliability patterns, with Microsoft first-party references and an honest implemented / aligned / deferred label on each. |
| [AI assistance](ai-assistance.md) | The actual AI/LLM components, prompts, [grounding](ai-assistance.md#how-the-ai-is-grounded) and quality checks. Azure OpenAI and a grounding/search layer are required, not optional. |
| [API](api.md) | Endpoint groups, interactive docs (`/docs`), and common call sequences. |
| [Data model](data-model.md) | Tables, relationships and immutability invariants. |
| [Configuration & operations](configuration.md) | Environment variables, setup/run/test commands, security status, observability, extension points. |
| [Known limitations](known-limitations.md) | The honest register of what is not implemented and the standards-gap backlog. |

## Additional public reference material

These pages provide optional depth beyond the core documentation:

- **[Specs](specs/)** —
  [PDF ingestion architecture](specs/pdf-ingestion-architecture-v1.md) and the
  [verbatim passage extractor](specs/verbatim-passage-extractor-v1.md).
- **[Policy standards research](policy-standards-research.md)** — comparison
  against XACML, OPA, DMN, ISO 37301/27001 and NIST.
