# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Policy Composer / Reviewer** (primary, default persona in the app's role switcher) — drafts and edits candidate rules extracted from policy documents, asks AI for grounded explanations/rewrites, checks rule quality, and submits rules for approval. Works rule-by-rule and document-by-document, often across dozens to hundreds of candidates per project.
- **Policy Manager / Approver** — approves or rejects candidate rules, can override-approve or override-reject (send back to review with feedback), and publishes new policy versions. Accountable for what goes live.
- **Auditor / compliance reviewer** (implied by the immutable publish/versioning model and recertification workflow under discussion) — needs to trace any published rule back to verbatim source text, see who approved what and when, and review exception/override history.

All three roles work inside the same local, single-tenant instance (no multi-tenant auth model yet — role is a display-only "acting as" switch, not enforced authorization).

## Product Purpose

Turn real enterprise policy documents (HR handbooks, IT/hardware provisioning policies, finance/expense approval policies, etc.) into **deterministic, machine-evaluable rules** instead of leaving policy meaning trapped in prose. Success means: a rule extracted from a document can be evaluated the same way every time against a real scenario, is always traceable back to the exact source sentence it came from, and never silently drifts from what was actually approved and published.

## Positioning

Unlike generic document-Q&A or summarization tools, this platform produces **structured, testable policy rules** — with formal effects (allow/deny/require_action), conditions, exceptions with numeric limits, precedence/override/supersession semantics, and combined aggregate caps across related rules. The "sum" of a policy can be run through an evaluation engine against a scenario and get a deterministic answer, not just a paraphrase. This is grounded in real standards (XACML/ABAC-style attribute conditions, DMN-style decision logic, SBVR-style rule semantics) rather than inventing bespoke policy semantics.

## Operating Context

- Work is organized into **Projects** (policy sets), each holding its own source documents, extracted/drafted candidate rules, approved rules, and a version history.
- Real-world policy text is often genuinely complicated: nested exceptions, escalation routes, role-based overrides (e.g., "executives may override X"), and aggregate caps across scenarios (e.g., "60 days pregnancy leave + 15 days family-sick leave, but both combined can't exceed 70 days/year"). The platform must represent this complexity explicitly, not flatten it.
- Lifecycle: source document uploaded → AI extraction drafts candidate rules (verbatim-grounded quotes) → Composer reviews/edits/asks AI → Manager approves, rejects, requests changes, or overrides → approved rules are published as an **immutable, versioned snapshot** → published rules appear read-only in the Policies tab; changing one means drafting a new candidate that explicitly supersedes it, not editing history.
- Rules are categorized by business domain (HR, Finance, IT, etc.), tagged, and grouped into "variation groups" — sets of rules that are scenario/exception/escalation variants of the same underlying topic (so related complexity stays visually together instead of scattered).
- Three real sample projects currently loaded, each from real document structure with synthetic data: Corporate Expense Approval Policy (Finance), Workplace Hardware Provisioning Policy POL-HW-001 (IT), HR Guide Policy and Procedure (HR, currently 73 published rules across 17 rule-type groups, 346 pending candidates).

## Capabilities and Constraints

- Local-first stack: Python FastAPI + SQLAlchemy async backend, PostgreSQL (non-default local port), React + TypeScript + Vite frontend (Ant Design v6 components), Azure OpenAI + Azure AI Search for AI-assisted extraction/rewrite/Q&A — AI output is always verbatim-grounded to source text, never fabricated.
- Canonical rule contract: effect, a recursively-structured condition tree (fact comparisons / all / any / not), required facts with types, exceptions (each with an optional numeric `limit_value`/`limit_unit`), scope, priority, and explicit precedence fields (`is_explicit_override`, `supersedes_rule_ids`).
- `AggregateLimit`: a combined cap that multiple rules can contribute to (e.g., a shared annual leave-day ceiling across several distinct leave-type rules).
- Published policy versions are append-only/immutable by design — this is a hard constraint, not a missing feature, and any redesign must keep that model legible rather than implying rules can be edited in place.
- No multi-tenant auth yet; single local instance.

## Brand Commitments

- Name: "PolicyVerbAItim", tagline "AI to read. Evidence to prove. Determinism to decide."
  Each clause maps to a real layer: the formulator reads, verbatim spans and
  clause anchors prove what it read, and the deterministic evaluator decides
  with no model in the path. The name carries the same guarantee — *verbatim*.
  Written plainly everywhere (docs, CLI, package, domain); the AI infix is a
  wordmark treatment, not a spelling anyone should have to reproduce by hand.
- Existing visual language: dark indigo/purple sidebar, purple (#6366f1-ish) accent color, Ant Design v6 component set, card-based layouts. Treat this as an existing but not-yet-formalized visual world — the user has explicitly called the current Policies-page presentation "ugly" and not scalable, so the incumbent detail-card treatment is evidence/anti-reference for that surface, not a constraint to preserve as-is.

## Evidence on Hand

- Three real sample projects with real source documents (PDF/template-based) layered with synthetic data, as described above. No customer testimonials, pricing, or external case studies exist or should be fabricated.

## Product Principles

1. **Determinism and auditability over cleverness** — every rule must be traceable to verbatim source text and evaluate identically every time.
2. **Immutable publish history** — published rule versions are never edited in place, only superseded by a new reviewed/approved version.
3. **Human-in-the-loop AI** — AI drafts and suggests; a human Composer and Manager always review, approve, or override. Never auto-publish.
4. **Ground in real standards** — align policy semantics to established models (XACML/ABAC/DMN/SBVR-style thinking) instead of inventing one-off concepts.
5. **Design for real-world complexity, not the happy path** — exceptions, escalation routes, aggregate caps, and ambiguity are the normal case for enterprise policy text, and the product (including its UI) must represent them clearly rather than hide them.

## Accessibility & Inclusion

No specific mandate established beyond standard web accessibility expectations (keyboard operability, screen-reader-usable Ant Design components). Revisit if a concrete requirement emerges.
