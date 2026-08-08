# Verification Guide

Use this reference before declaring an architecture or implementation complete and when reviewing an existing system.

## Contents

- Source and publication tests
- Deterministic rule tests
- Workflow tests
- Agent evaluations
- Security and isolation tests
- Architectural anti-patterns
- Definition of done

## Source and publication tests

- Verify all approved clauses, tables, qualifiers, and footnotes are represented.
- Verify superseded and draft content cannot become active accidentally.
- Verify searchable and executable projections share the same release.
- Verify rollback restores a consistent release.
- Compare extraction against policy-owner-approved golden cases.
- Verify source hashes and references resolve to the intended approved version.
- Verify policy owners can review the source-to-rule mapping before activation.

## Deterministic rule tests

- Cover every rule and decision-table branch.
- Test values immediately below, at, and above every threshold.
- Test inclusive and exclusive dates, time zones, calendars, units, and rounding.
- Test missing, stale, contradictory, and unauthorized facts.
- Test precedence, overlapping rules, multiple simultaneous entitlements, and exceptions.
- Verify replaying the same request and release produces the same decision.
- Verify unknown or retired releases fail safely.
- Verify reason codes and matched rule IDs remain stable enough for downstream consumers.

## Workflow tests

- Test every edge and terminal state.
- Verify no action can execute before required decision and approval states.
- Verify retries do not duplicate side effects.
- Verify checkpoint resume does not repeat completed actions.
- Verify timeouts, cancellation, escalation, dead-letter, and human rejection paths.
- Verify policy updates during active cases follow the declared pinning behavior.
- Verify malformed or free-form agent output cannot select workflow branches.
- Verify concurrent read operations reconcile deterministically.
- Verify a workflow cannot resume with a forged or cross-tenant state object.

## Agent evaluations

- Measure intent classification and domain-routing accuracy.
- Measure fact-extraction precision and recall by field.
- Measure whether the agent asks for every material missing fact and avoids irrelevant questions.
- Measure citation correctness and support for every explanatory claim.
- Measure faithfulness to the immutable decision result.
- Test abstention when evidence, tools, or policy versions are unavailable.
- Test prompt injection in user text, uploaded files, indexed policy content, and tool results.
- Test misleading user claims against authoritative system facts.
- Test that explanation wording cannot create an unsupported promise or approval.
- Evaluate separately by language, jurisdiction, case type, and material user population where relevant.

Do not use model-graded evaluations alone for binding policy correctness. Include deterministic assertions and policy-owner-reviewed golden cases.

## Security and isolation tests

- Test cross-user and cross-tenant access attempts.
- Test unauthorized policy and evidence retrieval.
- Test forged identifiers, roles, approvals, and workflow state.
- Test excessive tool arguments, malformed model output, and replayed approval responses.
- Verify logs, traces, errors, and audit records do not expose unnecessary sensitive data.
- Verify retrieval applies access filtering before returning content to the model.
- Verify every side-effecting service performs its own authorization checks.
- Verify secrets and credentials are not present in prompts, source, configuration files, traces, or generated documentation.
- Verify rate, token, iteration, timeout, concurrency, and payload limits.

## Architectural anti-patterns

Flag these as defects unless the use case clearly proves otherwise:

- copying an entire policy into every system prompt;
- hard-coding policy values only in prompts;
- using RAG as a rules engine;
- asking the LLM to calculate binding numeric or date-based entitlements;
- creating an agent for every policy or process step;
- routing binding outcomes from free-form model text;
- letting the model choose the active policy version;
- allowing the explanation agent to revise the decision;
- using group chat, voting, or model confidence as legal or policy authority;
- accepting user-provided facts without verification when authoritative systems exist;
- granting agents broad write access to systems of record;
- executing tools without idempotency and approval checks;
- caching decisions without policy version, identity, authorization, and relevant fact keys;
- storing the authoritative case only in conversation history;
- logging full sensitive prompts and tool payloads in production;
- activating LLM-extracted rules without human approval and regression tests;
- claiming compliance because responses usually look correct;
- silently falling back to model memory when retrieval or decision services fail.

## Definition of done

Treat the solution as complete only when:

- every automated binding decision maps to an approved source clause and executable rule;
- every discretionary outcome maps to the applicable source, an authorized human decision, and its evidence;
- every case records the exact policy release and verified fact provenance;
- deterministic outcomes are repeatable and boundary-tested;
- ambiguous, conflicting, unsupported, and missing-information cases cannot become automatic approvals;
- retrieval respects identity and document authorization before returning content;
- agents cannot bypass decision, approval, or action controls;
- actions are idempotent, authorized, auditable, and safe to retry or explicitly non-retriable;
- explanations are grounded in immutable decisions and exact evidence references;
- long-running workflows resume without duplicating completed effects;
- sensitive data is minimized in prompts and telemetry;
- required policy-owner, security, privacy, legal, and operational reviews are identified and completed according to organizational requirements;
- the implementation and documentation state all remaining assumptions and limitations truthfully.

Do not claim production readiness while policy approval, security validation, load testing, operational ownership, or required integration tests remain incomplete.
