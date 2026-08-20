# PolicyVerbAItim documentation

*AI to read. Evidence to prove. Determinism to decide.*

Start with the [User guide](user-guide.md) to see the product, or
[How we work](how-we-work.md) to contribute to it.

## Core

| Page | Purpose |
|---|---|
| [User guide](user-guide.md) | End-to-end journey with screenshots |
| [How we work](how-we-work.md) | Engineering agreements and the reasoning behind them |
| [Standards](standards.md) | Which published standard governs which decision |
| [Architecture](architecture.md) | Components, boundaries, and trust model |
| [Extraction run coverage](extraction-run-coverage.md) | What a finished run promises, and what it does not |
| [Relationships](relationships.md) | How rules are linked, and what is deliberately not claimed |
| [Docling](docling.md) | Document conversion and graph discovery |
| [AI assistance](ai-assistance.md) | Extraction, grounding, and validation |
| [Workflows](workflows.md) | Concise operational lifecycle |
| [Capability flows](capability-flows.md) | High-impact diagrams |
| [API](api.md) | Endpoints and common sequences |
| [Configuration](configuration.md) | Local setup and troubleshooting |
| [Testing](testing.md) | Commands, fixtures, and coverage |
| [Data model](data-model.md) | Tables and invariants |
| [Known limitations](known-limitations.md) | Current product gaps |

## Deployment

| Page | Status |
|---|---|
| [Local deployment](configuration.md#deployment-status) | Available |
| [Azure deployment](azure-deployment.md) | Pending |
| [Azure prerequisites](azure-prerequisites.md) | Pending deployment checklist |
| [Azure operations](azure-operations.md) | Future runbook |
| [Deployment options](azure-deployment-options.md) | Alternative hosting/security options |
| [Security roadmap](security-roadmap.md) | Pending authentication, RBAC, and managed identity |

## Technical reference

- [Frameworks](frameworks.md) — the technologies actually used
- [Microsoft services](microsoft-technologies.md)
- [Standards research](policy-standards-research.md) — the full survey, including what was evaluated and rejected
- [Ingestion specifications](specs/) — Docling integration and PDF ingestion

## Kept on the workstation

Some pages are deliberately not published. Failure analyses, drift reports, the
step-by-step account of what this build actually executes, and designs that have
been decided but not built are written for whoever is doing the work. They
describe how the product went wrong, or what it is not yet — which is not what a
reader should have to sift through to learn how it behaves today.

What the product **is** lives in the pages above; what it does **not** do is in
[Known limitations](known-limitations.md), which is published and guarded.

See "What stays on the workstation" in [How we work](how-we-work.md) for the
convention and the paths it covers.
