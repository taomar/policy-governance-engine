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
| [The running path](running-path.md) | What this build actually executes, step by step, named by symbol |
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

## Failure reports

Written after the fact, from the running system. These are records of what went
wrong and why, not descriptions of how the platform works now — read them for
the reasoning, and read the pages above for current behaviour.

| Report | What it covers |
|---|---|
| [Index and current state](failures/README.md) | The corpus figures, and the two numbers that look contradictory and are both true |
| [Designed pipeline and running pipeline](failures/designed-pipeline-and-running-pipeline.md) | Nine designed extraction stages, two reached, and why ten dead subsystems are one fact |
| [Validators that could not fail](failures/validators-that-could-not-fail.md) | Four checks that shipped reporting success while structurally unable to report anything else |
| [Duplicate detection](failures/duplicate-detection.md) | Three attempts at one check; the first merged two real rules, the second hid two real duplicates |
| [Display overclaims](failures/display-overclaims.md) | Where the interface stated something the data did not |
| [Execution and linkage](failures/execution-and-linkage.md) | Which linkage and evaluation blockers are fixable here and which need a customer's data model |
