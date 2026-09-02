# PolicyVerbAItim documentation

*AI to read. Evidence to prove. Determinism to decide.*

This index is for public readers, reviewers, operators and contributors finding the right published page without opening local-only working notes. Start with the [User guide](user-guide.md) to see the product, or [How we work](how-we-work.md) to contribute to it.

## Core

| Page | Purpose |
|---|---|
| [User guide](user-guide.md) | End-to-end journey with screenshots |
| [From document to policy](from-document-to-policy.md) | How extraction produces reviewable policy and checks itself |
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
| [External consumption](external-consumption.md) | Calling the audited decision API from another system |
| [Integration guide](integration-guide.md) | Endpoints, request and response shapes, and how to verify an integration |
| [Configuration](configuration.md) | Local setup and troubleshooting |
| [Testing](testing.md) | Commands, fixtures, and coverage |
| [Measured performance](measured-performance.md) | Observed latency and tokens, the method that produced them, and which deployment to use |
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

## Technical reference

| Page | Purpose |
|---|---|
| [Frameworks](frameworks.md) | Technologies actually used |
| [Microsoft services](microsoft-technologies.md) | Implemented and planned Microsoft services |
| [Standards research](policy-standards-research.md) | Full standards survey, including what was evaluated and rejected |

## Ingestion specifications

| Page | Purpose |
|---|---|
| [PDF ingestion architecture](specs/pdf-ingestion-architecture-v1.md) | Original ingestion and extraction architecture instruction, with current status |
| [Docling integration runbook](specs/docling-integration-runbook.md) | How to enable, run, verify, and roll back the Docling path |
| [Docling operating notes](specs/docling-integration-operating-notes.md) | Observed dependency and conversion behavior |
| [Docling conformance map](specs/docling-integration-conformance-map.md) | Repository areas preserved, adapted, replaced, or missing for Docling |
| [Docling handoff](specs/docling-integration-handoff.md) | Completed integration deliverables and verification notes |
| [Docling corpus report](specs/docling-corpus-report.md) | Sample-corpus conversion results |
| [Docling shadow comparison](specs/docling-shadow-comparison-report.md) | Legacy versus Docling comparison summary |

## Kept on the workstation

Some pages are deliberately not published. They live together under `docs/internal/` — decision records in `docs/internal/adr/`, failure analyses and drift reports in `docs/internal/audits/`, and designs that have been decided but not built in `docs/internal/planning/`. They are written for whoever is doing the work, and they describe how the product went wrong or what it is not yet, which is not what a reader should have to sift through to learn how it behaves today.

The unpublished set includes the **security roadmap**: the itemised list of authentication and authorization work still outstanding. What that roadmap concludes is stated plainly in the repository README and in [Known limitations](known-limitations.md) — access control exists, but ships off by default and must be configured before the build is exposed beyond a trusted environment. The itemised gap list is kept local because a public checklist of specific unclosed gaps is an invitation rather than a disclosure, and the honest summary is published without it.

What the product **is** lives in the pages above; what it does **not** do is in [Known limitations](known-limitations.md), which is published and guarded.

See "What stays on the workstation" in [How we work](how-we-work.md) for the convention and the paths it covers.
